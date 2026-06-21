"""CLI layer for chapter validation: grade, quarantine, renumber, report."""
from pathlib import Path

from extract import validate

from . import ui

_MAX_STEM = 50


def _trunc(s: str) -> str:
    return s if len(s) <= _MAX_STEM else s[: _MAX_STEM - 3] + "..."


def run(cfg: dict, dry: bool = False) -> None:
    out_dir = Path(cfg["output_folder"]) / "text"

    if not out_dir.is_dir():
        raise SystemExit(f"No extracted text found in {out_dir} — run extract first")

    groups = validate.book_groups(out_dir)
    if not groups:
        ui.info(f"No multi-part book outputs found in {out_dir}")
        return

    mode = "dry-run (no files moved)" if dry else "quarantine + renumber"

    ui.step("Plan")
    ui.info(f"Step 1/2: Grade {len(groups)} book(s)")
    ui.info(f"Step 2/2: Apply verdicts  [{mode}]")
    ui.info(f"Output:   {out_dir.resolve()}")

    ui.step(f"Step 1/2: Grade  [{len(groups)} book(s)]")
    graded: dict = {}
    total = len(groups)

    for i, (stem, group) in enumerate(sorted(groups.items()), 1):
        ui.info(f"[{i}/{total}] {_trunc(stem)}")
        rows = validate.grade_book(group)
        graded[stem] = rows
        keep = sum(1 for r in rows if r[4] == "keep")
        flag = sum(1 for r in rows if r[4].startswith("flag"))
        reject = sum(1 for r in rows if r[4].startswith("reject"))
        parts = [f"{keep} keep"]
        if flag:
            parts.append(f"{flag} flag")
        if reject:
            parts.append(f"{reject} reject")
        ui.ok(f"  {len(group)} chapter(s) → {', '.join(parts)}")

    ui.step(f"Step 2/2: Apply verdicts  [{mode}]")
    for stem, rows in graded.items():
        validate.apply_grades(out_dir, stem, rows, dry)

    validate.write_report(out_dir, graded)

    kept = sum(1 for rows in graded.values() for r in rows if not r[4].startswith("reject"))
    rejected = sum(1 for rows in graded.values() for r in rows if r[4].startswith("reject"))
    flagged = sum(1 for rows in graded.values() for r in rows if r[4].startswith("flag"))
    verb = "would quarantine" if dry else "quarantined"

    ui.step("Done")
    ui.ok(f"{kept} chapter(s) kept ({flagged} flagged for review)")
    if rejected:
        ui.warn(f"{verb} {rejected} into {out_dir / '_review'}")
    ui.ok(f"Report → {out_dir / 'report.md'}")
