"""CLI layer for segmentation evaluation: label PDFs, then score against corrections."""
from pathlib import Path

from evaluate import harness

from . import ui

_MAX_NAME = 46


def _trunc(name: str) -> str:
    return name if len(name) <= _MAX_NAME else name[: _MAX_NAME - 3] + "..."


def _gather(cfg: dict, input_dir: str | None) -> tuple[list, str]:
    """Return [(path, keep)] to label and a one-line source description."""
    if input_dir:
        src = Path(input_dir)
        if not src.is_dir():
            raise SystemExit(f"Input folder not found: {src}")
        pdfs = sorted(src.glob("*.pdf"))
        if not pdfs:
            raise SystemExit(f"No PDFs found in {src}")
        return [(p, None) for p in pdfs], f"{src.resolve()} (all pages)"
    if harness.SELECTION.exists():
        items = harness.selection(Path(cfg["input_folder"]))
        missing = [p.name for p, _ in items if not p.exists()]
        if missing:
            raise SystemExit(f"selection.tsv lists {len(missing)} missing PDF(s): "
                             f"{', '.join(missing[:3])}{' ...' if len(missing) > 3 else ''}")
        return items, f"{harness.SELECTION} ({len(items)} sliced doc(s))"
    raise SystemExit("No selection.tsv and no --input given. Create "
                     f"{harness.SELECTION} (filename<TAB>page-spec) or pass --input FOLDER.")


def label(cfg: dict, input_dir: str | None = None) -> None:
    items, src_desc = _gather(cfg, input_dir)
    harness.ensure_dirs()

    ui.step("Plan")
    ui.info("Step 1/2: Extract line streams")
    ui.info("Step 2/2: Write correctable tag files")
    ui.info(f"Source: {src_desc}")
    ui.info(f"Review: {harness.REVIEW_DIR.resolve()}")

    ui.step(f"Step 1/2: Extract streams  [{len(items)} doc(s)]")
    streams = []
    for i, (p, keep) in enumerate(items, 1):
        span = "all" if keep is None else f"{len(keep)}p"
        ui.info(f"[{i}/{len(items)}] {_trunc(p.name)}  ({span})")
        try:
            streams.append(harness.build_stream(p, cfg, keep))
        except Exception as e:
            ui.error(f"    {e}")

    ui.step(f"Step 2/2: Write tag files  [{len(streams)} stream(s)]")
    for i, stream in enumerate(streams, 1):
        path, skipped = harness.write_review(stream)
        name = _trunc(stream["name"])
        if skipped:
            ui.warn(f"[{i}/{len(streams)}] {name} — kept existing correction ({path.name})")
        else:
            ui.ok(f"[{i}/{len(streams)}] {name} — {path.name} ({len(stream['lines'])} lines)")

    ui.step("Done")
    ui.ok(f"Correct the tag files in {harness.REVIEW_DIR}, then run: python manage.py score")


def score(cfg: dict) -> None:
    items = harness.pending()
    if not items:
        raise SystemExit("No tag files found. Run: python manage.py label")

    ui.step("Plan")
    ui.info(f"Step 1/1: Score {len(items)} file(s) against corrections")
    ui.info(f"Report: {harness.REPORT.resolve()}")

    ui.step(f"Step 1/1: Score  [{len(items)} file(s)]")
    rows = []
    for i, (name, stream_path, review_path) in enumerate(items, 1):
        ui.info(f"[{i}/{len(items)}] {_trunc(name)}")
        base, merged, note = harness.grade_one(stream_path, review_path)
        if base is None:
            ui.warn(f"    skipped — {note}")
            continue
        if note:
            ui.warn(f"    {note}")
        rows.append((name, base, merged))
        ui.ok(f"    F1 {base['f1'] * 100:.1f}% → {merged['f1'] * 100:.1f}%  ·  "
              f"over {base['over_seg']}→{merged['over_seg']}  under {merged['under_seg']}  "
              f"junk {merged['junk']}  ·  WD {merged['windowdiff']:.3f}")

    ui.step("Done")
    if not rows:
        ui.warn("Nothing scored — correct some tag files first.")
        return
    harness.write_report(rows)
    base_agg = harness.aggregate([b for _, b, _ in rows])
    mrg_agg = harness.aggregate([m for _, _, m in rows])
    ui.ok(f"Macro-F1 {mrg_agg['f1'] * 100:.1f}% with merge "
          f"({base_agg['f1'] * 100:.1f}% pre-merge, "
          f"{(mrg_agg['f1'] - base_agg['f1']) * 100:+.1f})  ·  "
          f"over-splits {base_agg['over_seg']}→{mrg_agg['over_seg']}  ·  "
          f"median WindowDiff {mrg_agg['windowdiff']:.3f}")
    ui.ok(f"Report → {harness.REPORT}")
