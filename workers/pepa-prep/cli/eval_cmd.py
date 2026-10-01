"""CLI layer for segmentation evaluation: label PDFs, then score against corrections."""
from pathlib import Path

from evaluate import chapters, harness
from evaluate import refine as refine_eval
from extract.validate import book_groups
from refine import engine

from . import ui

_MAX_NAME = 46


def _trunc(name: str) -> str:
    return name if len(name) <= _MAX_NAME else name[: _MAX_NAME - 3] + "..."


def _gather(cfg: dict, input_dir: str | None) -> dict:
    """Return docs to label and a one-line source description.

    Returns:
        {"items": [(path, keep)], "source": one-line source description}.
    """
    if input_dir:
        src = Path(input_dir)
        if not src.is_dir():
            raise SystemExit(f"Input folder not found: {src}")
        pdfs = sorted(src.glob("*.pdf"))
        if not pdfs:
            raise SystemExit(f"No PDFs found in {src}")
        return {"items": [(p, None) for p in pdfs], "source": f"{src.resolve()} (all pages)"}
    if harness.SELECTION.exists():
        items = harness.selection(Path(cfg["input_folder"]))
        missing = [p.name for p, _ in items if not p.exists()]
        if missing:
            raise SystemExit(f"selection.tsv lists {len(missing)} missing PDF(s): "
                             f"{', '.join(missing[:3])}{' ...' if len(missing) > 3 else ''}")
        return {"items": items, "source": f"{harness.SELECTION} ({len(items)} sliced doc(s))"}
    raise SystemExit("No selection.tsv and no --input given. Create "
                     f"{harness.SELECTION} (filename<TAB>page-spec) or pass --input FOLDER.")


def label(cfg: dict, input_dir: str | None = None) -> None:
    gathered = _gather(cfg, input_dir)
    items, src_desc = gathered["items"], gathered["source"]
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
        written = harness.write_review(stream)
        path, skipped = written["path"], written["kept"]
        name = _trunc(stream["name"])
        if skipped:
            ui.warn(f"[{i}/{len(streams)}] {name}: kept existing correction ({path.name})")
        else:
            ui.ok(f"[{i}/{len(streams)}] {name}: {path.name} ({len(stream['lines'])} lines)")

    ui.step("Done")
    ui.ok(f"Correct the tag files in {harness.REVIEW_DIR}, then run: python manage.py score")


def _gather_books(cfg: dict, input_dir: str | None) -> dict:
    """Return book PDFs to label and a one-line source description.

    Returns:
        {"items": PDF paths, "source": one-line source description}.
    """
    if input_dir:
        src = Path(input_dir)
        if not src.is_dir():
            raise SystemExit(f"Input folder not found: {src}")
        pdfs = sorted(src.glob("*.pdf"))
        if not pdfs:
            raise SystemExit(f"No PDFs found in {src}")
        return {"items": pdfs, "source": str(src.resolve())}
    if chapters.SELECTION.exists():
        items = chapters.selection(Path(cfg["input_folder"]))
        missing = [p.name for p in items if not p.exists()]
        if missing:
            raise SystemExit(f"selection.tsv lists {len(missing)} missing PDF(s): "
                             f"{', '.join(missing[:3])}{' ...' if len(missing) > 3 else ''}")
        return {"items": items, "source": f"{chapters.SELECTION} ({len(items)} book(s))"}
    raise SystemExit("No selection.tsv and no --input given. Create "
                     f"{chapters.SELECTION} (one PDF filename per line) or pass --input FOLDER.")


def label_chapters(cfg: dict, input_dir: str | None = None) -> None:
    gathered = _gather_books(cfg, input_dir)
    items, src_desc = gathered["items"], gathered["source"]
    chapters.ensure_dirs()

    ui.step("Plan")
    ui.info("Step 1/1: Detect chapters and write correctable gold files")
    ui.info(f"Source: {src_desc}")
    ui.info(f"Gold:   {chapters.GOLD_DIR.resolve()}")

    ui.step(f"Step 1/1: Detect chapters  [{len(items)} book(s)]")
    for i, p in enumerate(items, 1):
        ui.info(f"[{i}/{len(items)}] {_trunc(p.name)}")
        try:
            pred = chapters.predict_book(p, cfg)
        except Exception as e:
            ui.error(f"    {e}")
            continue
        if pred["route"] != "book":
            ui.warn(f"    route {pred['route']}, skipped (chapter detection runs "
                    "on the book route)")
            continue
        written = chapters.write_gold(pred)
        path, kept = written["path"], written["kept"]
        if kept:
            ui.warn(f"    kept existing gold ({path.name})")
        else:
            ui.ok(f"    {path.name} ({len(pred['bounds'])} boundaries, "
                  f"{pred['meta']['strategy']})")

    ui.step("Done")
    ui.ok(f"Correct the gold files in {chapters.GOLD_DIR}, then run: "
          "python manage.py score-chapters")


