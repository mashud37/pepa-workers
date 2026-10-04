"""CLI layer for the extract pipeline: categorise → straight → books → OCR."""
import functools
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from extract import categorise, marks, workers

from . import items, ui

OCR_LOG_EVERY = 25


def _print_plan(src: Path, out_dir: Path, cfg: dict) -> None:
    """The four phases and the folders they use, printed before any phase starts."""
    where = str(src.resolve())
    if cfg["scan_subfolders"]:
        where += "  (including sub-folders)"
    ui.step("Plan")
    ui.info("Step 1/4: Categorise PDFs")
    ui.info("Step 2/4: Extract straight documents")
    ui.info("Step 3/4: Extract books (with chapter splitting)")
    ui.info("Step 4/4: Extract scanned PDFs (OCR)")
    ui.info(f"Input:    {where}")
    ui.info(f"Output:   {out_dir.resolve()}")
    ui.info(f"Workers:  {cfg['workers']}")


def run(cfg: dict, file: str | None = None, force: bool = False) -> None:
    src = Path(cfg["input_folder"])
    out_dir = Path(cfg["output_folder"]) / "text"

    if not src.is_dir():
        raise SystemExit(f"Input folder not found: {src}")

    if cfg["scan_subfolders"]:
        pdfs = sorted(src.rglob("*.pdf"))
    else:
        pdfs = sorted(src.glob("*.pdf"))
    excluded = marks.excluded_names()
    pdfs = [p for p in pdfs if p.name not in excluded]
    only = marks.only_names()
    if only is not None:
        pdfs = [p for p in pdfs if p.name in only]
    if file:
        pdfs = [p for p in pdfs if p.name == file]
    if not pdfs:
        raise SystemExit(f"No PDFs to prepare in {src}")

    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = dict(cfg, force=force)

    _print_plan(src, out_dir, cfg)

    scanned = _categorise_phase(pdfs, out_dir, cfg)
    groups = scanned["groups"]
    skipped = scanned["skipped"]
    unreadable = scanned["unreadable"]

    n_straight = len(groups["straight"])
    n_book = len(groups["book"])
    n_ocr = len(groups["ocr"])
    ui.ok(
        f"{n_straight} straight  {n_book} book  {n_ocr} OCR"
        + (f"  ({skipped} already done)" if skipped else "")
        + (f"  ({unreadable} unreadable)" if unreadable else "")
    )

    todo = n_straight + n_book + n_ocr
    if not todo:
        ui.info("Nothing to extract.")
        return

    items.announce("total", todo)
    # Phases 2-4
    warns = _run_phase({"step_label": "Step 2/4", "display": "straight", "route": "straight"},
                        groups["straight"], out_dir, cfg)
    warns += _run_phase({"step_label": "Step 3/4", "display": "books", "route": "book"},
                         groups["book"], out_dir, cfg)
    # OCR parallelises pages inside each file; run files serially to avoid
    # oversubscribing the CPU with nested pools, and report page progress per file.
    warns += _run_ocr_phase("Step 4/4", groups["ocr"], out_dir, cfg)

    ui.step("Done")
    ui.ok(f"{todo} file(s) processed → {out_dir.resolve()}")
    if warns:
        ui.warn(f"{len(warns)} file(s) need a look:")
        for name, w in warns:
            ui.warn(f"  {name}: {w}")


def _clear_outputs(out_dir: Path, stem: str) -> None:
    """Delete a PDF's earlier output, one file or numbered chapter files, so it is prepared again."""
    whole = f"text_{stem}.md"
    for old in out_dir.glob("text_*.md"):
        number = old.name[len(f"text_{stem}_"):-len(".md")]
        chapter = old.name.startswith(f"text_{stem}_") and number.isdigit()
        if old.name == whole or chapter:
            old.unlink()


def _categorise_phase(pdfs: list, out_dir: Path, cfg: dict) -> dict:
    """Scan every PDF not already extracted and sort it into a route group.

    Returns:
        {"groups": {"straight", "book", "ocr"} lists of paths, "skipped": already-done
        count, "unreadable": unreadable count}.
    """
    existing = categorise.scan_existing(out_dir)
    groups: dict = {"straight": [], "book": [], "ocr": []}
    skipped = unreadable = 0
    n_workers = max(1, cfg.get("workers", 4))

    to_scan = []
    for p in pdfs:
        if categorise.any_output(existing, p.stem) and not cfg["force"]:
            skipped += 1
        else:
            to_scan.append(p)

    # Phase 1: categorise, pre-filter before opening any PDF
    ui.step(f"Step 1/4: Categorise  [{len(to_scan)} to scan  {skipped} already done]")

    try:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(categorise.scan_one, p): p for p in to_scan}
            for i, fut in enumerate(as_completed(futures), 1):
                path = futures[fut]
                ui.info(f"[{i}/{len(to_scan)}] {path.name}")
                scan = fut.result()
                if scan is None:
                    ui.warn("  unreadable, skipping")
                    unreadable += 1
                    continue
                pages, fraction = scan["pages"], scan["fraction"]
                file_route = categorise.route(pages, fraction, cfg)
                if file_route == "straight" and marks.marked_starts(path.stem):
                    file_route = "book"
                groups[file_route].append(path)
    except KeyboardInterrupt:
        raise SystemExit("\nInterrupted.")

    return {"groups": groups, "skipped": skipped, "unreadable": unreadable}


