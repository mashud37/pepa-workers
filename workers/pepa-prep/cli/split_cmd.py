"""CLI layer for manual chapter splitting of single-block book files."""
import tempfile
from pathlib import Path

from extract import split as split_mod

from . import ui

_MAX_STEM = 60


def _trunc(s: str) -> str:
    return s if len(s) <= _MAX_STEM else s[: _MAX_STEM - 3] + "..."


def run(cfg: dict, file: str | None = None) -> None:
    out_dir = Path(cfg["output_folder"]) / "text"
    if not out_dir.is_dir():
        raise SystemExit(f"No extracted text found in {out_dir} — run extract first")

    singles = split_mod.find_single_blocks(out_dir)
    if not singles:
        ui.ok("No single-block book files found — nothing to split")
        return

    if file:
        # --file may be a full path or just the stem
        target_path = Path(file)
        if not target_path.exists():
            stem = target_path.stem if target_path.suffix else str(target_path)
            # Try to strip text_ prefix and _01 suffix for convenience
            stem = stem.removeprefix("text_").removesuffix("_01")
            if stem not in singles:
                raise SystemExit(
                    f"'{stem}' is not a single-block book file.\n"
                    f"Run without --file to see the full list."
                )
            source = singles[stem]
            stem_key = stem
        else:
            source = target_path
            # Derive stem from filename
            import re
            m = re.match(r"^text_(.+)_\d+\.md$", target_path.name)
            if not m:
                raise SystemExit(f"File name does not match expected pattern: {target_path.name}")
            stem_key = m.group(1)
    else:
        stem_key, source = _pick_book(singles)
        if stem_key is None:
            return

    ui.step(f"Split: {_trunc(stem_key)}")
    ui.info(f"File: {source.name}")
    ui.info(f"Size: {source.stat().st_size:,} bytes")
    ui.info("")
    ui.info("The file will open in your editor.")
    ui.info("Add a line containing exactly:  <!-- chapter -->")
    ui.info("at each point where a new chapter begins, then save and close.")

    if not ui.confirm("Open editor now?"):
        ui.info("Cancelled")
        return

    with tempfile.NamedTemporaryFile(
        suffix=".md", prefix=f"pepa_split_{stem_key[:30]}_",
        delete=False, dir=out_dir, mode="w", encoding="utf-8"
    ) as tf:
        tmp_path = Path(tf.name)

    try:
        split_mod.prepare_editor_file(source, tmp_path)
        split_mod.open_editor(tmp_path)

        ui.step("Applying markers")
        count, warnings = split_mod.apply_markers(tmp_path, stem_key, out_dir)

        for w in warnings:
            ui.warn(w)

        if count >= 2:
            ui.ok(f"Split into {count} chapter file(s):")
            width = max(2, len(str(count)))
            for i in range(1, count + 1):
                name = f"text_{stem_key}_{i:0{width}d}.md"
                size = (out_dir / name).stat().st_size
                ui.info(f"  {name}  ({size:,} bytes)")
        elif count == 1:
            ui.warn("Only 1 chunk found — file written as _01, no split performed")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _pick_book(singles: dict) -> tuple[str | None, Path | None]:
    stems = sorted(singles)
    ui.step(f"Single-block books  [{len(stems)} found]")

    page_size = 20
    offset = 0

    while True:
        batch = stems[offset: offset + page_size]
        options = [(f"{_trunc(s)}", f"text_{s}_01.md") for s in batch]
        if offset + page_size < len(stems):
            options.append(("More …", f"show next {min(page_size, len(stems) - offset - page_size)} books"))

        choice = ui.menu(
            f"Choose a book to split  [{offset + 1}–{offset + len(batch)} of {len(stems)}]",
            options,
        )
        if choice is None:
            return None, None
        if offset + page_size < len(stems) and choice == len(batch):
            offset += page_size
            continue
        stem = batch[choice]
        return stem, singles[stem]
