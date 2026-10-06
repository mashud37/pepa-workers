"""Per-file extraction workers for straight, book, and OCR routes."""
from pathlib import Path

from . import marks, pdf, toc
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


def drop_front_matter(doc, bounds: list) -> list:
    """The chapter starts without front matter: units whose pages are mostly roman-numbered, as books number it.

    The starts stay as found when fewer than two would be left.
    """
    page_count = pdf.page_count(doc)
    ends = [bound["page"] for bound in bounds[1:]] + [page_count]
    kept = []
    for bound, end in zip(bounds, ends):
        roman = 0
        for page in range(bound["page"], end):
            if toc.is_roman(pdf.page_label(doc, page)):
                roman += 1
        if roman * 2 <= end - bound["page"]:
            kept.append(bound)
    if len(kept) < 2:
        return bounds
    return kept


def extract_book(path: Path, out_dir: Path, cfg: dict) -> dict:
    """Extract a born-digital PDF and split it into chapter files.

    Returns:
        {"result": one-line summary, "warnings": list of warning strings}.
    """
    doc = pdf.open_pdf(path)
    try:
        page_count = pdf.page_count(doc)
        every_page = doc_lines(doc, range(page_count))
        pages = marks.blank_left_out(path.stem, every_page, [])
        dims = doc_dims(doc, range(page_count))
        tables = marks.blank_left_out(path.stem, doc_tables(path, doc, range(page_count)), [])
        stats = doc_stats(pages)
        dk = drop_keys(pages)
        marked_pages = {
            "left_out": {page - 1 for page in marks.left_out_pages(path.stem)},
            "contents": [page - 1 for page in marks.contents_pages(path.stem)],
        }
        detected = detect_chapters(doc, every_page, dims, stats, dict(cfg, marked_pages=marked_pages))
        bounds, meta = drop_front_matter(doc, detected["bounds"]), detected["meta"]
    finally:
        pdf.close_pdf(doc)
    found = []
    if meta["strategy"] in ("outline", "toc") and len(bounds) >= 2:
        found = [b["page"] + 1 for b in bounds]
    detector = {"starts": found, "strategy": meta["strategy"]}
    marked = marks.marked_starts(path.stem)
    if marked:
        found = marked
        meta = {"strategy": "marked", "notes": []}
    marks.save_found(path.stem, found, meta["strategy"], detector)
    whole = segment(pages, stats, dk, tables)
    if found:
        starts = [page - 1 for page in found]
        chapters = [segment(pages[a:z], stats, dk, tables[a:z])
                    for a, z in zip(starts, starts[1:] + [page_count])]
    else:
        chapters = split_into_chapters(whole)
    chapters = [chapter for chapter in chapters if chapter]
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
    every_page = ocr_pages(path, cfg, progress=progress)
    pages = marks.blank_left_out(path.stem, every_page, "")
    contents = [page - 1 for page in marks.contents_pages(path.stem)]
    from_contents = toc.ocr_contents_starts(every_page, contents)
    detector = {"starts": [start + 1 for start in from_contents], "strategy": "toc" if from_contents else "regex"}
    starts = [page - 1 for page in marks.marked_starts(path.stem)]
    strategy = "marked"
    if not starts:
        starts = from_contents
        strategy = "toc"
    if starts:
        chapters = [text_to_elements(pages[a:z]) for a, z in zip(starts, starts[1:] + [len(pages)])]
        chapters = [chapter for chapter in chapters if chapter]
        marks.save_found(path.stem, [start + 1 for start in starts], strategy, detector)
        how = " from your marks" if strategy == "marked" else " via toc, read by OCR"
        return {"result": write_chapters(path.stem, out_dir, chapters) + how, "warnings": []}
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
