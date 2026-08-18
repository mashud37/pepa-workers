"""Run the deterministic local preprocessing before the model sees a paper: read the
PDF or markdown to text, extract linguistic signals, retrieve rich passages.
"""
from extract.read_source import SUFFIXES, read_document
from extract.read_pdf import read_pdf
from extract.signals import extract_signals
from extract.passages import select_passages

__all__ = ["read_document", "read_pdf", "SUFFIXES", "extract_signals", "select_passages"]
