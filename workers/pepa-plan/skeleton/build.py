"""Label every paper's paragraph moves via one LLM call each, in serial,
parallel, or batch mode by estimated wall-clock, then synthesise the
skeleton library with one final clustering call.
"""
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import config
from backends import anthropic_client, llm, prompt
from cli import ui
from cli.progress import StepSpinner
from corpus.load import paper_count, para_files
from corpus.parse_para import parse as parse_para
from skeleton import examples, moves

COST_WARNING_THRESHOLD = 10.0
SYNTH_CHAR_BUDGET = 600_000
CHARS_PER_TOKEN = 4
CHARS_PER_SENTENCE = 236
TYPICAL_SENTENCES = 36
SYNTH_PROMPT_TOKENS = 2_000
SYNTH_OUTPUT_TOKENS = 4_000
BLUEPRINT_CALLS_AT_MOST = 30
BLUEPRINT_INPUT_TOKENS = 7_000
BLUEPRINT_OUTPUT_TOKENS = 1_500


def build(limit=None, sample=None, mode=None, approved=None):
    """Label the papers added since the last run, then synthesise the library from every labelled paper.
    `approved` is None, or the most the user agreed to spend. Returns None when there is nothing new.
    """
    known = labelled_before()
    found = papers_to_label(limit, sample, known)
    parsed = parse_papers(found["files"])
    if not parsed and config.SKELETONS_FILE.exists():
        ui.ok(f"All {len(known)} papers were labelled before; the library is up to date.")
        return None
    if not parsed and not known:
        raise SystemExit("No paragraphs parsed from the corpus para_ files.")

    anthropic_client.reset_usage()
    chosen = _select_mode(len(parsed), mode)
    new_sequences = []
    if parsed:
        _show_plan(len(parsed), chosen, mode)
        _preflight_cost_check([len(sentences) for _base, sentences in parsed], chosen, approved)
        if chosen == "batch":
            new_sequences = _label_batch(parsed)
        elif chosen == "serial":
            new_sequences = _label_serial(parsed)
        else:
            new_sequences = _label_parallel(parsed)

    sequences = new_sequences
    for base, sequence in known.items():
        if base in found["bases"]:
            sequences.append(sequence)
    _checkpoint_sequences(sequences)
    skeletons = synthesise(sequences)
    _report_cost()
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_papers": len(sequences),
        "skeletons": skeletons,
    }


def labelled_before():
    """The move sequences an earlier run labelled, keyed by paper, so a new run labels only papers added since."""
    if not config.SEQUENCES_FILE.exists():
        return {}
    known = {}
    for sequence in json.loads(config.SEQUENCES_FILE.read_text(encoding="utf-8")):
        known[sequence["base"]] = sequence
    return known


def papers_to_label(limit, sample, known):
    """The corpus files of every paper not labelled before, cut to the sample or limit asked for.

    Returns:
        dict with "files", the corpus entries to label, and "bases", every paper in the corpus.
    """
    files = para_files()
    if not files:
        raise SystemExit(
            "No para_*.md files found in corpus.\n"
            "Run pepa-sum to generate paragraph rundowns first."
        )
    new_files = [entry for entry in files if entry["base"] not in known]
    if sample and sample < len(new_files):
        new_files = random.sample(new_files, sample)
    if limit:
        new_files = new_files[:limit]
    return {"files": new_files, "bases": {entry["base"] for entry in files}}


def parse_papers(files):
    """Each file's paper name and its paragraph sentences, leaving out files with none."""
    sp = StepSpinner("Parsing corpus")
    sp.start()
    parsed = []
    try:
        for entry in files:
            sentences = parse_para(entry["path"])
            if sentences:
                parsed.append((entry["base"], sentences))
    finally:
        sp.done(f"{len(parsed)} new papers")
    return parsed


