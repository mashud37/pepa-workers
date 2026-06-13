"""Extract text from a PDF, falling back to OCR for image-only pages.

pypdf reads the embedded text layer, which born-digital academic PDFs almost
always have. A page that yields almost no text is treated as scanned: it is
rendered and OCR'd locally via tesseract. That OCR path is optional and lazily
imported, so the tool still runs (with a warning) when poppler/tesseract are
not installed.
"""
import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

from cli import ui

# Below this many characters a page is assumed to be scanned, not born-digital.
_OCR_THRESHOLD = 40

# A line that is just a page number (arabic or roman), at a page edge.
_PAGE_NUM_RE = re.compile(r"^\s*(?:\d{1,4}|[ivxlcdm]{1,6})\s*$", re.IGNORECASE)

# A reference-list heading on its own line. Stripping everything from here cuts
# 1k+ tokens off a typical paper and removes text that adds nothing to a summary.
_REF_HEADING = re.compile(
    r"(?im)^\s*(?:\d+\.?\s*)?(references|bibliography|works cited|literature cited|reference list)\s*$"
)


def read_pdf(path) -> str:
    path = Path(path)
    reader = PdfReader(str(path))
    pages = []
    scanned = []
    for n, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if len(text) < _OCR_THRESHOLD:
            scanned.append(n)
        pages.append(text)

    if scanned:
        for n, text in _ocr_pages(path, scanned):
            pages[n] = text
    pages = _strip_running_headers(pages)
    return _strip_references("\n\n".join(p for p in pages if p).strip())


def _hdr_key(line):
    """Identity of a header/footer line ignoring its page number (which varies):
    the alphabetic characters, lowercased. None for lines too short to matter."""
    key = re.sub(r"[^a-z]", "", line.lower())
    return key if len(key) >= 5 else None


def _strip_running_headers(pages, edge_lines=3):
    """Remove running headers/footers and bare page-number lines.

    A running header (journal name, article title, author) repeats near the top
    or bottom of most pages, so pypdf splices it into the body between pages. We
    find edge lines whose text (minus the page number) recurs across many pages
    and drop them everywhere, plus any line that is only a page number."""
    if len(pages) < 4:
        return pages

    counts = Counter()
    for p in pages:
        lines = p.split("\n")
        for ln in lines[:edge_lines] + lines[-edge_lines:]:
            key = _hdr_key(ln)
            if key:
                counts[key] += 1

    threshold = max(3, int(len(pages) * 0.3))
    recurring = {k for k, c in counts.items() if c >= threshold}

    cleaned = []
    for p in pages:
        kept = [ln for ln in p.split("\n")
                if not _PAGE_NUM_RE.match(ln) and _hdr_key(ln) not in recurring]
        cleaned.append("\n".join(kept))
    return cleaned


def _strip_references(text):
    """Cut the document at its reference list. Uses the last references heading
    in the back half of the text, so an earlier in-text mention of "references"
    is never mistaken for the section itself."""
    cut = None
    for m in _REF_HEADING.finditer(text):
        if m.start() >= len(text) * 0.5:
            cut = m.start()
    return text[:cut].rstrip() if cut else text


def _ocr_pages(path, page_numbers):
    """Render the given (0-based) pages and OCR them. Yields (n, text).

    Degrades to a warning and no text when the OCR stack is unavailable."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        ui.warn(f"{path.name}: {len(page_numbers)} scanned page(s) skipped "
                "(install pytesseract + pdf2image, plus tesseract & poppler)")
        return

    for n in page_numbers:
        try:
            image = convert_from_path(str(path), first_page=n + 1, last_page=n + 1)[0]
            yield n, pytesseract.image_to_string(image).strip()
        except Exception as e:
            ui.warn(f"{path.name}: OCR failed on page {n + 1} ({e})")
