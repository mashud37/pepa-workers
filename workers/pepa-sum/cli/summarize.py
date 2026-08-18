"""Turn every PDF in input/ into sum_, para_, and quote_ documents in
output/, picking serial, parallel, or batch execution by estimated
wall-clock.
"""
import sys
import time
from functools import partial

import config
from cli import ui
from cli.progress import StepSpinner, ProgressSpinner, _CHECK, _LABEL_W
from render import paper_stem

_DOCS = ("sum", "para", "quote")
_LABELS = {
    "sum": "sum_  structured brief",
    "para": "para_ paragraph rundown",
    "quote": "quote_ salient quotes",
}

# PDFs that yield fewer characters than this have no usable text layer and are
# skipped: they produce meaningless LLM output rather than a real summary.
MIN_TEXT_CHARS = 5000

# Above this estimated dollar cost, a run asks for confirmation before spending.
COST_CONFIRM_THRESHOLD = 10.0
# Paper name width in the per-paper progress line before it gets truncated.
PAPER_NAME_WIDTH = 50

# spaCy/numpy (thinc, blis, MKL/OpenBLAS) each default to one compute thread per
# core. The local stage already parallelises across papers with a process pool,
# so every worker must run single-threaded, otherwise N workers spawn N*cores
# threads that thrash the CPU instead of parsing. Pinning these to 1 is the
# difference between seconds and minutes per paper; it changes no output.
_THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def _pin_threads():
    import os
    for var in _THREAD_ENV:
        os.environ[var] = "1"


def run(input_dir=None, output_dir=None, force=False, mode=None):
    _pin_threads()  # parent sets them so spawned workers inherit before numpy imports
    try:
        from extract import read_document, extract_signals, select_passages  # noqa: F401
    except ImportError as e:
        raise SystemExit(f"Missing dependency ({e.name}). Run: pip install -r requirements.txt")

    in_dir = (input_dir or config.INPUT_DIR)
    out_dir = (output_dir or config.OUTPUT_DIR)
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    sources = _discover_sources(in_dir)
    if not sources:
        raise SystemExit(f"No papers found in {in_dir}. Drop .pdf, .md or .txt files there "
                         "and re-run.")

    on_existing = config.load('ON_EXISTING')
    ui.header("pepa-sum: summarising papers")
    ui.info(f"{len(sources)} paper(s) in {in_dir}")
    ui.info(f"backend: {config.load('BACKEND')}  ·  paragraph rundown: {config.load('PARA_METHOD')}")

    planned = _plan_work(sources, out_dir, force, on_existing)
    work, skipped = planned["work"], planned["skipped"]
    if not work:
        ui.step("Done")
        ui.ok(f"0 processed, {skipped} skipped")
        return 0

    chosen = _select_mode(len(work), mode)
    _show_plan(len(work), chosen, mode)
    _preflight_cost_check(work, chosen)
    _reset_usage()

    if chosen == "serial":
        code = _run_serial(sources, out_dir, force, on_existing)
    elif chosen == "batch":
        code = _run_batch(work, out_dir, skipped)
    else:
        code = _run_parallel(work, out_dir, skipped)
    _report_cost()
    return code


def _discover_sources(in_dir):
    """Every ingestable paper in in_dir (.pdf, .md/.markdown, or .txt), one per
    stem. When a stem has both a PDF and a text file (e.g. a hand-converted
    paper.pdf + paper.md), the text file wins: it is already reflowed and
    reference-stripped, so re-reading the PDF would be wasted work and could
    disagree with it. Both still map to the same sum_<stem>.md output, so taking
    one prevents a silent overwrite."""
    from extract import SUFFIXES

    found = {}
    for p in sorted(in_dir.iterdir()):
        if not (p.is_file() and p.suffix.lower() in SUFFIXES):
            continue
        stem = paper_stem(p.name)
        prior = found.get(stem)
        if prior is None or (prior.suffix.lower() == ".pdf" and p.suffix.lower() != ".pdf"):
            found[stem] = p
    return [found[stem] for stem in sorted(found)]


def _plan_work(sources, out_dir, force, on_existing):
    """Papers to (re)process, resolved without prompting: `ask` is treated as
    `skip` here, as it already is off a TTY. Each entry is (pdf, regen); regen
    True redoes all three documents, False fills only the missing ones."""
    work, skipped = [], 0
    for pdf in sources:
        present = [d for d in _DOCS if (out_dir / f"{d}_{paper_stem(pdf.name)}.md").exists()]
        if force:
            work.append((pdf, True))
        elif len(present) == len(_DOCS):
            if on_existing == "overwrite":
                work.append((pdf, True))
            else:
                skipped += 1
        else:
            work.append((pdf, False))
    return {"work": work, "skipped": skipped}


