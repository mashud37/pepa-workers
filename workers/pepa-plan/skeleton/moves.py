import re

from backends import llm, prompt

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


def request(sentences):
    """Build the labelling request for one paper: shared by the live and batch
    paths, so a batch-labelled paper is identical in shape to a live one.
    max_tokens covers one short '<n>. <LABEL>' line per sentence, plus slack.

    Returns:
        dict with `system`, `prompt`, and `max_tokens`.
    """
    max_tokens = 16 * len(sentences) + 64
    return {"system": prompt.moves_system(), "prompt": prompt.moves_prompt(sentences),
            "max_tokens": max_tokens}


def parse(raw, n):
    """Snap the model's numbered lines back to the controlled vocabulary, padding
    any short reply with OTHER so the result always has one move per sentence."""
    results = []
    for line in raw.splitlines():
        m = re.match(r"^\s*\d+[.)]\s*(.+)", line)
        if m:
            cleaned = m.group(1).strip().upper().replace(" ", "_").replace("-", "_")
            results.append(_MOVES_UPPER.get(cleaned, "OTHER"))
    if len(results) < n:
        results.extend(["OTHER"] * (n - len(results)))
    return results[:n]


def label(sentences):
    if not sentences:
        return []
    built = request(sentences)
    system, user, max_tokens = built["system"], built["prompt"], built["max_tokens"]
    raw = llm.complete(system, user, max_tokens=max_tokens, quality=False)
    return parse(raw, len(sentences))
