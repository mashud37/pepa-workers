"""The main command: turn every PDF in input/ into three structured documents.

Per paper: read text (OCR fallback, references stripped) -> extract deterministic
signals + passages -> build sum_ (structured brief), para_ (paragraph rundown),
and quote_ (verified verbatim quotes) in output/. A paper already processed is
left alone: with --force it is redone silently; interactively the run asks
before overwriting.

The run picks an execution mode by estimated wall-clock (config.mode(), default
`auto`):
  - serial   — one paper at a time with a live per-step spinner (single paper,
               or the cloudrun backend).
  - parallel — streamed in chunks of LOCAL_BATCH papers: each chunk's local CPU
               stage (PDF + spaCy + BM25) runs across processes to escape the
               GIL, then its LLM calls run across a thread pool (bounded by the
               client's global concurrency governor) before the next chunk is
               read — so peak memory stays flat regardless of volume.
  - batch    — the same prompts go to the Anthropic Message Batches API: ~50%
               cheaper and far higher throughput, at the cost of asynchronous
               (typically up to ~1h) turnaround. The local stage spools each
               paper's artifacts to a temp folder, so the parent process never
               holds every paper's text at once. Best for large volumes.

All three modes build identical documents: same model, system prompts, prompt
builders, temperature, and post-processing — only the transport differs.
"""
import sys
import time

import config
from cli import ui
from cli.progress import StepSpinner, ProgressSpinner, _CHECK, _LABEL_W

_DOCS = ("sum", "para", "quote")
_LABELS = {
    "sum": "sum_  structured brief",
    "para": "para_ paragraph rundown",
    "quote": "quote_ salient quotes",
}

# PDFs that yield fewer characters than this have no usable text layer and are
# skipped — they produce meaningless LLM output rather than a real summary.
MIN_TEXT_CHARS = 5000

# spaCy/numpy (thinc, blis, MKL/OpenBLAS) each default to one compute thread per
# core. The local stage already parallelises across papers with a process pool,
# so every worker must run single-threaded — otherwise N workers spawn N*cores
# threads that thrash the CPU instead of parsing. Pinning these to 1 is the
# difference between seconds and minutes per paper; it changes no output.
_THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def _pin_threads():
    import os
    for var in _THREAD_ENV:
        os.environ[var] = "1"


