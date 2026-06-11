"""Talks to the Cloud Run summariser service and builds its prompt."""
from backends.prompt import build_prompt, SYSTEM
from backends.summarizer import summarize

__all__ = ["build_prompt", "SYSTEM", "summarize"]
