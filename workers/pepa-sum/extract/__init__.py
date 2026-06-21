"""Deterministic local preprocessing run before the LLM ever sees a paper.

read_document -> plain text from a .pdf (text layer, OCR fallback) or a .md/.txt
                (e.g. pepa-prep output), via read_pdf or a direct read
signals       -> salient noun phrases, named entities, subject-verb-object triplets
passages      -> TREC-style retrieval of the information-rich passages + sections
"""
from extract.read_source import SUFFIXES, read_document
from extract.read_pdf import read_pdf
from extract.signals import extract_signals
from extract.passages import select_passages

__all__ = ["read_document", "read_pdf", "SUFFIXES", "extract_signals", "select_passages"]
