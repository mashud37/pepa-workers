"""Build the three output documents from a paper's text and signals: sum_
the structured brief, para_ the paragraph rundown, quote_ the verified
verbatim quotes.
"""
from documents.quotes import build as build_quotes
from documents.rundown import build as build_rundown
from documents.summary import build as build_summary
from documents.summary import has_template

__all__ = ["build_summary", "build_rundown", "build_quotes", "has_template"]
