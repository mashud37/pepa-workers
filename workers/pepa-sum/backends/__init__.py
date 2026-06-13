"""LLM generation (backend-routed) and the prompts for the generated documents."""
from backends.llm import complete
from backends.prompt import (
    SUMMARY_SYSTEM, RUNDOWN_SYSTEM,
    build_summary_prompt, build_rundown_prompt,
)

__all__ = [
    "complete",
    "SUMMARY_SYSTEM", "RUNDOWN_SYSTEM",
    "build_summary_prompt", "build_rundown_prompt",
]
