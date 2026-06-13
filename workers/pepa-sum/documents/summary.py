"""sum_<name>.md — the structured brief, filled by the LLM from text + signals."""
from backends import SUMMARY_SYSTEM, build_summary_prompt, complete


def build(text, signals, passages):
    return complete(SUMMARY_SYSTEM, build_summary_prompt(text, signals, passages), max_tokens=2000)
