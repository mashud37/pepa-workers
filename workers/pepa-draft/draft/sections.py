"""Assign and persist plan paragraph-to-section mapping."""
import json

import config
from draft.template import SECTION_KEYS


def load(path=None) -> dict | None:
    p = path or config.SECTIONS_FILE
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save(assignment: dict, path=None) -> None:
    p = path or config.SECTIONS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(assignment, indent=2), encoding="utf-8")


def from_defaults(plan_items: list) -> dict:
    """Build assignment from move-label defaults.

    Args:
        plan_items: List of parsed plan items (from corpus/parse_plan.py).

    Returns:
        Dict mapping section key to list of item indices.
    """
    assignment = {k: [] for k in SECTION_KEYS}
    for item in plan_items:
        sec = item.get("default_section", "findings")
        if sec in assignment:
            assignment[sec].append(item["index"])
        else:
            assignment["findings"].append(item["index"])
    return assignment


def items_for_section(section_key: str, assignment: dict, plan_items: list) -> list:
    """Return plan items assigned to a section, in index order.

    Args:
        section_key: Section key string.
        assignment: Section assignment dict.
        plan_items: Full list of parsed plan items.

    Returns:
        Ordered list of plan item dicts.
    """
    indices = set(assignment.get(section_key, []))
    return [item for item in plan_items if item["index"] in indices]
