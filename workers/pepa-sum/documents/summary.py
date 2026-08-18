"""Build `sum_<name>.md`, the structured brief the model fills from the text and its
signals.
"""
import re

from backends import SUMMARY_SYSTEM, SUMMARY_TEMPLATE, Truncated, build_summary_prompt, complete

# One constant for the brief's output budget, shared by the live and batch paths.
# A full brief runs long: 2000 tokens cut off the closing fields (conclusion,
# future research), so the budget is 4000 with truncation now flagged, not silent.
MAX_TOKENS = 4000

# The template's bold field labels (**Question & context:**, **Methods:**, ...),
# read straight from the contract so this never drifts from the prompt.
_FIELDS = tuple(re.findall(r"\*\*[^*]+:\*\*", SUMMARY_TEMPLATE))
# A real brief carries the ## title and every field; a failed run returns plain
# prose with neither. Require the title plus all-but-two fields: strict enough
# that a stray "## " in an error message can't pass, lenient enough that the odd
# dropped field doesn't reject an otherwise good summary.
_MIN_FIELDS = max(1, len(_FIELDS) - 2)


class InvalidSummary(ValueError):
    """A summary run that must not be written: either the model returned text
    without the structured template, or it stopped at the output-token limit with
    the brief unfinished. Either way the paper is counted as a per-paper failure
    and no faulty sum_ file is written; a re-run retries it (its sum_ is absent).
    `partial` holds the cut-off body when truncation caused it, so the caller can
    save it for eval; it is None for a missing-template failure."""

    def __init__(self, message, partial=None):
        super().__init__(message)
        self.partial = partial


def has_template(text):
    """True when text is a filled summary brief rather than a plain-text stub.

    Checks the structure only a successful run produces: the ## H2 title plus a
    quorum of the template's bold field labels. Accepts either the raw LLM body
    (which starts with the H2) or a written file (filename line, then the H2)."""
    has_title = text.lstrip().startswith("## ") or "\n## " in text
    fields = sum(1 for f in _FIELDS if f in text)
    return has_title and fields >= _MIN_FIELDS


def build(text, signals, passages):
    try:
        body = complete(SUMMARY_SYSTEM, build_summary_prompt(text, signals, passages),
                        max_tokens=MAX_TOKENS, flag_truncation=True)
    except Truncated as e:
        raise InvalidSummary(
            f"summary hit the {MAX_TOKENS}-token output limit before completing",
            partial=e.text,
        )
    if not has_template(body):
        raise InvalidSummary("summary missing the structured template")
    return body
