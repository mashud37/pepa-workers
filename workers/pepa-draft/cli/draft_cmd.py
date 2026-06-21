"""Main draft command: produce a full manuscript."""
from datetime import datetime
from pathlib import Path

import config
from cli import ui
from cli.progress import StepSpinner


def _load_inputs(review_file, plan_file):
    from corpus.load import pick_plan, pick_review
    review_path = pick_review(review_file)
    plan_path = pick_plan(plan_file)
    ui.info(f"review: {review_path.name}")
    ui.info(f"plan:   {plan_path.name}")
    return review_path, plan_path


def _parse_inputs(review_path, plan_path):
    sp = StepSpinner("parsing files")
    sp.start()
    try:
        from corpus.parse_plan import parse as parse_plan
        from corpus.parse_review import parse as parse_review
        review_parsed = parse_review(review_path)
        plan_items = parse_plan(plan_path)
    finally:
        sp.done(f"{len(plan_items)} plan items")
    return review_parsed, plan_items


def _show_plan_assignment(assignment, plan_items):
    from draft.sections import items_for_section
    from draft.template import SECTIONS
    ui.step("Section assignment")
    for sec in SECTIONS:
        items = items_for_section(sec["key"], assignment, plan_items)
        ui.info(f"\n  {sec['label']} ({len(items)} moves)")
        for item in items:
            ui.info(f"    {item['index']:>2}. [{item['move']}] {item['text'][:65]}")


def _resolve_assignment(plan_items, plan_path, sections_file):
    from corpus.load import sections_path_for_plan
    from draft.sections import from_defaults
    from draft.sections import load as load_assignment
    from draft.sections import save as save_assignment
    sec_path = Path(sections_file) if sections_file else sections_path_for_plan(plan_path)
    assignment = load_assignment(sec_path)
    if assignment:
        return assignment

    ui.info("no section assignment found — building from move-label defaults")
    assignment = from_defaults(plan_items)
    _show_plan_assignment(assignment, plan_items)

    choice = ui.menu("Proceed with this assignment?", [
        ("Proceed to draft", "Use this assignment as-is and continue"),
        ("Edit first",       "Adjust section assignments before drafting"),
    ])
    if choice is None:
        raise SystemExit("Cancelled.")
    if choice == 1:
        from cli.sections_cmd import edit_loop
        result, proceed = edit_loop(assignment, plan_items, sec_path, draft_mode=True)
        if not proceed:
            raise SystemExit("Cancelled.")
        return result

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
                ui.warn(f"{sec['label']}: {issue['type']} — {issue['detail']}")
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


def run(review_file=None, plan_file=None, sections_file=None, backend=None, skip=None, style_profile=None):
    skip = skip or set()
    ui.header("pepa-draft — draft manuscript")

    review_path, plan_path = _load_inputs(review_file, plan_file)
    review_parsed, plan_items = _parse_inputs(review_path, plan_path)
    assignment = _resolve_assignment(plan_items, plan_path, sections_file)

    from draft.template import targets
    word_targets = targets()
    total_target = sum(word_targets.values())
    ui.info(f"target: {total_target} words total")

    from draft.assemble import render_markdown
    from draft.assemble import run as assemble
    opts = {
        "backend": backend,
        "use_retrieval": "retrieval" not in skip,
        "use_style": "style" not in skip,
        "restrict_works": set(review_parsed.get("works", [])) or None,
        "style_profile": style_profile,
    }
    manuscript = assemble(plan_items, assignment, review_parsed, opts)

    ui.step("Post-draft checks")
    _run_checks(manuscript)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = config.OUTPUT_DIR / f"manuscript_{ts}.md"
    out_path.write_text(render_markdown(manuscript), encoding="utf-8")
    _print_summary(manuscript, word_targets, total_target, out_path)