def score_chapters(cfg: dict) -> None:
    items = chapters.pending(Path(cfg["input_folder"]))
    if not items:
        raise SystemExit("No gold files found. Run: python manage.py label-chapters")

    ui.step("Plan")
    ui.info(f"Step 1/1: Re-run detection on {len(items)} book(s) and compare "
             "against your corrected reference files")
    ui.info("Match score: how closely detected chapter starts line up with "
             "yours, 0-100% (100% = every chapter start matches exactly)")
    ui.info(f"Report: {chapters.REPORT.resolve()}")

    ui.step(f"Step 1/1: Score  [{len(items)} book(s)]")
    rows = []
    for i, (name, pdf_path, gold_path) in enumerate(items, 1):
        ui.info(f"[{i}/{len(items)}] {_trunc(name)}")
        try:
            graded = chapters.grade_one(pdf_path, gold_path, cfg)
        except Exception as e:
            ui.error(f"    {e}")
            continue
        res, note = graded["result"], graded["note"]
        if res is None:
            ui.warn(f"    skipped: {note}")
            continue
        rows.append((name, res))
        ui.ok(f"    {res['strategy']}: match score {res['f1'] * 100:.1f}%  "
              f"(precision {res['precision'] * 100:.0f}%, recall {res['recall'] * 100:.0f}%)  "
              f"exact page {res['exact'] * 100:.0f}%  "
              f"({res['n_pred']} found / {res['n_gold']} in your reference)")

    ui.step("Done")
    if not rows:
        ui.warn("Nothing scored, correct some reference files first "
                 "(run label-chapters, then edit the files it writes).")
        return
    chapters.write_report(rows)
    agg = chapters.aggregate([r for _, r in rows])
    ui.ok(f"Overall match score: {agg['f1'] * 100:.1f}%  ·  exact page {agg['exact'] * 100:.1f}%  ·  "
          f"{agg['over']} spurious  {agg['under']} missed")
    ui.ok(f"Report: {chapters.REPORT}")


def label_refine(cfg: dict) -> None:
    groups = book_groups(Path(cfg["output_folder"]) / "text")
    refine_eval.ensure_dirs()
    if not refine_eval.SELECTION.exists():
        raise SystemExit(f"No selection found. Create {refine_eval.SELECTION} "
                         "(one book stem per line, as in text_<stem>_NN.md).")
    stems = refine_eval.selection()
    missing = [s for s in stems if s not in groups]
    if missing:
        raise SystemExit(f"selection.tsv lists {len(missing)} unknown stem(s): "
                         f"{', '.join(missing[:3])}{' ...' if len(missing) > 3 else ''}")

    ui.step("Plan")
    ui.info("Step 1/1: Write one reference file per book listing where each "
             "chapter currently starts")
    ui.info(f"Reference files: {refine_eval.GOLD_DIR.resolve()}")

    ui.step(f"Step 1/1: Write reference files  [{len(stems)} book(s)]")
    for i, stem in enumerate(stems, 1):
        ui.info(f"[{i}/{len(stems)}] {_trunc(stem)}")
        book = engine.load_book(stem, groups[stem])
        written = refine_eval.write_gold(stem, refine_eval.prefill(book))
        path, kept = written["path"], written["kept"]
        if kept:
            ui.warn(f"    kept existing file ({path.name}), not overwritten")
        else:
            ui.ok(f"    {path.name} ({len(book['starts'])} chapter starts listed)")

    ui.step("Done")
    ui.ok(f"Open the files in {refine_eval.GOLD_DIR}: each row is one chapter start "
          "(<occurrence><TAB><first line of text>). Delete wrong rows, add missing "
          "ones by copying the line from the markdown, then fix any occurrence number.")
    ui.ok("When the files are correct, run: python manage.py score-refine")


