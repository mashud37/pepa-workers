"""CLI layer for markdown refinement: dry-run diagnosis and apply."""
from pathlib import Path

from extract.config import COMMAND, DATA_ROOT
from extract.validate import book_groups
from refine import engine

from . import ui

_MAX_NAME = 46
REPORT = DATA_ROOT / "data" / "refine_report.md"


def _gather(cfg: dict, book: str | None) -> dict:
    """Return the extracted-text folder and the chapter-file groups to refine.

    Returns:
        {"out_dir": text output folder, "items": sorted [(stem, group)] pairs}.
    """
    out_dir = Path(cfg["output_folder"]) / "text"
    if not out_dir.is_dir():
        raise SystemExit(f"No extracted text found in {out_dir}, run extract first")
    groups = book_groups(out_dir)
    if book:
        needle = book.casefold()
        groups = {s: g for s, g in groups.items() if needle in s.casefold()}
    if not groups:
        raise SystemExit("No chapter files (text_<stem>_NN.md) found"
                         + (f" matching '{book}'" if book else "") + ".")
    return {"out_dir": out_dir, "items": sorted(groups.items())}


def run(cfg: dict, apply: bool = False, book: str | None = None) -> None:
    gathered = _gather(cfg, book)
    out_dir, items = gathered["out_dir"], gathered["items"]

    ui.step("Plan")
    ui.info("Step 1/2: Analyse books and plan repairs")
    ui.info("Step 2/2: " + ("Apply repairs and write report"
                            if apply else "Write diagnosis report (dry-run)"))
    ui.info(f"Output: {out_dir.resolve()}")
    ui.info(f"Report: {REPORT.resolve()}")

    ui.step(f"Step 1/2: Analyse  [{len(items)} book(s)]")
    rows, changed, errors = [], 0, 0
    for i, (stem, group) in enumerate(items, 1):
        short_stem = stem if len(stem) <= _MAX_NAME else stem[: _MAX_NAME - 3] + "..."
        ui.info(f"[{i}/{len(items)}] {short_stem}")
        try:
            bk = engine.load_book(stem, group)
            plan = engine.analyse(bk, cfg)
            if apply and engine.has_actions(plan):
                engine.apply_plan(bk, plan, out_dir)
        except Exception as e:
            ui.error(f"    {e}")
            errors += 1
            continue
        rows.append((stem, plan))
        if engine.has_actions(plan):
            changed += 1
            ui.ok(f"    {plan['n_before']} → {plan['n_after']} unit(s)  ·  "
                  f"{engine.actions_summary(plan)}")

    ui.step("Step 2/2: Report")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    engine.write_report(rows, REPORT)
    verb = "repaired" if apply else "with planned repairs"
    ui.ok(f"{len(rows)} book(s) analysed · {changed} {verb}"
          + (f" · {errors} error(s)" if errors else ""))
    ui.ok(f"Report → {REPORT}")
    if not apply and changed:
        ui.info(f"Nothing was changed. Apply with: {COMMAND} refine --apply")
