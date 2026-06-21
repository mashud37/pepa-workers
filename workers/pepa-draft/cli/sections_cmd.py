"""Assign plan items to manuscript sections interactively."""
from cli import ui
from draft.template import SECTIONS


def _show_current(assignment: dict) -> None:
    ui.step("Current assignment")
    for sec in SECTIONS:
        indices = assignment.get(sec["key"], [])
        ui.info(f"  {sec['label']:<20} {len(indices)} items: {indices[:8]}")


def _move_item(assignment: dict, plan_items: list) -> None:
    raw = ui.ask("Item index to move")
    if not raw or not raw.isdigit():
        return
    idx = int(raw)
    item = next((i for i in plan_items if i["index"] == idx), None)
    if not item:
        ui.warn(f"No item with index {idx}")
        return
    ui.info(f"[{item['move']}] {item['text'][:80]}")
    sec_choice = ui.menu("Move to section", [s["label"] for s in SECTIONS])
    if sec_choice is None:
        return
    for key in assignment:
        if idx in assignment[key]:
            assignment[key].remove(idx)
    target_key = SECTIONS[sec_choice]["key"]
    assignment[target_key].append(idx)
    assignment[target_key].sort()
    ui.ok(f"item {idx} moved to {SECTIONS[sec_choice]['label']}")


def _show_unassigned(assignment: dict, plan_items: list) -> None:
    all_assigned = {i for indices in assignment.values() for i in indices}
    unassigned = [item for item in plan_items if item["index"] not in all_assigned]
    if not unassigned:
        ui.ok("all items assigned")
        return
    ui.info(f"{len(unassigned)} unassigned:")
    for item in unassigned:
        ui.info(f"  {item['index']}. [{item['move']}] {item['text'][:60]}")


def _show_section(assignment: dict, plan_items: list) -> None:
    choice = ui.menu("Section", [s["label"] for s in SECTIONS])
    if choice is None:
        return
    key = SECTIONS[choice]["key"]
    indices = set(assignment.get(key, []))
    items = [i for i in plan_items if i["index"] in indices]
    if not items:
        ui.info("no items assigned")
        return
    for item in sorted(items, key=lambda x: x["index"]):
        ui.info(f"  {item['index']}. [{item['move']}] {item['text'][:80]}")


def edit_loop(assignment: dict, plan_items: list, sec_path) -> dict:
    """Run the interactive section editor. Saves on exit and returns the final assignment.

    Args:
        assignment: Current section assignment dict (modified in place or replaced on reset).
        plan_items: All parsed plan items.
        sec_path: Path where the assignment should be saved.

    Returns:
        The saved assignment dict.
    """
    from draft.sections import from_defaults
    from draft.sections import save as save_assignment

    def _reset():
        nonlocal assignment
        assignment = from_defaults(plan_items)
        ui.ok("reset to move-label defaults (not yet saved)")

    while True:
        _ACTIONS = {
            0: lambda: _move_item(assignment, plan_items),
            1: lambda: _show_unassigned(assignment, plan_items),
            2: lambda: _show_section(assignment, plan_items),
            3: _reset,
        }
        _show_current(assignment)
        choice = ui.menu("Edit assignment", [
            ("Move item",          "Move a plan item to a different section"),
            ("Show unassigned",    "List items not in any section"),
            ("Show section items", "List items for a specific section"),
            ("Reset to defaults",  "Rebuild from move-label defaults (unsaved changes lost)"),
            ("Save and exit",      "Persist and return"),
        ])
        if choice is None or choice == 4:
            save_assignment(assignment, sec_path)
            ui.ok(f"saved to {sec_path.name}")
            return assignment
        if choice in _ACTIONS:
            _ACTIONS[choice]()


def run(plan_file: str = None, reset: bool = False) -> None:
    ui.header("pepa-draft — section assignment")

    from corpus.load import pick_plan, sections_path_for_plan
    from corpus.parse_plan import parse as parse_plan
    from draft.sections import from_defaults
    from draft.sections import load as load_assignment

    plan_path = pick_plan(plan_file)
    plan_items = parse_plan(plan_path)
    sec_path = sections_path_for_plan(plan_path)
    ui.ok(f"loaded {len(plan_items)} plan items from {plan_path.name}")
    ui.info(f"sections file: {sec_path.name}")

    if reset or not sec_path.exists():
        assignment = from_defaults(plan_items)
        ui.info("built default assignment from move labels")
    else:
        assignment = load_assignment(sec_path)
        ui.ok("loaded existing assignment")

    edit_loop(assignment, plan_items, sec_path)
