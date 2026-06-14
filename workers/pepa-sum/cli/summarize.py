"""The main command: turn every PDF in input/ into three structured documents.

Per paper: read text (OCR fallback, references stripped) -> extract deterministic
signals + passages -> build sum_ (structured brief), para_ (paragraph rundown),
and quote_ (verified verbatim quotes) in output/. A paper already processed is
left alone: with --force it is redone silently; interactively the run asks
before overwriting.
"""
import sys
import time

import config
from cli import ui
from cli.progress import StepSpinner, _CHECK, _LABEL_W

_DOCS = ("sum", "para", "quote")
_LABELS = {
    "sum": "sum_  structured brief",
    "para": "para_ paragraph rundown",
    "quote": "quote_ salient quotes",
}


def run(input_dir=None, output_dir=None, force=False):
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

    ui.header("pepa-sum — summarising papers")
    ui.info(f"{len(pdfs)} PDF(s) in {in_dir}")
    ui.info(f"backend: {config.backend()}  ·  paragraph rundown: {config.para_method()}")
    ui.info(f"on existing: {config.on_existing()}  ·  Ctrl-C to stop after the current step.")

    on_existing = config.on_existing()
    done = errors = skipped = stopped = 0
    for pdf in pdfs:
        present = [d for d in _DOCS if (out_dir / f"{d}_{pdf.stem}.md").exists()]
        regen = force
        if len(present) == len(_DOCS) and not force:
            if not _keep_existing(pdf.name, on_existing):
                regen = True
            else:
                ui.info(f"skip {_short(pdf.name)} (all documents exist)")
                skipped += 1
                continue
        try:
            _summarise_one(pdf, out_dir, force=regen)
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

    ui.step("Done")
    ui.ok(f"{done} processed, {skipped} skipped, {errors} failed"
          + (f", {len(pdfs) - done - skipped - errors} not reached" if stopped else ""))
    return 1 if errors else 0


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


def _summarise_one(pdf, out_dir, force=False):
    from extract import read_pdf, extract_signals, select_passages
    import documents
    from render import write_doc

    ui.step(pdf.name)

    todo = [d for d in _DOCS if force or not (out_dir / f"{d}_{pdf.stem}.md").exists()]
    for d in _DOCS:
        if d not in todo:
            ui.info(f"kept {d}_ (exists)")
    if not todo:
        return

    t0 = time.time()
    text = _spin("reading + OCR", lambda: read_pdf(pdf), lambda t: f"{len(t):,} chars")
    if not text:
        raise RuntimeError("no extractable text")

    def _local():
        signals = extract_signals(text)
        return signals, select_passages(text, signals)

    signals, passages = _spin(
        "local signals", _local,
        lambda r: f"{len(r[0]['noun_phrases'])} phrases, {len(r[1])} passages",
    )

    builders = {
        "sum": lambda: documents.build_summary(text, signals, passages),
        "para": lambda: documents.build_rundown(text),
        "quote": lambda: documents.build_quotes(text, signals),
    }

    llm_todo = [d for d in ("sum", "para") if d in todo]

    if len(llm_todo) == 2:
        from concurrent.futures import ThreadPoolExecutor

        def _run_both():
            def _build(d):
                write_doc(out_dir, d, pdf.name, builders[d]())
            with ThreadPoolExecutor(max_workers=2) as ex:
                futures = [ex.submit(_build, d) for d in llm_todo]
                for f in futures:
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


def _short(name, width=50):
    return name if len(name) <= width else name[:width] + "..."


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
