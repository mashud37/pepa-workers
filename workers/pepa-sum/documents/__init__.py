"""Builds the three output documents from a paper's text and signals.

summary  -> sum_<name>.md   the structured brief
rundown  -> para_<name>.md  one sentence per paragraph, in order
quotes   -> quote_<name>.md the most expressive verbatim quotes (verified)
"""
from documents.summary import build as build_summary, has_template
from documents.rundown import build as build_rundown
from documents.quotes import build as build_quotes

__all__ = ["build_summary", "build_rundown", "build_quotes", "has_template"]
