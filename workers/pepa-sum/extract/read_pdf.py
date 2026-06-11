"""Extract text from a PDF, falling back to OCR for image-only pages.

pypdf reads the embedded text layer, which born-digital academic PDFs almost
always have. A page that yields almost no text is treated as scanned: it is
rendered and OCR'd locally via tesseract. That OCR path is optional and lazily
imported, so the tool still runs (with a warning) when poppler/tesseract are
not installed.
"""
import re
from pathlib import Path

from pypdf import PdfReader

from cli import ui

# Below this many characters a page is assumed to be scanned, not born-digital.
_OCR_THRESHOLD = 40

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
    return _strip_references("\n\n".join(p for p in pages if p).strip())


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