def _docs_todo(pdf, out_dir, regen):
    """Which of the three documents this paper still needs."""
    return [d for d in _DOCS if regen or not (out_dir / f"{d}_{paper_stem(pdf.name)}.md").exists()]


# ---- Mode selection (by estimated wall-clock time) ----

def _select_mode(n, override=None):
    """Resolve the execution mode. cloudrun is always serial; an explicit mode
    (flag or config) is honoured; otherwise `auto` picks the fastest estimate."""
    wanted = (override or config.load('MODE') or "auto").lower()
    if config.load('BACKEND') == "cloudrun":
        if wanted == "batch":
            raise SystemExit("Batch mode requires the anthropic backend.")
        return "serial"
    if wanted in ("serial", "parallel", "batch"):
        return wanted
    if wanted != "auto":
        raise SystemExit(f"Unknown mode '{wanted}'. Use auto|serial|parallel|batch.")
    if n <= 1:
        return "serial"
    est = _estimate(n)
    return min(est, key=est.get)


def _estimate(n):
    """Rough wall-clock seconds for each mode at this volume. Parallel is bounded
    by the tier-realistic papers/hour (raising the worker counts won't beat the
    account's rate limit); batch carries a latency floor but very high throughput
    once running, so it overtakes parallel on large volumes."""
    cores = config.local_workers()
    conc = config.max_concurrency()
    local_serial = n * config.EST_LOCAL_SECONDS
    llm_serial = n * config.EST_LLM_SECONDS
    serial = local_serial + llm_serial
    parallel = max(local_serial / cores + llm_serial / conc,
                   n / config.est_parallel_pph() * 3600)
    batch = max(config.EST_BATCH_FLOOR_MINUTES * 60, n / config.EST_BATCH_PPH * 3600)
    return {"serial": serial, "parallel": parallel, "batch": batch}


def _show_plan(n, chosen, override):
    ui.step(f"Planning {n} paper(s)")
    if config.load('BACKEND') == "cloudrun":
        ui.info("cloudrun backend: serial (single scale-to-zero instance)")
        return
    est = _estimate(n)
    for m in ("serial", "parallel", "batch"):
        mark = "  <- chosen" if m == chosen else ""
        ui.info(f"{m:<9} ~{_fmt(est[m])}{mark}")
    forced = (override or config.load('MODE') or "auto").lower() != "auto"
    if forced:
        ui.info("(mode forced by setting/flag)")
    elif chosen == "batch":
        ui.info("(fastest estimate; batch is also billed at ~50%)")
    else:
        ui.info("(fastest estimate)")


# ---- Local extraction stage (CPU-bound; runs across processes to escape the GIL) ----

def _plans(work, out_dir):
    """(pdf, todo) for every paper that still needs at least one document."""
    plans = [(pdf, _docs_todo(pdf, out_dir, regen)) for pdf, regen in work]
    return [(pdf, todo) for pdf, todo in plans if todo]


def _extract_paper(pdf, todo):
    """Worker: read and signal-extract one paper, returning the artifacts inline.

    Used for parallel mode, where the pipeline keeps only a bounded look-ahead
    window of papers in memory at once.

    Returns:
        The `pdf` and its `todo` back, plus `artifacts` holding `text`,
        `signals` and `passages`, or None when the paper has no usable text.
    """
    from extract import read_document, extract_signals, select_passages
    text = read_document(pdf)
    if not text or len(text) < MIN_TEXT_CHARS:
        return {"pdf": pdf, "todo": todo, "artifacts": None}
    signals = extract_signals(text)
    passages = select_passages(text, signals)
    return {
        "pdf": pdf,
        "todo": todo,
        "artifacts": {"text": text, "signals": signals, "passages": passages},
    }


def _extract_to_disk(pdf, todo, idx, spool):
    """Worker: read and signal-extract one paper, pickling its artifacts to disk.

    Spooling inside the child keeps the heavy artifacts off the parent process:
    for batch mode, where every paper is read up front before any LLM work.

    Returns:
        The `pdf` and its `todo` back, plus the `path` of the pickle holding
        (text, signals, passages), or None when the paper has no usable text.
    """
    import pickle
    from extract import read_document, extract_signals, select_passages
    text = read_document(pdf)
    if not text or len(text) < MIN_TEXT_CHARS:
        return {"pdf": pdf, "todo": todo, "path": None}
    signals = extract_signals(text)
    passages = select_passages(text, signals)
    path = spool / f"{idx}.pkl"
    with open(path, "wb") as f:
        pickle.dump((text, signals, passages), f, protocol=pickle.HIGHEST_PROTOCOL)
    return {"pdf": pdf, "todo": todo, "path": path}


