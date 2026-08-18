"""Build the three output documents from a paper's text and signals: sum_
the structured brief, para_ the paragraph rundown, quote_ the verified
verbatim quotes.
"""
from documents.summary import build as build_summary, has_template
from documents.rundown import build as build_rundown
from documents.quotes import build as build_quotes

__all__ = ["build_summary", "build_rundown", "build_quotes", "has_template"]
