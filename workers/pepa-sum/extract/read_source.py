"""Read a source paper to plain text, dispatching on file type.

PDFs go through read_pdf (text layer, OCR fallback, running-header and reference
stripping). Markdown / plain-text inputs — produced upstream by pepa-prep, which
already reflows paragraphs and strips running headers, page numbers, and the
reference list — are read as-is. The reference strip is reapplied (idempotent on
pepa-prep output, a genuine cut on a hand-dropped .md) so a paper reaches the LLM
the same way whatever format it arrived in. The page-based header/page-number
logic is PDF-only: markdown has no page splits for it to act on.
"""
from pathlib import Path

from extract.read_pdf import read_pdf, strip_references

_TEXT_SUFFIXES = (".md", ".markdown", ".txt")
SUFFIXES = (".pdf",) + _TEXT_SUFFIXES


def read_document(path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix in _TEXT_SUFFIXES:
        return strip_references(path.read_text(encoding="utf-8", errors="ignore").strip())
    raise ValueError(f"unsupported input type: {suffix or path.name}")