def _extract_to_spool(plans, spool, n):
    """Read every paper across processes, each worker pickling its artifacts into
    `spool`; the parent collects only lightweight (pdf, todo, path) handles, so
    peak memory stays flat regardless of volume.

    Returns:
        The `spooled` (pdf, todo, path) handles and the count of `errors`.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    workers = min(config.local_workers(), n)
    ui.step(f"Reading {n} paper(s) locally: PDF + spaCy signals, {workers} process(es)")
    spooled, failures = [], []
    sp = ProgressSpinner("reading + signals", n)
    sp.start()
    try:
        with ProcessPoolExecutor(max_workers=workers, initializer=_pin_threads) as ex:
            futures = {ex.submit(_extract_to_disk, pdf, todo, idx, spool): pdf
                       for idx, (pdf, todo) in enumerate(plans)}
            for fut in as_completed(futures):
                pdf = futures[fut]
                try:
                    read = fut.result()
                except Exception as e:
                    failures.append(f"[read] {_short(pdf.name)}: {e}")
                else:
                    if read["path"] is None:
                        failures.append(f"[read] {_short(pdf.name)}: no extractable text")
                    else:
                        spooled.append((pdf, read["todo"], read["path"]))
                sp.advance()
    finally:
        sp.done(f"{len(spooled)}/{n} read"
                + (f", {len(failures)} failed" if failures else ""))
    for msg in failures:  # printed after the spinner closes, so the line stays clean
        ui.error(msg)
    return {"spooled": spooled, "errors": len(failures)}


# ---- Parallel mode (extract across processes, then build across threads) ----

def _builders(artifacts):
    """The three document builders for one paper, each ready to call with no arguments."""
    import documents

    text = artifacts["text"]
    signals = artifacts["signals"]
    passages = artifacts["passages"]
    return {
        "sum": lambda: documents.build_summary(text, signals, passages),
        "para": lambda: documents.build_rundown(text),
        "quote": lambda: documents.build_quotes(text, signals),
    }


def _write_one(out_dir, kind, name, build):
    """Build one document and write it under `out_dir`."""
    from render import write_doc

    write_doc(out_dir, kind, name, build())


def _write_together(out_dir, name, builders, kinds):
    """Build several documents at once, a thread each, then write them in order."""
    from concurrent.futures import ThreadPoolExecutor
    from render import write_doc

    with ThreadPoolExecutor(max_workers=len(kinds)) as ex:
        running = [(kind, ex.submit(builders[kind])) for kind in kinds]
        for kind, job in running:
            write_doc(out_dir, kind, name, job.result())


def _saved(_result):
    return "saved"


def _build_live(pdf, out_dir, todo, artifacts):
    """Build this paper's outstanding documents via live LLM calls. Mirrors the
    document set and ordering of _summarise_one, without the spinner."""
    builders = _builders(artifacts)
    llm_todo = [d for d in ("sum", "para") if d in todo]
    if len(llm_todo) == 2:
        _write_together(out_dir, pdf.name, builders, llm_todo)
    else:
        for d in llm_todo:
            _write_one(out_dir, d, pdf.name, builders[d])
    if "quote" in todo:
        _write_one(out_dir, "quote", pdf.name, builders["quote"])


class _Pipeline:
    """One parallel run's queues and counters, shared by the extract and build pools.

    Holds the look-ahead window so that at most `window` papers' artifacts are
    ever live in this process, whatever the corpus size.
    """

    def __init__(self, plans, out_dir, window):
        self.pending = list(plans)
        self.out_dir = out_dir
        self.window = window
        self.extract_futs = {}
        self.build_futs = {}
        self.done = 0
        self.errors = 0

    def refill(self, px):
        """Submit papers for extraction until the look-ahead window is full."""
        while self.pending and (len(self.extract_futs) + len(self.build_futs)) < self.window:
            pdf, todo = self.pending.pop(0)
            self.extract_futs[px.submit(_extract_paper, pdf, todo)] = pdf

    def on_extracted(self, fut, tx, sp):
        """Hand one finished extraction to the build pool, or count it as failed."""
        pdf = self.extract_futs.pop(fut)
        try:
            read = fut.result()
        except Exception as e:
            self.errors += 1
            sp.log(ui.line("error", f"{_short(pdf.name)} read failed: {e}"))
            sp.advance()
            return
        if read["artifacts"] is None:
            self.errors += 1
            sp.log(ui.line("warn", f"{_short(pdf.name)} no extractable text"))
            sp.advance()
            return
        todo = read["todo"]
        job = tx.submit(_build_live, pdf, self.out_dir, todo, read["artifacts"])
        self.build_futs[job] = (pdf, todo)

    def on_built(self, fut, sp):
        """Record one paper's documents, whether they were written or failed."""
        pdf, todo = self.build_futs.pop(fut)
        try:
            fut.result()
            self.done += 1
            built = " ".join(f"{d}_" for d in todo)
            sp.log(ui.line("ok", f"{_short(pdf.name)} {built}"))
        except Exception as e:  # per-paper failure: log and continue
            self.errors += 1
            saved = _maybe_log_truncated(self.out_dir, pdf.name, e)
            extra = " (partial saved for eval)" if saved else ""
            sp.log(ui.line("error", f"{_short(pdf.name)} build failed: {e}{extra}"))
        sp.advance()

    def run(self, px, tx, sp):
        """Keep both pools fed until every paper has been read and built."""
        from concurrent.futures import wait, FIRST_COMPLETED

        self.refill(px)
        while self.extract_futs or self.build_futs:
            ready, _ = wait(set(self.extract_futs) | set(self.build_futs),
                            return_when=FIRST_COMPLETED)
            for fut in ready:
                if fut in self.extract_futs:
                    self.on_extracted(fut, tx, sp)
                else:
                    self.on_built(fut, sp)
            self.refill(px)

    def cancel(self):
        """Drop queued papers and cancel whatever has not started yet."""
        self.pending.clear()
        for fut in list(self.extract_futs) + list(self.build_futs):
            fut.cancel()


