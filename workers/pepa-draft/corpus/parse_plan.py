"""Parse a pepa-plan outline markdown file into structured items."""
import re
from pathlib import Path

_ITEM_RE = re.compile(r"^(\d+)\.\s+\[([A-Z_\-–— ]+)\]\s*[—\-–]\s*(.+)$")

MOVE_TO_SECTION = {
    "HOOK_PROBLEM": "introduction",
    "GAP": "introduction",
    "THESIS_AIM": "introduction",
    "OVERVIEW": "introduction",
    "THEORY_CONCEPT": "literature_review",
    "THEORY_FRAMEWORK": "literature_review",
    "LITERATURE_REVIEW": "literature_review",
    "PRIOR_WORK": "literature_review",
    "SYNTHESIS": "literature_review",
    "METHOD_DESIGN": "methods",
    "METHOD_DATA": "methods",
    "METHOD_ANALYSIS": "methods",
    "METHOD_VALIDITY": "methods",
    "METHOD_SAMPLE": "methods",
    "METHOD_INSTRUMENT": "methods",
    "METHOD_ANALYTICAL": "methods",
    "METHOD": "methods",
    "DATA_COLLECTION": "methods",
    "DATA_ANALYSIS": "methods",
    "ANALYSIS_FINDING": "findings",
    "FINDING": "findings",
    "RESULT": "findings",
    "DATA_RESULT": "findings",
    "DATA_SETTING": "findings",
    "INTERPRETATION": "discussion",
    "INTERPRETATION_THEORY": "discussion",
    "IMPLICATION": "discussion",
    "COUNTERPOINT": "discussion",
    "LIMITATION": "discussion",
    "CONCLUSION": "conclusion",
    "FUTURE_WORK": "conclusion",
    "CLOSING": "conclusion",
}


def _flush_item(items, current_index, current_move, current_lines):
    if current_index is None:
        return
    move_clean = current_move.strip()
    text = " ".join(" ".join(current_lines).split())
    default = _infer_section(move_clean)
    items.append({
        "index": current_index,
        "move": move_clean,
        "text": text,
        "default_section": default,
    })


def parse(path: Path) -> list[dict]:
    """Parse plan outline into a list of paragraph items.

    Args:
        path: Path to the plan markdown file.

    Returns:
        List of dicts: {index, move, text, default_section}
    """
    items = []
    current_index = None
    current_move = None
    current_lines = []

    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ITEM_RE.match(line.strip())
        if m:
            _flush_item(items, current_index, current_move, current_lines)
            current_index = int(m.group(1))
            current_move = m.group(2)
            current_lines = [m.group(3).strip()]
        elif line.strip() and current_index is not None:
            current_lines.append(line.strip())
    _flush_item(items, current_index, current_move, current_lines)
    return items


def _infer_section(move: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", move.upper()).strip("_")
    for key, section in MOVE_TO_SECTION.items():
        if normalized.startswith(key):
            return section
    return "findings"
