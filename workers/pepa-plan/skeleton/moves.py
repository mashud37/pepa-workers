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


def _snap(label):
    cleaned = label.strip().upper().replace(" ", "_").replace("-", "_")
    return _MOVES_UPPER.get(cleaned, "OTHER")


def label(sentences):
    if not sentences:
        return []
    raw = llm.complete(prompt.moves_system(), prompt.moves_prompt(sentences), quality=False)
    results = []
    for line in raw.splitlines():
        m = re.match(r"^\s*\d+[.)]\s*(.+)", line)
        if m:
            results.append(_snap(m.group(1)))
    if len(results) < len(sentences):
        results.extend(["OTHER"] * (len(sentences) - len(results)))
    return results[:len(sentences)]