def _run_parallel(work, out_dir, skipped):
    """Pipeline the two stages: keep the local extraction process-pool running a
    bounded look-ahead window *ahead* of the LLM thread-pool, so the next papers'
    spaCy/BM25 work proceeds on the CPU while the current papers' LLM calls wait
    on the network. The window (LOCAL_BATCH) caps how many extracted papers are
    held in memory at once, so peak memory stays flat regardless of volume."""
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

    plans = _plans(work, out_dir)
    n = len(plans)
    if not n:
        ui.step("Done")
        ui.ok(f"0 processed, {skipped} skipped")
        return 0

    local_w = min(config.local_workers(), n)
    paper_w = min(config.paper_workers(), n)
    window = max(config.local_batch(), paper_w)
    ui.info(f"parallel ({config.speed()}): reading up to {window} papers ahead "
            f"across {local_w} process(es), summarising {paper_w} at once, up to "
            f"{config.max_concurrency()} LLM calls in flight  ·  "
            f"Ctrl-C to stop after running papers finish")
    ui.step(f"Summarising {n} paper(s)")

    pipeline = _Pipeline(plans, out_dir, window)
    # Live [i/N] + ETA, lit BEFORE the first blocking wait, advancing once per
    # paper (on a read failure, or when its build finishes) so the screen is never
    # dead while the first papers are still being read/OCR'd.
    sp = ProgressSpinner("summarising", n)
    sp.start()
    interrupted = False
    with ProcessPoolExecutor(max_workers=local_w, initializer=_pin_threads) as px, \
         ThreadPoolExecutor(max_workers=paper_w) as tx:
        try:
            pipeline.run(px, tx, sp)
        except KeyboardInterrupt:
            interrupted = True
            pipeline.cancel()

    done, errors = pipeline.done, pipeline.errors
    sp.done(f"{done}/{n} built" + (f", {errors} failed" if errors else ""))
    if interrupted:
        ui.warn("stopped: finished papers are saved; the rest were cancelled")

    ui.step("Done")
    ui.ok(f"{done} processed, {skipped} skipped, {errors} failed")
    return 1 if errors else 0


# ---- Batch mode (Anthropic Message Batches API) ----

def _summary_request(idx, text, signals, passages):
    """Build one paper's summary request for the batch.

    Returns:
        The `request` and the `cid` it will come back under, or `oversize` set
        when the prompt is too large for the model context.
    """
    from documents import summary
    from backends import SUMMARY_SYSTEM, build_summary_prompt
    from backends import anthropic_client

    prompt = build_summary_prompt(text, signals, passages)
    # A batch request too large for the context window would fail silently and
    # re-fail on every re-run; catch it here instead.
    if anthropic_client.would_overflow(SUMMARY_SYSTEM, prompt, summary.MAX_TOKENS):
        return {"request": None, "cid": None, "oversize": True}
    cid = f"p{idx}s"
    return {
        "request": {
            "custom_id": cid,
            "system": SUMMARY_SYSTEM,
            "prompt": prompt,
            "max_tokens": summary.MAX_TOKENS,
        },
        "cid": cid,
        "oversize": False,
    }


