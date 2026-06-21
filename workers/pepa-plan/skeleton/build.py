"""Label every corpus paper's paragraph moves, then synthesise the skeleton library.

Labelling is one fast LLM call per paper and scales to thousands of papers, so it
runs in one of three modes (config.mode(), default `auto`, picked by estimated
wall-clock):
  - serial   — one paper at a time (single paper, or a tiny corpus).
  - parallel — a thread pool bounded by the client's concurrency governor.
  - batch    — the same prompts go to the Anthropic Message Batches API: ~50%
               cheaper and far higher throughput, at the cost of asynchronous
               (typically up to ~1h) turnaround. Best for large volumes.
All three produce identical move sequences; only the transport differs. The final
clustering into 3–6 templates is a single quality call, always live.
"""
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import config
from backends import anthropic_client, llm, prompt
from cli import ui
from cli.progress import StepSpinner
from corpus.load import para_files
from corpus.parse_para import parse as parse_para
from skeleton import examples, moves


def build(limit=None, sample=None, mode=None):
    files = para_files()
    if not files:
        raise SystemExit(
            "No para_*.md files found in corpus.\n"
            "Run pepa-sum to generate paragraph rundowns first."
        )
    if sample and sample < len(files):
        files = random.sample(files, sample)
    if limit:
        files = files[:limit]

    sp = StepSpinner("Parsing corpus")
    sp.start()
    try:
        parsed = [(entry["base"], parse_para(entry["path"])) for entry in files]
        parsed = [(base, sentences) for base, sentences in parsed if sentences]
    finally:
        sp.done(f"{len(parsed)} papers")
    if not parsed:
        raise SystemExit("No paragraphs parsed from the corpus para_ files.")

    anthropic_client.reset_usage()
    chosen = _select_mode(len(parsed), mode)
    _show_plan(len(parsed), chosen, mode)
    _preflight_cost_check(parsed, chosen)

    if chosen == "batch":
        sequences = _label_batch(parsed)
    elif chosen == "serial":
        sequences = _label_serial(parsed)
    else:
        sequences = _label_parallel(parsed)

    _checkpoint_sequences(sequences)
    skeletons = synthesise(sequences)
    _report_cost()
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_papers": len(sequences),
        "skeletons": skeletons,
    }


# ---------------------------------------------------------------------------
# Mode selection (by estimated wall-clock time)
# ---------------------------------------------------------------------------

def _select_mode(n, override=None):
    wanted = (override or config.mode() or "auto").lower()
    if wanted in ("serial", "parallel", "batch"):
        return wanted
    if wanted != "auto":
        raise SystemExit(f"Unknown mode '{wanted}'. Use auto|serial|parallel|batch.")
    if n <= 1:
        return "serial"
    est = _estimate(n)
    return min(est, key=est.get)


def _estimate(n):
    """Rough wall-clock seconds for each mode at this volume. Batch carries a
    latency floor but very high throughput once running, so it overtakes parallel
    on large volumes (and is also billed at ~50%)."""
    serial = n * config.EST_LABEL_SECONDS
    parallel = max(serial / config.concurrency(), n / config.EST_PARALLEL_PPH * 3600)
    batch = max(config.EST_BATCH_FLOOR_MINUTES * 60, n / config.EST_BATCH_PPH * 3600)
    return {"serial": serial, "parallel": parallel, "batch": batch}


def _show_plan(n, chosen, override):
    ui.step(f"Labelling moves for {n} paper(s)")
    est = _estimate(n)
    for m in ("serial", "parallel", "batch"):
        mark = "  <- chosen" if m == chosen else ""
        ui.info(f"{m:<9} ~{_fmt(est[m])}{mark}")
    forced = (override or config.mode() or "auto").lower() != "auto"
    if forced:
        ui.info("(mode forced by setting/flag)")
    elif chosen == "batch":
        ui.info("(fastest estimate; batch is also billed at ~50%)")
    else:
        ui.info("(fastest estimate)")


