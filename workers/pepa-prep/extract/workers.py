"""Per-file extraction workers for straight, book, and OCR routes."""
from pathlib import Path

from . import marks, pdf
from .chapter import detect_chapters, split_into_chapters, write_chapters
from .ocr import ocr_pages
from .tables import doc_tables
from .text import (
    doc_dims,
    doc_lines,
    doc_stats,
    drop_keys,
    render,
    segment,
    strip_references,
    text_to_elements,
)


def _resolve_chapters(chapters: list, whole: list, cfg: dict, count: int, unit: str) -> dict:
    """Sanity-check the chapter count; collapse to one file if it is implausibly high.

    Returns:
        {"chapters", "warnings"}.
    """
    cap = cfg.get("max_chapters", 80)
    if len(chapters) > cap:
        return {
            "chapters": [whole],
            "warnings": [
                f"{len(chapters)} chapter boundaries detected in {count} {unit} "
                f"(over max_chapters {cap}), almost certainly spurious headings; wrote a "
                "single file instead. Inspect the source or raise max_chapters."
            ],
        }
    if len(chapters) < 2:
        warning = (f"no chapter boundaries detected in {count} {unit}, wrote a single "
                   "file (possible missed Chapter/Part headings)")
        return {"chapters": chapters, "warnings": [warning]}
    return {"chapters": chapters, "warnings": []}


def extract_straight(path: Path, out_dir: Path, cfg: dict) -> dict:
    """Extract a single-file, born-digital PDF straight to markdown.

    Returns:
        {"result": one-line summary, "warnings": list of warning strings}.
    """
    doc = pdf.open_pdf(path)
    try:
        pages = marks.blank_left_out(path.stem, doc_lines(doc, range(pdf.page_count(doc))), [])
        tables = marks.blank_left_out(path.stem, doc_tables(path, doc, range(pdf.page_count(doc))), [])
    finally:
        pdf.close_pdf(doc)
    stats = doc_stats(pages)
    md = strip_references(render(segment(pages, stats, drop_keys(pages), tables)))
    dest = out_dir / f"text_{path.stem}.md"
    dest.write_text(md, encoding="utf-8")
    return {"result": f"one file, {len(md):,} characters", "warnings": []}


def extract_book(path: Path, out_dir: Path, cfg: dict) -> dict:
    """Extract a born-digital PDF and split it into chapter files.

    Returns:
        {"result": one-line summary, "warnings": list of warning strings}.
    """
    doc = pdf.open_pdf(path)
    try:
        page_count = pdf.page_count(doc)
        pages = marks.blank_left_out(path.stem, doc_lines(doc, range(page_count)), [])
        dims = doc_dims(doc, range(page_count))
        tables = marks.blank_left_out(path.stem, doc_tables(path, doc, range(page_count)), [])
        stats = doc_stats(pages)
        dk = drop_keys(pages)
        marked = marks.marked_starts(path.stem)
        if marked:
            bounds = [{"title": "", "page": page - 1} for page in marked]
            meta = {"strategy": "marked", "notes": []}
        else:
            detected = detect_chapters(doc, pages, dims, stats, cfg)
            bounds, meta = detected["bounds"], detected["meta"]
    finally:
        pdf.close_pdf(doc)
    whole = segment(pages, stats, dk, tables)
    if meta["strategy"] == "marked" or (meta["strategy"] in ("outline", "toc") and len(bounds) >= 2):
        starts = [b["page"] for b in bounds]
        chapters = [segment(pages[a:z], stats, dk, tables[a:z])
                    for a, z in zip(starts, starts[1:] + [page_count])]
        marks.save_found(path.stem, [start + 1 for start in starts], meta["strategy"])
    else:
        chapters = split_into_chapters(whole)
        marks.save_found(path.stem, [], meta["strategy"])
    warnings = []
    if meta["strategy"] != "marked":
        resolved = _resolve_chapters(chapters, whole, cfg, page_count, "pages")
        chapters, warnings = resolved["chapters"], resolved["warnings"]
    warnings = [f"{meta['strategy']}: {w}" for w in meta["notes"]] + warnings
    result = write_chapters(path.stem, out_dir, chapters)
    if meta["strategy"] == "marked":
        result += " from your marks"
    elif len(chapters) >= 2:
        verified = (f", {meta['verified']:.0%} verified"
                    if meta.get("verified") is not None else "")
        result += f" via {meta['strategy']}{verified}"
    return {"result": result, "warnings": warnings}


def extract_ocr(path: Path, out_dir: Path, cfg: dict, progress=None) -> dict:
    """Extract a scanned PDF through OCR, splitting into chapters if it is long.

    Returns:
        {"result": one-line summary, "warnings": list of warning strings}.
    """
    pages = marks.blank_left_out(path.stem, ocr_pages(path, cfg, progress=progress), "")
    marked = marks.marked_starts(path.stem)
    if marked:
        starts = [page - 1 for page in marked]
        chapters = [text_to_elements(pages[a:z]) for a, z in zip(starts, starts[1:] + [len(pages)])]
        marks.save_found(path.stem, marked, "marked")
        return {"result": write_chapters(path.stem, out_dir, chapters) + " from your marks", "warnings": []}
    elements = text_to_elements(pages)
    threshold = cfg.get("book_page_threshold", 100)
    if len(pages) > threshold:
        chapters = split_into_chapters(elements)
        resolved = _resolve_chapters(chapters, elements, cfg, len(pages), "scanned pages")
        chapters, warnings = resolved["chapters"], resolved["warnings"]
        return {"result": write_chapters(path.stem, out_dir, chapters), "warnings": warnings}
    md = strip_references(render(elements))
    dest = out_dir / f"text_{path.stem}.md"
    dest.write_text(md, encoding="utf-8")
    return {"result": f"one file, {len(md):,} characters, read by OCR", "warnings": []}


HANDLERS = {
    "straight": extract_straight,
    "book": extract_book,
    "ocr": extract_ocr,
}