def _rundown_requests(idx, text):
    """Build one paper's rundown chunk requests, empty when it has no paragraphs.

    Returns:
        The `requests` for the batch and the `cids` their answers arrive under.
    """
    from documents import rundown

    requests, cids = [], []
    for j, chunk in enumerate(rundown.chunk_paragraphs(text)):
        cid = f"p{idx}c{j}"
        built = rundown.chunk_request(chunk)
        requests.append({
            "custom_id": cid,
            "system": built["system"],
            "prompt": built["prompt"],
            "max_tokens": built["max_tokens"],
        })
        cids.append(cid)
    return {"requests": requests, "cids": cids}


def _plan_one_paper(entry, idx, out_dir, para_llm):
    """Turn one spooled paper into its batch requests and a plan for reassembly.

    Deterministic documents (quotes, and rundowns unless PARA_METHOD is llm)
    need no LLM, so they are written here and the plan records that the paper
    already produced output. The paper's spool file is deleted once read, so
    peak memory stays at one paper's artifacts.

    Returns:
        The `requests` this paper adds to the batch, and its `plan`.
    """
    import os
    import pickle

    import documents
    from documents import rundown
    from render import write_doc

    pdf, todo, path = entry
    with open(path, "rb") as f:
        text, signals, passages = pickle.load(f)
    plan = {"pdf": pdf, "sum": None, "para": None, "wrote": False, "oversize": False}
    requests = []

    if "quote" in todo:
        write_doc(out_dir, "quote", pdf.name, documents.build_quotes(text, signals))
        plan["wrote"] = True

    if "sum" in todo:
        wanted = _summary_request(idx, text, signals, passages)
        plan["oversize"] = wanted["oversize"]
        plan["sum"] = wanted["cid"]
        if wanted["request"] is not None:
            requests.append(wanted["request"])

    if "para" in todo and not para_llm:
        write_doc(out_dir, "para", pdf.name, documents.build_rundown(text))
        plan["wrote"] = True
    elif "para" in todo:
        built = _rundown_requests(idx, text)
        if not built["requests"]:
            write_doc(out_dir, "para", pdf.name, rundown.NO_PARAGRAPHS)
            plan["wrote"] = True
        else:
            requests.extend(built["requests"])
            plan["para"] = built["cids"]

    os.remove(path)  # artifacts consumed; keep the spool small too
    return {"requests": requests, "plan": plan}


def _assemble_one_paper(plan, batch_out, out_dir):
    """Write one paper's documents from the batch results it expected.

    A paper counts as done only if every request it queued came back; a summary
    cut off at the token limit is saved for eval but still counts as a failure.

    Returns:
        Whether the paper `wrote` anything, whether it `failed`, and whether its
        summary was `truncated`.
    """
    import documents
    from documents import rundown
    from render import write_doc

    results = batch_out["results"]
    truncated = batch_out["truncated"]
    pdf = plan["pdf"]
    wrote = plan["wrote"]
    failed = truncated_sum = False

    if plan["sum"] is not None:
        text = results.get(plan["sum"])
        if plan["sum"] in truncated:
            _log_truncated(out_dir, pdf.name, text)
            failed = truncated_sum = True
        elif text and documents.has_template(text):
            write_doc(out_dir, "sum", pdf.name, text)
            wrote = True
        else:
            failed = True

    if plan["para"] is not None:
        texts = [results.get(c) for c in plan["para"]]
        if all(t is not None for t in texts):
            write_doc(out_dir, "para", pdf.name, rundown.assemble_rundown(texts))
            wrote = True
        else:
            failed = True

    return {"wrote": wrote, "failed": failed, "truncated": truncated_sum}


def _build_batch_requests(spooled, out_dir):
    """Build every paper's batch requests and its plan for reassembly.

    One paper's spooled artifacts are loaded and freed at a time, so peak memory
    is one paper plus the batch payload rather than the whole corpus.

    Returns:
        The `requests` for the whole batch and the per-paper `plans`.
    """
    para_llm = config.load('PARA_METHOD') == "llm"
    total = len(spooled)
    ui.step(f"Building batch requests for {total} paper(s)")
    requests, plans = [], []
    for idx, entry in enumerate(spooled):
        pdf = entry[0]
        ui.info(f"[{idx + 1}/{total}] {_short(pdf.name)}")
        built = _plan_one_paper(entry, idx, out_dir, para_llm)
        requests.extend(built["requests"])
        plans.append(built["plan"])
    return {"requests": requests, "plans": plans}


