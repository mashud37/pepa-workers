"""Read a source paper to plain text by file type: PDFs through read_pdf,
markdown or text files read as-is with references stripped again.
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