def run(input_dir=None, output_dir=None, force=False, mode=None):
    _pin_threads()  # parent sets them so spawned workers inherit before numpy imports
    try:
        from extract import read_pdf, extract_signals, select_passages  # noqa: F401
    except ImportError as e:
        raise SystemExit(f"Missing dependency ({e.name}). Run: pip install -r requirements.txt")

    in_dir = (input_dir or config.INPUT_DIR)
    out_dir = (output_dir or config.OUTPUT_DIR)
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(in_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in {in_dir}. Drop papers there and re-run.")

    on_existing = config.on_existing()
    ui.header("pepa-sum — summarising papers")
    ui.info(f"{len(pdfs)} PDF(s) in {in_dir}")
    ui.info(f"backend: {config.backend()}  ·  paragraph rundown: {config.para_method()}")

    work, skipped = _plan_work(pdfs, out_dir, force, on_existing)
    if not work:
        ui.step("Done")
        ui.ok(f"0 processed, {skipped} skipped")
        return 0

    chosen = _select_mode(len(work), mode)
    _show_plan(len(work), chosen, mode)
    _preflight_cost_check(work, chosen)
    _reset_usage()

    if chosen == "serial":
        code = _run_serial(pdfs, out_dir, force, on_existing)
    elif chosen == "batch":
        code = _run_batch(work, out_dir, skipped)
    else:
        code = _run_parallel(work, out_dir, skipped)
    _report_cost()
    return code


def _plan_work(pdfs, out_dir, force, on_existing):
    """Papers to (re)process, resolved without prompting — `ask` is treated as
    `skip` here, as it already is off a TTY. Each entry is (pdf, regen); regen
    True redoes all three documents, False fills only the missing ones."""
    work, skipped = [], 0
    for pdf in pdfs:
        present = [d for d in _DOCS if (out_dir / f"{d}_{pdf.stem}.md").exists()]
        if force:
            work.append((pdf, True))
        elif len(present) == len(_DOCS):
            if on_existing == "overwrite":
                work.append((pdf, True))
            else:
                skipped += 1
        else:
            work.append((pdf, False))
    return work, skipped


def _docs_todo(pdf, out_dir, regen):
    """Which of the three documents this paper still needs."""
    return [d for d in _DOCS if regen or not (out_dir / f"{d}_{pdf.stem}.md").exists()]


# ---------------------------------------------------------------------------
# Mode selection (by estimated wall-clock time)
# ---------------------------------------------------------------------------

def _select_mode(n, override=None):
    """Resolve the execution mode. cloudrun is always serial; an explicit mode
    (flag or config) is honoured; otherwise `auto` picks the fastest estimate."""
    wanted = (override or config.mode() or "auto").lower()
    if config.backend() == "cloudrun":
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
    if config.backend() == "cloudrun":
        ui.info("cloudrun backend — serial (single scale-to-zero instance)")
        return
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


# ---------------------------------------------------------------------------
# Local extraction stage (CPU-bound; runs across processes to escape the GIL)
# ---------------------------------------------------------------------------

def _plans(work, out_dir):
    """(pdf, todo) for every paper that still needs at least one document."""
    plans = [(pdf, _docs_todo(pdf, out_dir, regen)) for pdf, regen in work]
    return [(pdf, todo) for pdf, todo in plans if todo]


def _extract_paper(pdf, todo):
    """Worker: read + signal-extract one paper, returning the artifacts inline.
    Used for parallel mode, where the pipeline keeps only a bounded look-ahead
    window of papers in memory at once.
    Returns (pdf, todo, data) with data = (text, signals, passages), or None."""
    from extract import read_pdf, extract_signals, select_passages
    text = read_pdf(pdf)
    if not text or len(text) < MIN_TEXT_CHARS:
        return pdf, todo, None
    signals = extract_signals(text)
    passages = select_passages(text, signals)
    return pdf, todo, (text, signals, passages)


def _extract_to_disk(pdf, todo, idx, spool):
    """Worker: read + signal-extract one paper and pickle (text, signals,
    passages) into `spool/idx.pkl`, returning the path (None for no text).
    Spooling inside the child keeps the heavy artifacts off the parent process —
    for batch mode, where every paper is read up front before any LLM work."""
    import pickle
    from extract import read_pdf, extract_signals, select_passages
    text = read_pdf(pdf)
    if not text or len(text) < MIN_TEXT_CHARS:
        return pdf, todo, None
    signals = extract_signals(text)
    passages = select_passages(text, signals)
    path = spool / f"{idx}.pkl"
    with open(path, "wb") as f:
        pickle.dump((text, signals, passages), f, protocol=pickle.HIGHEST_PROTOCOL)
    return pdf, todo, path


def _extract_to_spool(plans, spool, n):
    """Read every paper across processes, each worker pickling its artifacts into
    `spool`; the parent collects only lightweight (pdf, todo, path) handles, so
    peak memory stays flat regardless of volume. Returns (spooled, errors)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    workers = min(config.local_workers(), n)
    ui.step(f"Reading {n} paper(s) locally — PDF + spaCy signals, {workers} process(es)")
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
                    _, todo, path = fut.result()
                except Exception as e:
                    failures.append(f"[read] {_short(pdf.name)}: {e}")
                else:
                    if path is None:
                        failures.append(f"[read] {_short(pdf.name)}: no extractable text")
                    else:
                        spooled.append((pdf, todo, path))
                sp.advance()
    finally:
        sp.done(f"{len(spooled)}/{n} read"
                + (f", {len(failures)} failed" if failures else ""))
    for msg in failures:  # printed after the spinner closes, so the line stays clean
        ui.error(msg)
    return spooled, len(failures)


# ---------------------------------------------------------------------------
# Parallel mode (extract across processes, then build across threads)
# ---------------------------------------------------------------------------

def _build_live(pdf, out_dir, todo, text, signals, passages):
    """Build this paper's outstanding documents via live LLM calls. Mirrors the
    document set and ordering of _summarise_one, without the spinner."""
    from concurrent.futures import ThreadPoolExecutor
    import documents
    from render import write_doc

    builders = {
        "sum": lambda: documents.build_summary(text, signals, passages),
        "para": lambda: documents.build_rundown(text),
        "quote": lambda: documents.build_quotes(text, signals),
    }
    llm_todo = [d for d in ("sum", "para") if d in todo]
    if len(llm_todo) == 2:
        def _build(d):
            write_doc(out_dir, d, pdf.name, builders[d]())
        with ThreadPoolExecutor(max_workers=2) as ex:
            for f in [ex.submit(_build, d) for d in llm_todo]:
                f.result()
    else:
        for d in llm_todo:
            write_doc(out_dir, d, pdf.name, builders[d]())
    if "quote" in todo:
        write_doc(out_dir, "quote", pdf.name, builders["quote"]())


def _run_parallel(work, out_dir, skipped):
    """Pipeline the two stages: keep the local extraction process-pool running a
    bounded look-ahead window *ahead* of the LLM thread-pool, so the next papers'
    spaCy/BM25 work proceeds on the CPU while the current papers' LLM calls wait
    on the network. The window (LOCAL_BATCH) caps how many extracted papers are
    held in memory at once, so peak memory stays flat regardless of volume."""
    from concurrent.futures import (ProcessPoolExecutor, ThreadPoolExecutor,
                                    wait, FIRST_COMPLETED)

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

    done = errors = 0
    pending = list(plans)            # not yet submitted for extraction
    extract_futs, build_futs = {}, {}    # future -> (pdf, todo)

    def refill(px):
        # Keep extraction + building together within the look-ahead window, so at
        # most `window` papers' artifacts are ever live in this process.
        while pending and (len(extract_futs) + len(build_futs)) < window:
            pdf, todo = pending.pop(0)
            extract_futs[px.submit(_extract_paper, pdf, todo)] = (pdf, todo)

    # Live [i/N] + ETA, lit BEFORE the first blocking wait, advancing once per
    # paper (on a read failure, or when its build finishes) so the screen is never
    # dead while the first papers are still being read/OCR'd.
    sp = ProgressSpinner("summarising", n)
    sp.start()
    interrupted = False
    with ProcessPoolExecutor(max_workers=local_w, initializer=_pin_threads) as px, \
         ThreadPoolExecutor(max_workers=paper_w) as tx:
        refill(px)
        try:
            while extract_futs or build_futs:
                ready, _ = wait(set(extract_futs) | set(build_futs),
                                return_when=FIRST_COMPLETED)
                for fut in ready:
                    if fut in extract_futs:
                        pdf, _todo = extract_futs.pop(fut)
                        try:
                            _, todo, data = fut.result()
                        except Exception as e:
                            errors += 1
                            sp.log(ui.line("error", f"{_short(pdf.name)} read failed: {e}"))
                            sp.advance()
                        else:
                            if data is None:
                                errors += 1
                                sp.log(ui.line("warn", f"{_short(pdf.name)} no extractable text"))
                                sp.advance()
                            else:
                                build_futs[tx.submit(_build_live, pdf, out_dir,
                                                     todo, *data)] = (pdf, todo)
                    else:
                        pdf, todo = build_futs.pop(fut)
                        try:
                            fut.result()
                            done += 1
                            sp.log(ui.line("ok", f"{_short(pdf.name)} {_built(todo)}"))
                        except Exception as e:  # per-paper failure: log and continue
                            errors += 1
                            sp.log(ui.line("error", f"{_short(pdf.name)} build failed: {e}"))
                        sp.advance()
                refill(px)
        except KeyboardInterrupt:
            interrupted = True
            pending.clear()
            for f in list(extract_futs) + list(build_futs):
                f.cancel()

    sp.done(f"{done}/{n} built" + (f", {errors} failed" if errors else ""))
    if interrupted:
        ui.warn("stopped — finished papers are saved; the rest were cancelled")

    ui.step("Done")
    ui.ok(f"{done} processed, {skipped} skipped, {errors} failed")
    return 1 if errors else 0


# ---------------------------------------------------------------------------
# Batch mode (Anthropic Message Batches API)
# ---------------------------------------------------------------------------

def _run_batch(work, out_dir, skipped):
    """Read every paper up front, spooling its artifacts to a temp folder so the
    parent never holds all the text at once, then submit one Message Batch. The
    request set is built by reading one paper's spool file at a time and deleting
    it straight after, so peak memory is one paper's artifacts plus the batch
    payload — not 1000+ papers' extracted text."""
    import os
    import pickle
    import shutil
    import tempfile
    from pathlib import Path

    import documents
    from documents import rundown, summary
    from backends import SUMMARY_SYSTEM, build_summary_prompt
    from backends import anthropic_client
    from render import write_doc

    plans_in = _plans(work, out_dir)
    n = len(plans_in)
    if not n:
        ui.step("Done")
        ui.ok(f"0 processed, {skipped} skipped")
        return 0

    spool = Path(tempfile.mkdtemp(prefix="pepa_extract_"))
    done = 0
    try:
        spooled, errors = _extract_to_spool(plans_in, spool, n)
        if not spooled:
            ui.step("Done")
            ui.ok(f"0 processed, {skipped} skipped, {errors} failed")
            return 1 if errors else 0

        # Build the request set and a per-paper plan, loading one paper's spooled
        # artifacts at a time and freeing them straight after. Deterministic
        # documents (quotes, extractive rundowns) need no LLM, so write them now.
        para_llm = config.para_method() == "llm"
        ns = len(spooled)
        ui.step(f"Building batch requests for {ns} paper(s)")
        requests, plans = [], []
        for idx, (pdf, todo, path) in enumerate(spooled):
            ui.info(f"[{idx + 1}/{ns}] {_short(pdf.name)}")
            with open(path, "rb") as f:
                text, signals, passages = pickle.load(f)
            plan = {"pdf": pdf, "sum": None, "para": None, "wrote": False, "oversize": False}
            if "quote" in todo:
                write_doc(out_dir, "quote", pdf.name, documents.build_quotes(text, signals))
                plan["wrote"] = True
            if "sum" in todo:
                sum_prompt = build_summary_prompt(text, signals, passages)
                # A batch request too large for the context window would fail
                # silently and re-fail on every re-run; catch it here instead.
                if anthropic_client.would_overflow(SUMMARY_SYSTEM, sum_prompt, summary.MAX_TOKENS):
                    plan["oversize"] = True
                else:
                    cid = f"p{idx}s"
                    requests.append({
                        "custom_id": cid,
                        "system": SUMMARY_SYSTEM,
                        "prompt": sum_prompt,
                        "max_tokens": summary.MAX_TOKENS,
                    })
                    plan["sum"] = cid
            if "para" in todo:
                if not para_llm:
                    write_doc(out_dir, "para", pdf.name, documents.build_rundown(text))
                    plan["wrote"] = True
                else:
                    chunks = rundown.chunk_paragraphs(text)
                    if not chunks:
                        write_doc(out_dir, "para", pdf.name, rundown.NO_PARAGRAPHS)
                        plan["wrote"] = True
                    else:
                        cids = []
                        for j, chunk in enumerate(chunks):
                            cid = f"p{idx}c{j}"
                            system, prompt, max_tokens = rundown.chunk_request(chunk)
                            requests.append({"custom_id": cid, "system": system,
                                             "prompt": prompt, "max_tokens": max_tokens})
                            cids.append(cid)
                        plan["para"] = cids
            plans.append(plan)
            os.remove(path)  # artifacts consumed; keep the spool small too

        if not requests:
            done = sum(1 for p in plans if p["wrote"])
            ui.step("Done")
            ui.ok(f"{done} processed, {skipped} skipped, {errors} failed")
            return 1 if errors else 0

        ui.step(f"Submitting {len(requests)} request(s) to the Message Batches API")
        ui.info("most batches finish within ~1h (max 24h)  ·  Ctrl-C cancels the batch")
        results = anthropic_client.run_batch(requests, on_progress=_batch_progress())

        # Reassemble: a paper is done only if every request it expected came back.
        ui.step(f"Assembling results for {len(plans)} paper(s)")
        for pi, plan in enumerate(plans, 1):
            pdf = plan["pdf"]
            ui.info(f"[{pi}/{len(plans)}] {_short(pdf.name)}")
            if plan["oversize"]:
                errors += 1
                ui.error(f"[batch] {_short(pdf.name)}: too large for the model context — skipped")
                continue
            wrote = plan["wrote"]
            failed = False
            if plan["sum"] is not None:
                text = results.get(plan["sum"])
                if text:
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
            if failed:
                errors += 1
                ui.error(f"[batch] {_short(pdf.name)}: incomplete results — re-run to retry")
            elif wrote:
                done += 1
    finally:
        shutil.rmtree(spool, ignore_errors=True)

    ui.step("Done")
    ui.ok(f"{done} processed, {skipped} skipped, {errors} failed")
    return 1 if errors else 0


def _batch_progress():
    """A callback that prints one heartbeat line per poll of the running batch."""
    def cb(status):
        c = status.request_counts
        ui.info(f"batch {status.processing_status}: {c.succeeded} ok · "
                f"{c.errored} err · {c.processing} processing")
    return cb


# ---------------------------------------------------------------------------
# Serial mode (single paper, or the cloudrun backend) — live spinner per step,
# with a one-paper look-ahead so the next paper's local stage overlaps the LLM.
# ---------------------------------------------------------------------------

def _run_serial(pdfs, out_dir, force, on_existing):
    """One paper at a time, but a single look-ahead worker reads and signals the
    NEXT paper while the current paper's LLM calls are in flight, so the local CPU
    stage overlaps the network wait and the gap between papers closes. Only two
    papers' artifacts are ever live (current + the one prefetched), so peak memory
    stays flat — this is a thread, not extra processes, and cannot over-spawn."""
    from concurrent.futures import ThreadPoolExecutor

    ui.info(f"on existing: {on_existing}  ·  reading the next paper while the current "
            "one runs  ·  Ctrl-C to stop after the current paper.")
    counters = {"skipped": 0}
    done = errors = stopped = 0
    jobs = _serial_jobs(pdfs, out_dir, force, on_existing, counters)

    def submit_next(ex):
        """Advance to the next paper that needs work and start its extraction."""
        for pdf, regen in jobs:
            todo = _docs_todo(pdf, out_dir, regen)
            if todo:
                return pdf, regen, todo, ex.submit(_extract_paper, pdf, todo)
        return None

    with ThreadPoolExecutor(max_workers=1) as ex:
        pending = submit_next(ex)
        while pending is not None:
            pdf, regen, todo, fut = pending
            ui.step(pdf.name)
            for d in _DOCS:
                if d not in todo:
                    ui.info(f"kept {d}_ (exists)")
            # Live spinner BEFORE the wait: instant if the look-ahead already read
            # this paper during the previous one's LLM calls, animated (so it never
            # looks hung) while a slow paper — e.g. a scanned PDF being OCR'd — reads.
            try:
                data = _spin("reading + signals", lambda: fut.result()[2],
                             lambda d: f"{len(d[0]):,} chars" if d else "")
            except Exception as e:
                ui.error(f"{_short(pdf.name)}: {e}")
                errors += 1
                pending = submit_next(ex)
                continue
            # Start the next paper's read now, so it runs while this paper's LLM does.
            nxt = submit_next(ex)
            if data is None:
                ui.error(f"{_short(pdf.name)}: no extractable text")
                errors += 1
                pending = nxt
                continue
            try:
                _build_docs(pdf, out_dir, todo, *data)
                done += 1
            except KeyboardInterrupt:
                ui.warn("stopped (Ctrl-C) — finished documents are saved")
                stopped = 1
                break
            except SystemExit:
                raise  # configuration/endpoint errors are fatal for the whole run
            except Exception as e:
                ui.error(f"{pdf.name}: {e}")
                errors += 1
            pending = nxt

    skipped = counters["skipped"]
    ui.step("Done")
    ui.ok(f"{done} processed, {skipped} skipped, {errors} failed"
          + (", stopped early" if stopped else ""))
    return 1 if errors else 0


def _serial_jobs(pdfs, out_dir, force, on_existing, counters):
    """Yield (pdf, regen) for each paper that needs work, in order, applying the
    skip/overwrite decision (and the interactive prompt) inline. Fully-done papers
    need no extraction, so they are resolved here and never handed to the
    look-ahead — there is no gap to close on a paper that does no work."""
    for pdf in pdfs:
        present = [d for d in _DOCS if (out_dir / f"{d}_{pdf.stem}.md").exists()]
        if len(present) == len(_DOCS) and not force:
            if _keep_existing(pdf.name, on_existing):
                ui.info(f"skip {_short(pdf.name)} (all documents exist)")
                counters["skipped"] += 1
                continue
            yield pdf, True            # fully done but the user chose to overwrite
        else:
            yield pdf, force


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
    return not ui.confirm(f"'{name}' already done — overwrite?", default_yes=False)


def _build_docs(pdf, out_dir, todo, text, signals, passages):
    """Build a paper's outstanding documents with a live spinner per step, from
    artifacts the look-ahead worker already extracted. sum_ and para_ are LLM calls
    (run together when both are due); quote_ is deterministic. Mirrors the document
    set and ordering of _build_live, with serial mode's per-step spinners."""
    import documents
    from render import write_doc

    t0 = time.time()
    builders = {
        "sum": lambda: documents.build_summary(text, signals, passages),
        "para": lambda: documents.build_rundown(text),
        "quote": lambda: documents.build_quotes(text, signals),
    }

    steps = [d for d in ("sum", "para", "quote") if d in todo]
    for i, d in enumerate(steps, 1):
        ui.info(f"  · {i}/{len(steps)}  {_LABELS[d]}")

    llm_todo = [d for d in ("sum", "para") if d in todo]

    if len(llm_todo) == 2:
        from concurrent.futures import ThreadPoolExecutor

        def _run_both():
            def _build(d):
                write_doc(out_dir, d, pdf.name, builders[d]())
            with ThreadPoolExecutor(max_workers=2) as ex:
                for f in [ex.submit(_build, d) for d in llm_todo]:
                    f.result()

        _spin("running LLM calls", _run_both)
        for d in llm_todo:
            _done_line(_LABELS[d])
    else:
        for d in llm_todo:
            def _build_and_write(d=d):
                write_doc(out_dir, d, pdf.name, builders[d]())
            _spin(_LABELS[d], _build_and_write, lambda _: "saved")

    if "quote" in todo:
        _spin(_LABELS["quote"],
              lambda: write_doc(out_dir, "quote", pdf.name, builders["quote"]()),
              lambda _: "saved")

    ui.info(f"done in {time.time() - t0:.0f}s")


# ---------------------------------------------------------------------------
# Cost reporting and shared helpers
# ---------------------------------------------------------------------------

def _preflight_cost_check(work, mode, threshold=10.0):
    if not work:
        return
    if config.backend() != "anthropic":
        return
    price = config.price_per_mtok()
    if price is None:
        return
    model = config.anthropic_model()
    p_in, p_out = price
    n = len(work)
    total_in = n * 5000
    total_out = n * 2500
    cost = total_in / 1e6 * p_in + total_out / 1e6 * p_out
    if mode == "batch":
        cost *= 0.5
    if cost > threshold:
        ui.warn(f"Estimated cost: ~${cost:.2f}  ({total_in / 1e6:.2f}M in + {total_out / 1e6:.2f}M out · {model})")
        if not ui.confirm("Cost exceeds threshold — proceed?"):
            raise SystemExit("Aborted.")
    else:
        ui.info(f"Est. cost ~${cost:.2f}")


def _reset_usage():
    """Zero the token tally before a run, so the cost estimate covers only it.
    Only the anthropic backend reports usage; cloudrun bills by CPU time."""
    if config.backend() == "anthropic":
        from backends import anthropic_client
        anthropic_client.reset_usage()


def _report_cost():
    """Print an estimated cost from the tokens the API actually reported. Batch
    tokens are billed at 50%, so they enter the estimate halved."""
    if config.backend() != "anthropic":
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
        ui.info(f"LLM usage: {tokens} (no price on file for {config.anthropic_model()})")
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


def _short(name, width=50):
    truncated = name[:width] + "..." if len(name) > width else name
    return truncated.ljust(width + 3)


def _built(todo):
    """Compact note of which documents a paper produced, e.g. 'sum_ para_ quote_'."""
    return " ".join(f"{d}_" for d in todo)


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
    """Run fn() under a spinner, always closing it — even if fn raises."""
    sp = StepSpinner(label)
    sp.start()
    try:
        result = fn()
    except BaseException:
        sp.done("failed")
        raise
    sp.done(summary(result))
    return result