def _assemble_batch(plans, batch_out, out_dir):
    """Write every paper's documents from the finished batch.

    Returns:
        The count of papers `done` and the count that hit `errors`.
    """
    done = errors = 0
    ui.step(f"Assembling results for {len(plans)} paper(s)")
    for pi, plan in enumerate(plans, 1):
        pdf = plan["pdf"]
        ui.info(f"[{pi}/{len(plans)}] {_short(pdf.name)}")
        if plan["oversize"]:
            errors += 1
            ui.error(f"[batch] {_short(pdf.name)}: too large for the model context, skipped")
            continue
        outcome = _assemble_one_paper(plan, batch_out, out_dir)
        if outcome["failed"]:
            errors += 1
            extra = " (partial sum_ saved for eval)" if outcome["truncated"] else ""
            ui.error(f"[batch] {_short(pdf.name)}: incomplete results, re-run to retry{extra}")
        elif outcome["wrote"]:
            done += 1
    return {"done": done, "errors": errors}


def _run_batch(work, out_dir, skipped):
    """Read every paper up front, spooling its artifacts to a temp folder so the
    parent never holds all the text at once, then submit one Message Batch. The
    request set is built by reading one paper's spool file at a time and deleting
    it straight after, so peak memory is one paper's artifacts plus the batch
    payload, not 1000+ papers' extracted text."""
    import shutil
    import tempfile
    from pathlib import Path

    from backends import anthropic_client

    plans_in = _plans(work, out_dir)
    n = len(plans_in)
    if not n:
        ui.step("Done")
        ui.ok(f"0 processed, {skipped} skipped")
        return 0

    spool = Path(tempfile.mkdtemp(prefix="pepa_extract_"))
    done = 0
    try:
        read = _extract_to_spool(plans_in, spool, n)
        spooled, errors = read["spooled"], read["errors"]
        if not spooled:
            ui.step("Done")
            ui.ok(f"0 processed, {skipped} skipped, {errors} failed")
            return 1 if errors else 0

        prepared = _build_batch_requests(spooled, out_dir)
        requests, plans = prepared["requests"], prepared["plans"]

        if not requests:
            done = sum(1 for p in plans if p["wrote"])
            ui.step("Done")
            ui.ok(f"{done} processed, {skipped} skipped, {errors} failed")
            return 1 if errors else 0

        ui.step(f"Submitting {len(requests)} request(s) to the Message Batches API")
        ui.info("most batches finish within ~1h (max 24h)  ·  Ctrl-C cancels the batch")
        batch_out = anthropic_client.run_batch(requests, on_progress=_batch_progress)

        assembled = _assemble_batch(plans, batch_out, out_dir)
        done = assembled["done"]
        errors += assembled["errors"]
    finally:
        shutil.rmtree(spool, ignore_errors=True)

    ui.step("Done")
    ui.ok(f"{done} processed, {skipped} skipped, {errors} failed")
    return 1 if errors else 0


def _batch_progress(status):
    """Print one heartbeat line per poll of the running batch."""
    c = status.request_counts
    ui.info(f"batch {status.processing_status}: {c.succeeded} ok · "
            f"{c.errored} err · {c.processing} processing")


# ---- Serial mode (single paper, or the cloudrun backend) ----
# Live spinner per step, with a one-paper look-ahead so the next paper's local
# stage overlaps the LLM.

def _submit_next(queue, out_dir, ex):
    """Advance to the next paper that needs work and start its extraction.

    Returns:
        The `pdf`, the documents still `todo` for it, and the `future` reading
        it, or None once the queue holds no more papers needing work.
    """
    for pdf, regen in queue:
        todo = _docs_todo(pdf, out_dir, regen)
        if todo:
            return {"pdf": pdf, "todo": todo, "future": ex.submit(_extract_paper, pdf, todo)}
    return None


def _chars_read(read):
    """The spinner's one-line summary for a finished extraction."""
    if not read or read["artifacts"] is None:
        return ""
    return f"{len(read['artifacts']['text']):,} chars"