def _run_phase(phase: dict, files: list, out_dir: Path, cfg: dict,
               file_workers: int | None = None) -> list:
    n = len(files)
    ui.step(f"{phase['step_label']}: Extract {phase['display']}  [{n} file(s)]")
    if not files:
        ui.info("Nothing to do, skipped")
        return []

    handler = workers.HANDLERS[phase["route"]]
    n_workers = file_workers or max(1, cfg.get("workers", 4))
    warns: list = []

    try:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = {}
            for position, path in enumerate(files, 1):
                futures[pool.submit(_extract_one, handler, path, out_dir, cfg, f"[{position}/{n}]")] = path
            for fut in as_completed(futures):
                path = futures[fut]
                try:
                    outcome = fut.result()
                    result, warnings = outcome["result"], outcome["warnings"]
                    ui.ok(f"{path.name}: {result}")
                    items.announce("ok", path.name, result)
                    for w in warnings:
                        ui.warn(f"    {w}")
                        warns.append((path.name, w))
                except Exception as e:
                    ui.error(f"{path.name}: {e}")
                    items.announce("failed", path.name, str(e))
    except KeyboardInterrupt:
        raise SystemExit("\nInterrupted.")
    return warns


def _extract_one(handler, path, out_dir, cfg, counter):
    """Announce a file the moment a worker picks it up, then extract it."""
    ui.info(f"{counter} {path.name}")
    items.announce("start", path.name)
    if cfg["force"]:
        _clear_outputs(out_dir, path.stem)
    return handler(path, out_dir, cfg)


def _live(text: str) -> None:
    """Overwrite the current line with a transient progress line (TTY only).

    Mirrors ``ui.info``'s prefix so the live line and the settled lines align.
    """
    if sys.stdout.isatty():
        bullet = ui._c(ui.DIM, ui._SYM["info"])
        sys.stdout.write(f"\r  {bullet} {text}\033[K")
        sys.stdout.flush()


def _live_clear() -> None:
    if sys.stdout.isatty():
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


def _report_progress(i: int, name: str, n: int, done: int, total: int) -> None:
    """Show OCR page progress: a live line in a terminal, a log line every few pages elsewhere, and the console's item row."""
    _live(f"[{i}/{n}] {name}: page {done}/{total}")
    items.announce("progress", name, f"page {done:,} of {total:,}")
    if not sys.stdout.isatty() and done and (done % OCR_LOG_EVERY == 0 or done == total):
        ui.info(f"[{i}/{n}] {name}: page {done}/{total}")


def _run_ocr_phase(step_label: str, files: list, out_dir: Path, cfg: dict) -> list:
    """OCR runs file-serial (pages fan out inside each file), so announce every
    file before work starts and stream page-level progress, the phase is slow
    and would otherwise look hung."""
    n = len(files)
    ui.step(f"{step_label}: Extract OCR (scanned)  [{n} file(s)]")
    if not files:
        ui.info("Nothing to do, skipped")
        return []

    warns: list = []
    for i, path in enumerate(files, 1):
        name = path.name
        ui.info(f"[{i}/{n}] {name}: OCR starting…")
        items.announce("start", name)
        if cfg["force"]:
            _clear_outputs(out_dir, path.stem)

        try:
            report = functools.partial(_report_progress, i, name, n)
            outcome = workers.extract_ocr(path, out_dir, cfg, progress=report)
            result, warnings = outcome["result"], outcome["warnings"]
            _live_clear()
            ui.ok(f"[{i}/{n}] {name}: {result}")
            items.announce("ok", name, result)
            for w in warnings:
                ui.warn(f"    {w}")
                warns.append((path.name, w))
        except KeyboardInterrupt:
            _live_clear()
            raise SystemExit("\nInterrupted.")
        except Exception as e:
            _live_clear()
            ui.error(f"[{i}/{n}] {name}: {e}")
            items.announce("failed", name, str(e))
    return warns
