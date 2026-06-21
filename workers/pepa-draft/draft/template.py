"""Manuscript section definitions and word count targets."""
import config

SECTIONS = [
    {"key": "introduction",      "label": "Introduction"},
    {"key": "literature_review", "label": "Literature Review"},
    {"key": "methods",           "label": "Methods"},
    {"key": "findings",          "label": "Findings"},
    {"key": "discussion",        "label": "Discussion"},
    {"key": "conclusion",        "label": "Conclusion"},
]

SECTION_KEYS = [s["key"] for s in SECTIONS]


def targets(overrides: dict = None) -> dict:
    """Return word count targets per section key.

    Args:
        overrides: Optional dict mapping section key to word count.

    Returns:
        Dict mapping section key to target word count.
    """
    base = dict(config.SECTION_TARGETS)
    if overrides:
        base.update(overrides)
    return base


def section_label(key: str) -> str:
    for s in SECTIONS:
        if s["key"] == key:
            return s["label"]
    return key.replace("_", " ").title()