def _preflight_cost_check(parsed, chosen, threshold=10.0):
    if not parsed:
        return
    model = config.anthropic_model()
    price = config.price_per_mtok(model)
    if price is None:
        return
    p_in, p_out = price
    total_in = total_out = 0
    for _base, sentences in parsed:
        n = len(sentences)
        total_in += 500 + 20 * n
        total_out += 16 * n + 64
    cost = total_in / 1e6 * p_in + total_out / 1e6 * p_out
    if chosen == "batch":
        cost *= 0.5
    if cost > threshold:
        ui.warn(
            f"Estimated cost: ~${cost:.2f}  "
            f"({total_in / 1e6:.2f}M in + {total_out / 1e6:.2f}M out · {model})"
        )
        if not ui.confirm("Cost exceeds threshold — proceed?"):
            raise SystemExit("Aborted.")
    else:
        ui.info(f"Est. cost ~${cost:.2f}")


# ---------------------------------------------------------------------------
# Labelling paths
# ---------------------------------------------------------------------------

def _label_serial(parsed):
    sequences = []
    n = len(parsed)
    for done, (base, sentences) in enumerate(parsed, 1):
        ui.info(f"[{done}/{n}] labelling {base}")
        try:
            sequences.append({"base": base, "moves": moves.label(sentences)})
        except Exception as e:  # transient exhaustion for one paper: skip it
            ui.error(f"[{done}/{n}] {base}: {e}")
    return sequences


def _label_parallel(parsed):
    n = len(parsed)
    workers = min(config.concurrency(), n)
    ui.info(f"parallel: up to {workers} labelling calls in flight  ·  "
            "Ctrl-C to stop")
    sequences = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(moves.label, sentences): base for base, sentences in parsed}
        for future in as_completed(futures):
            base = futures[future]
            done += 1
            ui.info(f"[{done}/{n}] labelled {base}")
            try:
                sequences.append({"base": base, "moves": future.result()})
            except Exception as e:  # transient exhaustion for one paper: skip it
                ui.error(f"[{done}/{n}] {base}: {e}")
    return sequences


def _label_batch(parsed):
    model = config.anthropic_model()
    requests, meta = [], {}
    for idx, (base, sentences) in enumerate(parsed):
        system, user, max_tokens = moves.request(sentences)
        cid = f"p{idx}"
        requests.append({"custom_id": cid, "system": system, "prompt": user,
                         "max_tokens": max_tokens, "model": model})
        meta[cid] = (base, len(sentences))

    ui.step(f"Submitting {len(requests)} request(s) to the Message Batches API")
    ui.info("most batches finish within ~1h (max 24h)  ·  Ctrl-C cancels the batch")
    results = anthropic_client.run_batch(
        requests, on_progress=_batch_progress(), on_created=_batch_created())

    sequences, missing = [], 0
    for cid, (base, n_sent) in meta.items():
        raw = results.get(cid)
        if raw is None:
            missing += 1
            continue
        sequences.append({"base": base, "moves": moves.parse(raw, n_sent)})
    if missing:
        ui.warn(f"{missing} paper(s) had no batch result — re-run to retry them")
    return sequences


def _batch_created():
    def cb(batch_id):
        ui.info(f"batch id: {batch_id}  ·  results retrievable from the API for 29 "
                "days — keep this id to recover after any crash")
    return cb


def _batch_progress():
    def cb(status):
        c = status.request_counts
        ui.info(f"batch {status.processing_status}: {c.succeeded} ok · "
                f"{c.errored} err · {c.processing} processing")
    return cb


# ---------------------------------------------------------------------------
# Synthesis (the fan-in: one quality call over the whole corpus)
# ---------------------------------------------------------------------------

# Move sequences are long and near-unique per paper, so the full corpus does not
# fit one context window (4307 papers ~= 1.09M tokens). Templates are a property of
# the corpus's recurring *shapes*, not of every individual string, so synthesis
# runs on a representative sample compacted by run-length-collapsing repeats. The
# budget is in characters (~3.3 chars/token) and stays well under the model limit.
SYNTH_CHAR_BUDGET = 600_000


