"""Deterministic local preprocessing run before the LLM ever sees a paper.

read_pdf  -> plain text (text layer, OCR fallback for scanned pages)
signals   -> salient noun phrases, named entities, subject-verb-object triplets
passages  -> TREC-style retrieval of the information-rich passages + sections
"""
from extract.read_pdf import read_pdf
from extract.signals import extract_signals
from extract.passages import select_passages

__all__ = ["read_pdf", "extract_signals", "select_passages"]