def print_estimate(limit=None, sample=None, mode=None, more=0):
    """Print, as one JSON line, how many papers a run would label, each mode's time, and the cost at list price.
    `more` counts papers not in the corpus yet, such as those still to be summarised.
    """
    known = labelled_before()
    files = []
    if paper_count() > 0:
        files = papers_to_label(limit, sample, known)["files"]
    sentence_counts = [max(1, entry["path"].stat().st_size // CHARS_PER_SENTENCE) for entry in files]
    sentence_counts += [TYPICAL_SENTENCES] * more
    up_to_date = not sentence_counts and config.SKELETONS_FILE.exists()
    n = len(sentence_counts)
    seconds = _estimate(max(n, 1))
    cost = {}
    for name in seconds:
        cost[name] = 0.0 if up_to_date else run_cost(sentence_counts, name)
    print(json.dumps({
        "papers": n,
        "labelled": len(known),
        "model": config.model_names()["fast"],
        "auto": _select_mode(n, mode) if n else "serial",
        "seconds": seconds,
        "cost": cost,
        "blueprints": 0.0 if up_to_date else blueprint_cost(),
    }))


# ---- Mode selection ----
# By estimated wall-clock time.

def _select_mode(n, override=None):
    wanted = (override or config.load()["mode"] or "auto").lower()
    if wanted == "batch" and config.load()["backend"] != "anthropic":
        raise SystemExit("Batch mode requires the anthropic backend.")
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
    on large volumes (and is also billed at ~50%). Batch needs the anthropic backend."""
    serial = n * config.EST_LABEL_SECONDS
    concurrency = config.load()["concurrency"]
    parallel = max(serial / concurrency, n / config.EST_PARALLEL_PPH * 3600)
    estimates = {"serial": serial, "parallel": parallel}
    if config.load()["backend"] == "anthropic":
        estimates["batch"] = max(config.EST_BATCH_FLOOR_MINUTES * 60, n / config.EST_BATCH_PPH * 3600)
    return estimates


def _show_plan(n, chosen, override):
    ui.step(f"Labelling moves for {n} paper(s)")
    est = _estimate(n)
    for m in est:
        mark = "  <- chosen" if m == chosen else ""
        ui.info(f"{m:<9} ~{_fmt(est[m])}{mark}")
    forced = (override or config.load()["mode"] or "auto").lower() != "auto"
    if forced:
        ui.info("(mode forced by setting/flag)")
    elif chosen == "batch":
        ui.info("(fastest estimate; batch is also billed at ~50%)")
    else:
        ui.info("(fastest estimate)")


def run_cost(sentence_counts, chosen):
    """List-price dollars for labelling papers with these sentence counts and the one synthesis call, or None without a price."""
    if config.load()["backend"] != "anthropic":
        return None
    names = config.model_names()
    fast = config.price_per_mtok(names["fast"])
    quality = config.price_per_mtok(names["quality"])
    if fast is None or quality is None:
        return None
    label_in = label_out = 0
    for count in sentence_counts:
        label_in += 500 + 20 * count
        label_out += 16 * count + 64
    labelling = label_in / 1e6 * fast[0] + label_out / 1e6 * fast[1]
    if chosen == "batch":
        labelling *= 0.5
    synthesis_in = SYNTH_PROMPT_TOKENS + SYNTH_CHAR_BUDGET / CHARS_PER_TOKEN
    synthesis = synthesis_in / 1e6 * quality[0] + SYNTH_OUTPUT_TOKENS / 1e6 * quality[1]
    return labelling + synthesis


def blueprint_cost():
    """List-price dollars for the most the blueprint calls after a new library can spend, or None without a price."""
    quality = config.price_per_mtok(config.model_names()["quality"])
    if config.load()["backend"] != "anthropic" or quality is None:
        return None
    one_call = BLUEPRINT_INPUT_TOKENS / 1e6 * quality[0] + BLUEPRINT_OUTPUT_TOKENS / 1e6 * quality[1]
    return BLUEPRINT_CALLS_AT_MOST * one_call


def _preflight_cost_check(sentence_counts, chosen, approved, threshold=COST_WARNING_THRESHOLD):
    """Show the estimated cost and stop above the approved amount; above the threshold, go on only when
    the run was approved or the user says yes."""
    cost = run_cost(sentence_counts, chosen)
    if cost is None:
        return
    model = config.model_names()["fast"]
    if approved is not None and cost > approved:
        raise SystemExit(
            f"Stopped before spending: {len(sentence_counts)} papers would cost about ${cost:.2f}, more than the "
            f"${approved:.2f} approved. Open Process papers again for the new estimate."
        )
    if cost <= threshold:
        ui.info(f"Est. cost ~${cost:.2f}")
        return
    ui.warn(f"Estimated cost: ~${cost:.2f} ({model})")
    if approved is not None:
        return
    if not ui.confirm("Cost exceeds threshold, proceed?", default_yes=False):
        raise SystemExit("Stopped before spending.")


# ---- Labelling paths ----

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
    workers = min(config.load()["concurrency"], n)
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
    model = config.load()["anthropic_model"]
    requests, meta = [], {}
    for idx, (base, sentences) in enumerate(parsed):
        built = moves.request(sentences)
        system, user, max_tokens = built["system"], built["prompt"], built["max_tokens"]
        cid = f"p{idx}"
        requests.append({
            "custom_id": cid,
            "system": system,
            "prompt": user,
            "max_tokens": max_tokens,
            "model": model,
        })
        meta[cid] = (base, len(sentences))

    ui.step(f"Submitting {len(requests)} request(s) to the Message Batches API")
    ui.info("most batches finish within ~1h (max 24h)  ·  Ctrl-C cancels the batch")
    results = anthropic_client.run_batch(
        requests, on_progress=_batch_progress, on_created=_batch_created)

    sequences, missing = [], 0
    for cid, (base, n_sent) in meta.items():
        raw = results.get(cid)
        if raw is None:
            missing += 1
            continue
        sequences.append({"base": base, "moves": moves.parse(raw, n_sent)})
    if missing:
        ui.warn(f"{missing} paper(s) had no batch result, re-run to retry them")
    return sequences


def _batch_created(batch_id):
    ui.info(f"batch id: {batch_id}  ·  results retrievable from the API for 29 "
            "days, keep this id to recover after any crash")


def _batch_progress(status):
    c = status.request_counts
    ui.info(f"batch {status.processing_status}: {c.succeeded} ok · "
            f"{c.errored} err · {c.processing} processing")


# ---- Synthesis ----
# The fan-in: one quality call over the whole corpus. Move sequences are long and
# near-unique per paper, so the full corpus does not fit one context window (4307
# papers ~= 1.09M tokens). Templates are a property of the corpus's recurring
# *shapes*, not of every individual string, so synthesis runs on a representative
# sample compacted by run-length-collapsing repeats. The budget is in characters
# (~3.3 chars/token) and stays well under the model limit.

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
    reproducible representative sample that fits.

    Sorted by base first so the seeded sample is identical run-to-run: parallel
    labelling appends in completion order, which the seed alone wouldn't pin down.

    Returns:
        dict with `compact` (the sequences to synthesise from) and `n_total`
        (the full corpus size before any sampling).
    """
    ordered = sorted(sequences, key=lambda s: s["base"])
    compact = [{"base": s["base"], "moves": _collapse(s["moves"])} for s in ordered]
    n_total = len(compact)
    if sum(len(c["moves"]) + len(c["base"]) + 16 for c in compact) <= char_budget:
        return {"compact": compact, "n_total": n_total}
    avg = max(1, sum(len(c["moves"]) + len(c["base"]) + 16 for c in compact) // n_total)
    keep = max(1, char_budget // avg)
    sample = random.Random(seed).sample(compact, min(keep, n_total))
    return {"compact": sample, "n_total": n_total}


def _checkpoint_sequences(sequences):
    """Persist the labelled sequences before synthesis. Labelling is the paid,
    slow step; synthesis is fast but can fail, so banking the sequences here means
    a synthesis crash never discards the spend, re-run reads from this file."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.SEQUENCES_FILE.write_text(
        json.dumps(sequences, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ui.info(f"checkpointed {len(sequences)} sequence(s) -> {config.SEQUENCES_FILE.name}")


def synthesise(sequences):
    """The fan-in step: cluster the corpus's move sequences into 3-6 templates with
    one quality call. Shared by build() and the batch-recovery path."""
    prepared = prepare_synthesis(sequences)
    compact = prepared["compact"]
    n_total = prepared["n_total"]
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


# ---- Synthesis parsing, cost, persistence ----

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
            f"Try running {config.COMMAND} abstract again."
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
