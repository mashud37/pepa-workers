"""Write a first draft from a pepa-plan outline and a pepa-review review, section by section.
The console's Draft page shows each draft beside the papers it drew on.
"""
import json
from datetime import datetime
from pathlib import Path

import config
from cli import ui
from cli.progress import StepSpinner


def _load_inputs(review_file, plan_file):
    from corpus.load import pick_plan, pick_review
    review_path = pick_review(review_file)
    plan_path = pick_plan(plan_file)
    return {"review_path": review_path, "plan_path": plan_path}


def _parse_inputs(review_path, plan_path):
    sp = StepSpinner("parsing files")
    sp.start()
    try:
        from corpus.parse_plan import parse as parse_plan
        from corpus.parse_review import parse as parse_review
        review_parsed = parse_review(review_path)
        plan_items = parse_plan(plan_path)
    finally:
        sp.done()
    if not plan_items:
        raise SystemExit(f"{plan_path.name} has no numbered plan items like '1. [MOVE]: point'. Is it a pepa-plan outline?")
    return {"review_parsed": review_parsed, "plan_items": plan_items}


def _show_plan_assignment(assignment, plan_items):
    from draft.sections import items_for_section
    from draft.template import SECTIONS
    ui.step("Section assignment")
    for sec in SECTIONS:
        items = items_for_section(sec["key"], assignment, plan_items)
        ui.info(f"\n  {sec['label']} ({len(items)} moves)")
        for item in items:
            ui.info(f"    {item['index']:>2}. [{item['move']}] {item['text'][:65]}")


def _resolve_assignment(plan_items, plan_path, options):
    """The plan's section assignment: from --sections, an earlier save, or the move-label defaults.

    The defaults are used as they are with --accept-sections; otherwise the user is asked first.
    """
    from corpus.load import sections_path_for_plan
    from draft.sections import from_defaults
    from draft.sections import load as load_assignment
    from draft.sections import save as save_assignment
    sections_file = options.get("sections_file")
    sec_path = Path(sections_file) if sections_file else sections_path_for_plan(plan_path)
    assignment = load_assignment(sec_path)
    if assignment:
        return assignment

    assignment = from_defaults(plan_items)
    if options.get("only_estimate"):
        return assignment
    ui.info("no section assignment found: building from move-label defaults")
    _show_plan_assignment(assignment, plan_items)
    if options.get("accept_sections"):
        save_assignment(assignment, sec_path)
        return assignment

    choice = ui.menu("Proceed with this assignment?", [
        ("Proceed to draft", "Use this assignment as-is and continue"),
        ("Edit first",       "Adjust section assignments before drafting"),
    ])
    if choice is None:
        raise SystemExit("Cancelled.")
    if choice == 1:
        from cli.sections_cmd import edit_loop
        outcome = edit_loop(assignment, plan_items, sec_path, draft_mode=True)
        if not outcome["proceed"]:
            raise SystemExit("Cancelled.")
        return outcome["assignment"]

    save_assignment(assignment, sec_path)
    ui.ok(f"saved assignment to {sec_path.name}")
    return assignment


def _run_checks(manuscript):
    from edit.check import check
    all_issues = []
    for sec in manuscript["sections"]:
        if sec["text"]:
            issues = check(sec["text"])
            for issue in issues[:3]:
                ui.warn(f"{sec['label']}: {issue['type']}: {issue['detail']}")
            all_issues.extend(issues)
    if not all_issues:
        ui.ok("no issues found")


def _print_summary(manuscript, word_targets, total_target, out_path):
    ui.step("Complete")
    ui.ok(f"saved: {out_path.name}")
    ui.info(f"total: {manuscript['total_words']} words (target {total_target})")
    for sec in manuscript["sections"]:
        t = word_targets[sec["key"]]
        diff = sec["words"] - t
        sign = "+" if diff >= 0 else ""
        ui.info(f"  {sec['label']:<20} {sec['words']:>5} words  ({sign}{diff})")


def run(options=None):
    """Draft a manuscript and write it to output/, with the papers it drew on in a .json beside it.

    Args:
        options: "review_file", "plan_file", "sections_file", "backend", "skip" (a set holding
            "retrieval" or "style"), "style_profile", "accept_sections", "only_estimate" and
            "output_name", as manage.py parses them.
    """
    options = options or {}
    skip = options.get("skip") or set()
    loaded = _load_inputs(options.get("review_file"), options.get("plan_file"))
    parsed = _parse_inputs(loaded["review_path"], loaded["plan_path"])
    review_parsed, plan_items = parsed["review_parsed"], parsed["plan_items"]
    assignment = _resolve_assignment(plan_items, loaded["plan_path"], options)
    if options.get("only_estimate"):
        from draft.costs import draft_estimate
        print(json.dumps(draft_estimate(plan_items, assignment, review_parsed)))
        return
    ui.header("pepa-draft: draft manuscript")
    ui.info(f"review: {loaded['review_path'].name}")
    ui.info(f"plan:   {loaded['plan_path'].name}")

    from draft.template import targets
    word_targets = targets()
    total_target = sum(word_targets.values())
    ui.info(f"target: {total_target} words total")

    from draft.assemble import render_markdown
    from draft.assemble import run as assemble
    opts = {
        "backend": options.get("backend"),
        "use_retrieval": "retrieval" not in skip,
        "use_style": "style" not in skip,
        "restrict_works": set(review_parsed["works"]) or None,
        "style_profile": options.get("style_profile"),
    }
    manuscript = assemble(plan_items, assignment, review_parsed, opts)

    ui.step("Post-draft checks")
    _run_checks(manuscript)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = config.OUTPUT_DIR / (options.get("output_name") or f"manuscript_{ts}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_markdown(manuscript), encoding="utf-8")
    out_path.with_suffix(".json").write_text(json.dumps({"works": manuscript["works"]}, indent=2), encoding="utf-8")
    _print_summary(manuscript, word_targets, total_target, out_path)
    print(out_path)