def _run_serial(sources, out_dir, force, on_existing):
    """One paper at a time, but a single look-ahead worker reads and signals the
    NEXT paper while the current paper's LLM calls are in flight, so the local CPU
    stage overlaps the network wait and the gap between papers closes. Only two
    papers' artifacts are ever live (current + the one prefetched), so peak memory
    stays flat: this is a thread, not extra processes, and cannot over-spawn."""
    from concurrent.futures import ThreadPoolExecutor

    ui.info(f"on existing: {on_existing}  ·  reading the next paper while the current "
            "one runs  ·  Ctrl-C to stop after the current paper.")
    done = errors = stopped = 0
    planned = _serial_jobs(sources, out_dir, force, on_existing)
    queue = iter(planned["jobs"])

    with ThreadPoolExecutor(max_workers=1) as ex:
        pending = _submit_next(queue, out_dir, ex)
        while pending is not None:
            pdf, todo, fut = pending["pdf"], pending["todo"], pending["future"]
            ui.step(pdf.name)
            kept = [d for d in _DOCS if d not in todo]
            for d in kept:
                ui.info(f"kept {d}_ (exists)")
            # Live spinner BEFORE the wait: instant if the look-ahead already read
            # this paper during the previous one's LLM calls, animated (so it never
            # looks hung) while a slow paper (e.g. a scanned PDF being OCR'd) reads.
            try:
                read = _spin("reading + signals", fut.result, _chars_read)
            except Exception as e:
                ui.error(f"{_short(pdf.name)}: {e}")
                errors += 1
                pending = _submit_next(queue, out_dir, ex)
                continue
            # Start the next paper's read now, so it runs while this paper's LLM does.
            nxt = _submit_next(queue, out_dir, ex)
            if read["artifacts"] is None:
                ui.error(f"{_short(pdf.name)}: no extractable text")
                errors += 1
                pending = nxt
                continue
            try:
                _build_docs(pdf, out_dir, todo, read["artifacts"])
                done += 1
            except KeyboardInterrupt:
                ui.warn("stopped (Ctrl-C): finished documents are saved")
                stopped = 1
                break
            except SystemExit:
                raise  # configuration/endpoint errors are fatal for the whole run
            except Exception as e:
                saved = _maybe_log_truncated(out_dir, pdf.name, e)
                extra = f" (partial saved to {saved})" if saved else ""
                ui.error(f"{pdf.name}: {e}{extra}")
                errors += 1
            pending = nxt

    skipped = planned["skipped"]
    ui.step("Done")
    ui.ok(f"{done} processed, {skipped} skipped, {errors} failed"
          + (", stopped early" if stopped else ""))
    return 1 if errors else 0


def _serial_jobs(sources, out_dir, force, on_existing):
    """Decide, for every paper, whether it needs work, applying the skip/overwrite policy.

    Fully-done papers need no extraction, so they are resolved here and never
    handed to the look-ahead: there is no gap to close on a paper that does no work.

    Returns:
        The `jobs` as (pdf, regen) pairs in order, and the count of papers `skipped`.
    """
    jobs = []
    skipped = 0
    for pdf in sources:
        present = [d for d in _DOCS if (out_dir / f"{d}_{paper_stem(pdf.name)}.md").exists()]
        if len(present) == len(_DOCS) and not force:
            if _keep_existing(pdf.name, on_existing):
                ui.info(f"skip {_short(pdf.name)} (all documents exist)")
                skipped += 1
                continue
            jobs.append((pdf, True))   # fully done but the user chose to overwrite
        else:
            jobs.append((pdf, force))
    return {"jobs": jobs, "skipped": skipped}


def _keep_existing(name, policy):
    """Whether to keep a fully-done paper's existing documents.

    policy `skip` keeps them all (no prompt); `overwrite` redoes them; `ask`
    prompts per paper. Off a TTY, `ask` keeps existing so batch runs stay
    resumable. --force overrides this entirely (handled by the caller)."""
    if policy == "skip":
        return True
    if policy == "overwrite":
        return False
    if not sys.stdin.isatty():
        return True
    return not ui.confirm(f"'{name}' already done, overwrite?", default_yes=False)


def _build_docs(pdf, out_dir, todo, artifacts):
    """Build a paper's outstanding documents with a live spinner per step, from
    artifacts the look-ahead worker already extracted. sum_ and para_ are LLM calls
    (run together when both are due); quote_ is deterministic. Mirrors the document
    set and ordering of _build_live, with serial mode's per-step spinners."""
    t0 = time.time()
    builders = _builders(artifacts)
    steps = [d for d in ("sum", "para", "quote") if d in todo]
    for i, d in enumerate(steps, 1):
        ui.info(f"  · {i}/{len(steps)}  {_LABELS[d]}")

    llm_todo = [d for d in ("sum", "para") if d in todo]
    if len(llm_todo) == 2:
        _spin("running LLM calls",
              partial(_write_together, out_dir, pdf.name, builders, llm_todo))
        for d in llm_todo:
            _done_line(_LABELS[d])
    else:
        for d in llm_todo:
            _spin(_LABELS[d],
                  partial(_write_one, out_dir, d, pdf.name, builders[d]), _saved)

    if "quote" in todo:
        _spin(_LABELS["quote"],
              partial(_write_one, out_dir, "quote", pdf.name, builders["quote"]), _saved)

    ui.info(f"done in {time.time() - t0:.0f}s")