def _collapse(move_list):
    """Run-length-collapse a move sequence to a compact string that keeps order
    and weight without one line per paragraph: ANALYSIS_FINDING x9, IMPLICATION."""
    runs = []
    for m in move_list:
        if runs and runs[-1][0] == m:
            runs[-1][1] += 1
        else:
            runs.append([m, 1])
    return ", ".join(m if c == 1 else f"{m} x{c}" for m, c in runs)


def prepare_synthesis(sequences, char_budget=SYNTH_CHAR_BUDGET, seed=0):
    """Compact sequences for the synthesis call and, if still over budget, draw a
    reproducible representative sample that fits. Returns (compact, n_total).

    Sorted by base first so the seeded sample is identical run-to-run: parallel
    labelling appends in completion order, which the seed alone wouldn't pin down."""
    ordered = sorted(sequences, key=lambda s: s["base"])
    compact = [{"base": s["base"], "moves": _collapse(s["moves"])} for s in ordered]
    n_total = len(compact)
    if sum(len(c["moves"]) + len(c["base"]) + 16 for c in compact) <= char_budget:
        return compact, n_total
    avg = max(1, sum(len(c["moves"]) + len(c["base"]) + 16 for c in compact) // n_total)
    keep = max(1, char_budget // avg)
    sample = random.Random(seed).sample(compact, min(keep, n_total))
    return sample, n_total


def _checkpoint_sequences(sequences):
    """Persist the labelled sequences before synthesis. Labelling is the paid,
    slow step; synthesis is fast but can fail, so banking the sequences here means
    a synthesis crash never discards the spend — re-run reads from this file."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.SEQUENCES_FILE.write_text(
        json.dumps(sequences, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ui.info(f"checkpointed {len(sequences)} sequence(s) -> {config.SEQUENCES_FILE.name}")


def synthesise(sequences):
    """The fan-in step: cluster the corpus's move sequences into 3-6 templates with
    one quality call. Shared by build() and the batch-recovery path."""
    compact, n_total = prepare_synthesis(sequences)
    ui.step("Synthesising skeleton library")
    if len(compact) != n_total:
        ui.info(f"synthesising over a representative sample of {len(compact)} "
                f"of {n_total} papers (corpus too large for one call)")
    raw = llm.complete(
        prompt.skeleton_system(),
        prompt.skeleton_prompt(compact, n_total=n_total),
        max_tokens=4000,
        quality=True,
    )
    skeletons = _parse_skeletons(raw)
    return examples.attach(skeletons, sequences)


# ---------------------------------------------------------------------------
# Synthesis parsing, cost, persistence
# ---------------------------------------------------------------------------

def _parse_skeletons(raw):
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"Could not parse skeleton JSON from model: {e}\n"
            "Try running python manage.py abstract again."
        )


def _report_cost():
    snap = anthropic_client.usage_snapshot()
    if not snap:
        return
    total_in = total_out = total_calls = 0
    cost, priced = 0.0, True
    for model, u in snap.items():
        total_calls += u["calls"]
        total_in += u["input"] + u["batch_input"]
        total_out += u["output"] + u["batch_output"]
        price = config.price_per_mtok(model)
        if price is None:
            priced = False
            continue
        p_in, p_out = price
        cost += (u["input"] / 1e6 * p_in + u["output"] / 1e6 * p_out
                 + 0.5 * (u["batch_input"] / 1e6 * p_in + u["batch_output"] / 1e6 * p_out))
    if not total_calls:
        return
    tokens = f"{total_in:,} in + {total_out:,} out over {total_calls} calls"
    batched = any(u["batch_input"] or u["batch_output"] for u in snap.values())
    note = "  ·  batch billed at 50%" if batched else ""
    if priced:
        ui.info(f"est. cost ~${cost:.2f}  ·  {tokens}{note}  ·  estimate only, verify pricing")
    else:
        ui.info(f"LLM usage: {tokens}{note} (price unknown for some models)")


def _fmt(seconds):
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def save(library):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.SKELETONS_FILE.write_text(
        json.dumps(library, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load():
    if not config.SKELETONS_FILE.exists():
        return None
    return json.loads(config.SKELETONS_FILE.read_text(encoding="utf-8"))
