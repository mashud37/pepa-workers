"""Scan PDFs and determine their extraction route."""
import re
from pathlib import Path

from .text import _TEXT_THRESHOLD

_SCAN_SAMPLE = 24
_CHAPTER_FILE_RE = re.compile(r"^text_(.+)_(\d+)\.md$")


def import_fitz():
    import fitz
    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except Exception:
        pass
    return fitz


def _sample_indices(n: int) -> list:
    if n <= _SCAN_SAMPLE:
        return list(range(n))
    step = (n - 1) / (_SCAN_SAMPLE - 1)
    return sorted({int(round(i * step)) for i in range(_SCAN_SAMPLE)})


def scan_one(path: Path, fitz) -> dict | None:
    """Return the page count and text-layer fraction, or None if unreadable.

    The fraction is estimated from an evenly spaced page sample, not the whole
    document: routing only needs a coarse text-layer signal.

    Returns:
        {"pages": page count, "fraction": share of sampled pages with a text layer}.
    """
    try:
        with fitz.open(str(path)) as doc:
            n = doc.page_count
            if n == 0:
                return {"pages": 0, "fraction": 0.0}
            sample = _sample_indices(n)
            have = sum(1 for i in sample
                       if len((doc[i].get_text("text") or "").strip()) >= _TEXT_THRESHOLD)
    except Exception:
        return None
    return {"pages": n, "fraction": have / len(sample)}


def route(pages: int, fraction: float, cfg: dict) -> str:
    text_frac = 0.10
    if fraction < text_frac:
        return "ocr"
    return "book" if pages > cfg.get("book_page_threshold", 100) else "straight"


def scan_existing(out_dir: Path) -> dict:
    """Snapshot output filenames once.

    Returns:
        {"names": all text_*.md filenames, "chaptered": stems that have chapter files}.
    """
    names = {p.name for p in out_dir.glob("text_*.md")}
    chaptered = set()
    for name in names:
        match = _CHAPTER_FILE_RE.match(name)
        if match:
            chaptered.add(match.group(1))
    return {"names": names, "chaptered": chaptered}


def any_output(existing: dict, stem: str) -> bool:
    """True if any output file exists for this stem, regardless of route."""
    names, chaptered = existing["names"], existing["chaptered"]
    return f"text_{stem}.md" in names or stem in chaptered


def already_done(existing: dict, stem: str, file_route: str, pages: int, cfg: dict) -> bool:
    names, chaptered = existing["names"], existing["chaptered"]
    straight = f"text_{stem}.md" in names
    has_chapters = stem in chaptered
    if file_route == "straight":
        return straight
    if file_route == "book":
        return has_chapters
    return has_chapters if pages > cfg.get("book_page_threshold", 100) else straight