# ---- Cost reporting and shared helpers ----

def _preflight_cost_check(work, mode, threshold=COST_CONFIRM_THRESHOLD):
    if not work:
        return
    if config.load('BACKEND') != "anthropic":
        return
    price = config.price_per_mtok()
    if price is None:
        return
    model = config.load('ANTHROPIC_MODEL')
    p_in, p_out = price
    n = len(work)
    total_in = n * 5000
    total_out = n * 2500
    cost = total_in / 1e6 * p_in + total_out / 1e6 * p_out
    if mode == "batch":
        cost *= 0.5
    if cost > threshold:
        ui.warn(f"Estimated cost: ~${cost:.2f}  ({total_in / 1e6:.2f}M in + {total_out / 1e6:.2f}M out · {model})")
        if not ui.confirm("Cost exceeds threshold, proceed?"):
            raise SystemExit("Aborted.")
    else:
        ui.info(f"Est. cost ~${cost:.2f}")


def _reset_usage():
    """Zero the token tally before a run, so the cost estimate covers only it.
    Only the anthropic backend reports usage; cloudrun bills by CPU time."""
    if config.load('BACKEND') == "anthropic":
        from backends import anthropic_client
        anthropic_client.reset_usage()


def _report_cost():
    """Print an estimated cost from the tokens the API actually reported. Batch
    tokens are billed at 50%, so they enter the estimate halved."""
    if config.load('BACKEND') != "anthropic":
        return
    from backends import anthropic_client
    u = anthropic_client.usage_snapshot()
    if not u["calls"]:
        return
    total_in = u["input"] + u["batch_input"]
    total_out = u["output"] + u["batch_output"]
    tokens = f"{total_in:,} in + {total_out:,} out over {u['calls']} calls"
    price = config.price_per_mtok()
    if price is None:
        ui.info(f"LLM usage: {tokens} (no price on file for {config.load('ANTHROPIC_MODEL')})")
        return
    p_in, p_out = price
    cost = (u["input"] / 1e6 * p_in + u["output"] / 1e6 * p_out
            + 0.5 * (u["batch_input"] / 1e6 * p_in + u["batch_output"] / 1e6 * p_out))
    note = "  ·  batch billed at 50%" if (u["batch_input"] or u["batch_output"]) else ""
    ui.info(f"est. cost ~${cost:.2f}  ·  {tokens}{note}  ·  estimate only, verify pricing")


def _fmt(seconds):
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _short(name, width=PAPER_NAME_WIDTH):
    truncated = name[:width] + "..." if len(name) > width else name
    return truncated.ljust(width + 3)


def _log_truncated(out_dir, source_name, partial):
    """Save a cut-off sum_ body under output/_truncated/ for eval and return its
    path. No sum_ file is written, so the paper stays a failure and a re-run
    regenerates it from scratch; this copy only preserves what was produced."""
    from pathlib import Path
    dest = Path(out_dir) / "_truncated" / f"sum_{paper_stem(source_name)}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"{source_name}\n\n{(partial or '').strip()}\n", encoding="utf-8")
    return dest


def _maybe_log_truncated(out_dir, source_name, err):
    """When a build failure carries a truncated partial body, save it for eval and
    return the path; otherwise None, so a failure handler can add the note without
    knowing which document truncated."""
    partial = getattr(err, "partial", None)
    if partial is None:
        return None
    return _log_truncated(out_dir, source_name, partial)


def _done_line(label, summary="saved"):
    """Print a ✓ completion line matching StepSpinner.done() format (no colour)."""
    safe = summary.encode("ascii", "replace").decode("ascii")
    suffix = f"  {safe}" if safe else ""
    if sys.stdout.isatty():
        sys.stdout.write(f"  {_CHECK}  {label:<{_LABEL_W}}{suffix}\n")
        sys.stdout.flush()
    else:
        print(f"  {label}... {safe}")


def _spin(label, fn, summary=lambda r: ""):
    """Run fn() under a spinner, always closing it, even if fn raises."""
    sp = StepSpinner(label)
    sp.start()
    try:
        result = fn()
    except BaseException:
        sp.done("failed")
        raise
    sp.done(summary(result))
    return result
