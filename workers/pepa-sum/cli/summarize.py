"""The main command: turn every PDF in input/ into a structured summary.

Per paper: read text (OCR fallback) -> extract deterministic signals -> retrieve
the information-rich passages -> build the prompt -> call the Cloud Run model ->
write output/<name>.md. A paper that already has a summary is left alone: with
--force it is redone silently; interactively the run asks before overwriting.
"""
import sys

import config
from cli import ui
from cli.progress import StepSpinner


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

    done = errors = skipped = 0
    for pdf in pdfs:
        if (out_dir / (pdf.stem + ".md")).exists() and not force:
            if not _should_overwrite(pdf.name):
                ui.info(f"skip {pdf.name} (kept existing summary)")
                skipped += 1
                continue
        try:
            _summarise_one(pdf, out_dir)
            done += 1
        except SystemExit:
            raise  # configuration/endpoint errors are fatal for the whole run
        except Exception as e:
            ui.error(f"{pdf.name}: {e}")
            errors += 1

    ui.step("Done")
    ui.ok(f"{done} summarised, {skipped} skipped, {errors} failed")
    return 1 if errors else 0


def _should_overwrite(name):
    """Ask before re-summarising a paper that already has output. Off a TTY
    (piped/scripted) keep the existing file so batch runs stay resumable; use
    --force to overwrite without prompting."""
    if not sys.stdin.isatty():
        return False
    return ui.confirm(f"'{name}' already summarised — overwrite?", default_yes=False)


def _summarise_one(pdf, out_dir):
    from extract import read_pdf, extract_signals, select_passages
    from backends import build_prompt, SYSTEM, summarize
    from render import write_summary

    ui.step(pdf.name)

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

    summary = _spin(
        "summarising (cloud)",
        lambda: summarize(SYSTEM, build_prompt(text, signals, passages)),
    )

    out_path = write_summary(out_dir, pdf.name, summary)
    ui.ok(f"wrote {out_path.name}")


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