def score_refine(cfg: dict) -> None:
    items = refine_eval.pending()
    if not items:
        raise SystemExit("No gold files found. Run: python manage.py label-refine")
    groups = book_groups(Path(cfg["output_folder"]) / "text")

    ui.step("Plan")
    ui.info(f"Step 1/1: Re-run the refinement on {len(items)} book(s) and compare "
             "against your corrected reference files")
    ui.info("Match score: how closely the predicted chapter starts line up with "
             "yours, 0-100% (100% = every chapter start matches exactly)")
    ui.info(f"Report: {refine_eval.REPORT.resolve()}")

    ui.step(f"Step 1/1: Score  [{len(items)} book(s)]")
    rows = []
    for i, (stem, gold_path) in enumerate(items, 1):
        ui.info(f"[{i}/{len(items)}] {_trunc(stem)}")
        if stem not in groups:
            ui.warn("    skipped: no chapter files in the output folder")
            continue
        try:
            graded = refine_eval.grade_one(stem, groups[stem], gold_path, cfg)
        except Exception as e:
            ui.error(f"    {e}")
            continue
        res, note = graded["result"], graded["note"]
        if res is None:
            ui.warn(f"    skipped: {note}")
            continue
        if note:
            ui.warn(f"    {note}")
        rows.append((stem, res))
        ui.ok(f"    match score {res['base']['f1'] * 100:.1f}% → "
              f"{res['refined']['f1'] * 100:.1f}%  ·  "
              f"chapters found {res['base']['n_pred']} → {res['refined']['n_pred']} "
              f"(your reference: {res['base']['n_gold']})")

    ui.step("Done")
    if not rows:
        ui.warn("Nothing scored, correct some reference files first "
                 "(run label-refine, then edit the files it writes).")
        return
    refine_eval.write_report(rows)
    agg = refine_eval.aggregate([r for _, r in rows])
    ui.ok(f"Overall match score: {agg['base_f1'] * 100:.1f}% → {agg['f1'] * 100:.1f}% "
          f"({(agg['f1'] - agg['base_f1']) * 100:+.1f} points)")
    ui.ok(f"Report: {refine_eval.REPORT}")


def score(cfg: dict) -> None:
    items = harness.pending()
    if not items:
        raise SystemExit("No tag files found. Run: python manage.py label")

    ui.step("Plan")
    ui.info(f"Step 1/1: Compare {len(items)} file(s) against your corrections")
    ui.info("Match score: how closely detected boundaries line up with yours, "
             "0-100% (100% = every boundary matches exactly)")
    ui.info(f"Report: {harness.REPORT.resolve()}")

    ui.step(f"Step 1/1: Score  [{len(items)} file(s)]")
    rows = []
    for i, (name, stream_path, review_path) in enumerate(items, 1):
        ui.info(f"[{i}/{len(items)}] {_trunc(name)}")
        graded = harness.grade_one(stream_path, review_path)
        base, merged, note = graded["base"], graded["merged"], graded["note"]
        if base is None:
            ui.warn(f"    skipped: {note}")
            continue
        if note:
            ui.warn(f"    {note}")
        rows.append((name, base, merged))
        ui.ok(f"    match score {base['f1'] * 100:.1f}% → {merged['f1'] * 100:.1f}%  ·  "
              f"over-split {base['over_seg']}→{merged['over_seg']}  "
              f"under-split {merged['under_seg']}  "
              f"junk {merged['junk']}  ·  WindowDiff {merged['windowdiff']:.3f}")

    ui.step("Done")
    if not rows:
        ui.warn("Nothing scored, correct some tag files first.")
        return
    harness.write_report(rows)
    base_agg = harness.aggregate([b for _, b, _ in rows])
    mrg_agg = harness.aggregate([m for _, _, m in rows])
    ui.ok(f"Overall match score: {mrg_agg['f1'] * 100:.1f}% with merge "
          f"({base_agg['f1'] * 100:.1f}% pre-merge, "
          f"{(mrg_agg['f1'] - base_agg['f1']) * 100:+.1f} points)  ·  "
          f"over-splits {base_agg['over_seg']}→{mrg_agg['over_seg']}  ·  "
          f"median WindowDiff {mrg_agg['windowdiff']:.3f} (lower is better)")
    ui.ok(f"Report: {harness.REPORT}")
