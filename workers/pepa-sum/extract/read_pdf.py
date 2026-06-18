"""Extract text from a PDF, falling back to OCR for image-only pages.

PyMuPDF reads the embedded text layer, which born-digital academic PDFs almost
always have; it is C-fast and returns at once on image-only pages, so a scanned
or print-to-PDF file is recognised as text-less instantly rather than stalling a
pure-Python parser. pypdf is the fallback when PyMuPDF is not installed. A page
that yields almost no text is treated as scanned: with OCR enabled it is rendered
via PyMuPDF and OCR'd locally via tesseract. The OCR path is optional and lazily
imported, so the tool still runs (with a warning) when PyMuPDF or tesseract are
not installed.
"""
import logging
import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)

import config
from cli import ui

# Below this many characters a page is assumed to be scanned, not born-digital.
_OCR_THRESHOLD = 40
# In `auto` mode, OCR only kicks in when at least this fraction of the pages are
# sparse — i.e. the document is genuinely scanned, not a born-digital paper with
# a few figure/equation pages that happen to carry no extractable text.
_OCR_DOC_FRACTION = 0.5

# A line that is just a page number (arabic or roman), at a page edge.
_PAGE_NUM_RE = re.compile(r"^\s*(?:\d{1,4}|[ivxlcdm]{1,6})\s*$", re.IGNORECASE)

# A reference-list heading on its own line. Stripping everything from here cuts
# 1k+ tokens off a typical paper and removes text that adds nothing to a summary.
_REF_HEADING = re.compile(
    r"(?im)^\s*(?:\d+\.?\s*)?(references|bibliography|works cited|literature cited|reference list)\s*$"
)


def read_pdf(path) -> str:
    path = Path(path)
    pages = _text_pages(path)
    scanned = [n for n, t in enumerate(pages) if len(t) < _OCR_THRESHOLD]

    if scanned and _should_ocr(len(scanned), len(pages)):
        for n, text in _ocr_pages(path, scanned):
            pages[n] = text
    pages = _strip_running_headers(pages)
    return _strip_references("\n\n".join(p for p in pages if p).strip())


def _text_pages(path):
    """Per-page text via PyMuPDF (fitz) — C-fast, and instant on image-only pages,
    so a scanned/print-to-PDF is recognised as text-less at once instead of grinding
    pypdf's pure-Python content-stream parser for minutes. Falls back to pypdf only
    when PyMuPDF is not installed."""
    try:
        import fitz
    except ImportError:
        return _text_pages_pypdf(path)
    # Malformed/print-to-PDF content streams make MuPDF print "syntax error in
    # content stream" straight to stderr; the text still extracts fine, so mute
    # the chatter — left on, it collides with the progress spinner's live line.
    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except Exception:
        pass
    out = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            raw = (page.get_text("text") or "").strip()
            out.append(raw.encode("utf-8", "surrogatepass").decode("utf-8", "ignore"))
    return out


def _text_pages_pypdf(path):
    out = []
    for page in PdfReader(str(path)).pages:
        raw = (page.extract_text() or "").strip()
        out.append(raw.encode("utf-8", "surrogatepass").decode("utf-8", "ignore"))
    return out


def _should_ocr(num_scanned, num_pages):
    """Whether to run the (slow) OCR path for this document. `off` never does;
    `force` always does; `auto` only when the document is mostly scanned, so a
    born-digital paper's odd image page never drags it onto the OCR path."""
    mode = config.ocr_mode()
    if mode == "off":
        return False
    if mode == "force":
        return True
    return num_pages > 0 and num_scanned / num_pages >= _OCR_DOC_FRACTION


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
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError:
        ui.warn(f"{path.name}: {len(page_numbers)} scanned page(s) skipped "
                "(install PyMuPDF + pytesseract, plus tesseract)")
        return

    dpi = config.ocr_dpi()
    scale = dpi / 72
    total = len(page_numbers)
    # Heads-up BEFORE the slow loop starts, so a scanned paper reads as "OCR is
    # working" rather than a hang. Set OCR: off (or PEPA_OCR=off) to skip it.
    ui.warn(f"{path.name}: scanned — OCR-ing {total} page(s) at {dpi} dpi (slow)")
    doc = fitz.open(str(path))
    try:
        for i, n in enumerate(page_numbers, 1):
            ui.info(f"[{i}/{total}] OCR page {n + 1}")
            try:
                pix = doc[n].get_pixmap(matrix=fitz.Matrix(scale, scale))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                raw = pytesseract.image_to_string(img).strip()
                yield n, raw.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")
            except Exception as e:
                ui.warn(f"{path.name}: OCR failed on page {n + 1} ({e})")
    finally:
        doc.close()
