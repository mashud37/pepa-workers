import re

from backends import llm
from backends import prompt

MOVES = [
    "HOOK_PROBLEM",
    "BACKGROUND",
    "GAP",
    "THESIS_AIM",
    "CONTRIBUTION_PREVIEW",
    "ROADMAP",
    "LIT_POSITIONING",
    "THEORY_CONCEPT",
    "METHOD",
    "DATA_SETTING",
    "ANALYSIS_FINDING",
    "INTERPRETATION",
    "COUNTERPOINT_LIMITATION",
    "IMPLICATION",
    "FUTURE_WORK",
    "CONCLUSION",
]

_MOVES_UPPER = {m.upper(): m for m in MOVES}


def _snap(label_text):
    cleaned = label_text.strip().upper().replace(" ", "_").replace("-", "_")
    return _MOVES_UPPER.get(cleaned, "OTHER")


def _max_tokens(n):
    """One short '<n>. <LABEL>' line per sentence, plus a little slack."""
    return 16 * n + 64


def request(sentences):
    """(system, prompt, max_tokens) for labelling one paper — shared by the live
    and batch paths, so a batch-labelled paper is identical in shape to a live one."""
    return (prompt.moves_system(), prompt.moves_prompt(sentences), _max_tokens(len(sentences)))


def parse(raw, n):
    """Snap the model's numbered lines back to the controlled vocabulary, padding
    any short reply with OTHER so the result always has one move per sentence."""
    results = []
    for line in raw.splitlines():
        m = re.match(r"^\s*\d+[.)]\s*(.+)", line)
        if m:
            results.append(_snap(m.group(1)))
    if len(results) < n:
        results.extend(["OTHER"] * (n - len(results)))
    return results[:n]


def label(sentences):
    if not sentences:
        return []
    system, user, max_tokens = request(sentences)
    raw = llm.complete(system, user, max_tokens=max_tokens, quality=False)
    return parse(raw, len(sentences))
