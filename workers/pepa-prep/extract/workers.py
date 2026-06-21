"""Per-file extraction workers for straight, book, and OCR routes."""
from pathlib import Path

from .categorise import import_fitz
from .chapter import split_into_chapters, toc_chapters, write_chapters
from .ocr import ocr_pages
from .text import (
    doc_lines,
    doc_stats,
    drop_keys,
    render,
    segment,
    strip_references,
    text_to_elements,
)


def _text_flags(fitz) -> int:
    return fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES


def _no_boundary_warning(unit: str, pages: int) -> list:
    return [f"no chapter boundaries detected in {pages} {unit} — wrote a single "
            "file (possible missed Chapter/Part headings)"]


def _resolve_chapters(chapters: list, whole: list, cfg: dict, count: int, unit: str) -> tuple:
    """Sanity-check the chapter count; collapse to one file if it is implausibly high."""
    cap = cfg.get("max_chapters", 80)
    if len(chapters) > cap:
        return [whole], [
            f"{len(chapters)} chapter boundaries detected in {count} {unit} "
            f"(over max_chapters {cap}) — almost certainly spurious headings; wrote a "
            "single file instead. Inspect the source or raise max_chapters."
        ]
    if len(chapters) < 2:
        return chapters, _no_boundary_warning(unit, count)
    return chapters, []


def extract_straight(path: Path, out_dir: Path, cfg: dict) -> tuple[str, list]:
    fitz = import_fitz()
    with fitz.open(str(path)) as doc:
        pages = doc_lines(doc, range(doc.page_count), _text_flags(fitz))
    body, heads, lh = doc_stats(pages)
    md = strip_references(render(segment(pages, body, heads, drop_keys(pages), lh)))
    dest = out_dir / f"text_{path.stem}.md"
    dest.write_text(md, encoding="utf-8")
    return f"text_{path.stem}.md ({len(md):,} chars)", []


def extract_book(path: Path, out_dir: Path, cfg: dict) -> tuple[str, list]:
    fitz = import_fitz()
    with fitz.open(str(path)) as doc:
        page_count = doc.page_count
        pages = doc_lines(doc, range(page_count), _text_flags(fitz))
        body, heads, lh = doc_stats(pages)
        dk = drop_keys(pages)
        toc = toc_chapters(doc)
    whole = segment(pages, body, heads, dk, lh)
    if toc:
        chapters = [segment(pages[rng.start:rng.stop], body, heads, dk, lh)
                    for _, rng in toc]
    else:
        chapters = split_into_chapters(whole)
    chapters, warnings = _resolve_chapters(chapters, whole, cfg, page_count, "pages")
    return write_chapters(path.stem, out_dir, chapters), warnings


def extract_ocr(path: Path, out_dir: Path, cfg: dict) -> tuple[str, list]:
    fitz = import_fitz()
    pages = ocr_pages(path, fitz, cfg)
    elements = text_to_elements(pages)
    threshold = cfg.get("book_page_threshold", 100)
    if len(pages) > threshold:
        chapters = split_into_chapters(elements)
        chapters, warnings = _resolve_chapters(chapters, elements, cfg, len(pages),
                                               "scanned pages")
        return write_chapters(path.stem, out_dir, chapters), warnings
    md = strip_references(render(elements))
    dest = out_dir / f"text_{path.stem}.md"
    dest.write_text(md, encoding="utf-8")
    return f"text_{path.stem}.md ({len(md):,} chars, OCR)", []


HANDLERS = {
    "straight": extract_straight,
    "book": extract_book,
    "ocr": extract_ocr,
}
