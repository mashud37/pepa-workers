"""Assign plan items to manuscript sections interactively."""
from cli import ui
from draft.template import SECTIONS


def _show_current(assignment: dict) -> None:
    ui.step("Current assignment")
    for sec in SECTIONS:
        indices = assignment.get(sec["key"], [])
        ui.info(f"  {sec['label']:<20} {len(indices)} items: {indices}")


def _move_item(assignment: dict, plan_items: list) -> None:
    raw = ui.ask("Item indices to move (e.g. 40 or 40,41,42)")
    if not raw:
        return
    parts = [p.strip() for p in raw.split(",")]
    to_move = []
    for p in parts:
        if not p.isdigit():
            ui.warn(f"Skipping invalid index: {p!r}")
            continue
        idx = int(p)
        item = None
        for i in plan_items:
            if i["index"] == idx:
                item = i
                break
        if not item:
            ui.warn(f"No item with index {idx}")
            continue
        to_move.append((idx, item))
    if not to_move:
        return
    for idx, item in to_move:
        ui.info(f"  {idx}. [{item['move']}] {item['text'][:80]}")
    sec_choice = ui.menu("Move to section", [s["label"] for s in SECTIONS])
    if sec_choice is None:
        return
    target_key = SECTIONS[sec_choice]["key"]
    for idx, _item in to_move:
        for key in assignment:
            if idx in assignment[key]:
                assignment[key].remove(idx)
        assignment[target_key].append(idx)
    assignment[target_key].sort()
    label = SECTIONS[sec_choice]["label"]
    if len(to_move) == 1:
        ui.ok(f"item {to_move[0][0]} moved to {label}")
    else:
        ui.ok(f"{len(to_move)} items moved to {label}: {[i for i, _ in to_move]}")
    _show_current(assignment)


def _show_unassigned(assignment: dict, plan_items: list) -> None:
    all_assigned = set()
    for indices in assignment.values():
        for i in indices:
            all_assigned.add(i)
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


def _reset_assignment(_assignment, plan_items):
    from draft.sections import from_defaults
    ui.ok("reset to move-label defaults (not yet saved)")
    return from_defaults(plan_items)


def _edit_loop_menu(draft_mode: bool) -> dict:
    if draft_mode:
        options = [
            ("Proceed to draft",   "Save and continue to manuscript generation"),
            ("Move item",          "Move one or more plan items to a different section"),
            ("Show unassigned",    "List items not in any section"),
            ("Show section items", "List items for a specific section"),
            ("Reset to defaults",  "Rebuild from move-label defaults (unsaved changes lost)"),
        ]
        actions = {1: _move_item, 2: _show_unassigned, 3: _show_section, 4: _reset_assignment}
    else:
        options = [
            ("Move item",          "Move one or more plan items to a different section"),
            ("Show unassigned",    "List items not in any section"),
            ("Show section items", "List items for a specific section"),
            ("Reset to defaults",  "Rebuild from move-label defaults (unsaved changes lost)"),
        ]
        actions = {0: _move_item, 1: _show_unassigned, 2: _show_section, 3: _reset_assignment}
    return {"options": options, "actions": actions}


def edit_loop(assignment: dict, plan_items: list, sec_path, draft_mode: bool = False) -> dict:
    """Run the interactive section editor.

    Args:
        assignment: Current section assignment dict (modified in place or replaced on reset).
        plan_items: All parsed plan items.
        sec_path: Path where the assignment should be saved.
        draft_mode: When True, show a 'Proceed to draft' option as [1].

    Returns:
        Dict with keys assignment and proceed. proceed is True only when the user
        explicitly chose to continue to the draft.
    """
    from draft.sections import save as save_assignment

    menu = _edit_loop_menu(draft_mode)

    while True:
        _show_current(assignment)
        choice = ui.menu("Edit assignment", menu["options"], back_label="Save and exit")

        if choice is None:
            save_assignment(assignment, sec_path)
            ui.ok(f"saved to {sec_path.name}")
            return {"assignment": assignment, "proceed": False}

        if draft_mode and choice == 0:
            save_assignment(assignment, sec_path)
            ui.ok(f"saved to {sec_path.name}")
            return {"assignment": assignment, "proceed": True}

        if choice in menu["actions"]:
            result = menu["actions"][choice](assignment, plan_items)
            if result is not None:
                assignment = result


def run(plan_file: str = None, reset: bool = False) -> None:
    ui.header("pepa-draft: section assignment")

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

    edit_loop(assignment, plan_items, sec_path, draft_mode=False)
