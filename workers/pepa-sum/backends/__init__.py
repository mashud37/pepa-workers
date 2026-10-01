"""LLM generation (backend-routed) and the prompts for the generated documents."""
from backends.anthropic_client import Truncated
from backends.llm import complete
from backends.prompt import (
    SUMMARY_SYSTEM, SUMMARY_TEMPLATE, RUNDOWN_SYSTEM,
    build_summary_prompt, build_rundown_prompt,
)

__all__ = [
    "complete",
    "Truncated",
    "SUMMARY_SYSTEM",
    "SUMMARY_TEMPLATE",
    "RUNDOWN_SYSTEM",
    "build_summary_prompt",
    "build_rundown_prompt",
]
