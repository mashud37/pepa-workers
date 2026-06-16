"""sum_<name>.md — the structured brief, filled by the LLM from text + signals."""
from backends import SUMMARY_SYSTEM, build_summary_prompt, complete

# One constant for the brief's output budget, shared by the live and batch paths.
MAX_TOKENS = 2000


def build(text, signals, passages):
    return complete(SUMMARY_SYSTEM, build_summary_prompt(text, signals, passages),
                    max_tokens=MAX_TOKENS)
