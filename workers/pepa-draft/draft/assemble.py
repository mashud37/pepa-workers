"""Orchestrate full manuscript drafting across all sections."""
import time

from cli import items, ui
from cli.progress import StepSpinner
from draft.sections import items_for_section
from draft.template import SECTIONS, targets


def _retrieve_for_section(label, section_items, restrict_works):
    sp = StepSpinner(f"retrieving literature ({label})")
    sp.start()
    passages = []
    try:
        from index.retrieve import retrieve
        query = " ".join(item["text"][:100] for item in section_items[:3])
        passages = retrieve(query, restrict_bases=restrict_works)
    except SystemExit:
        pass
    finally:
        sp.done(f"{len(passages)} passages")
    return passages


def _style_for_section(section_items, label, profile=None):
    try:
        from index.style import retrieve as style_retrieve
        query = section_items[0]["text"] if section_items else label
        return style_retrieve(query, profile=profile)
    except Exception:
        return []


def _draft_section(key, label, section_items, review_text, opts):
    from draft.section import draft as draft_section
    backend = opts.get("backend")
    context = {
        "review_text": review_text,
        "retrieval": _retrieve_for_section(label, section_items, opts.get("restrict_works")) if opts.get("use_retrieval", True) else [],
        "style": _style_for_section(section_items, label, opts.get("style_profile")) if opts.get("use_style", True) else [],
    }
    sp = StepSpinner(f"drafting {label}")
    sp.start()
    t0 = time.perf_counter()
    text, words = "", 0
    try:
        drafted = draft_section(key, section_items, context, target=opts.get("targets", {}).get(key), backend=backend)
        text, words = drafted["text"], drafted["words"]
    finally:
        elapsed = time.perf_counter() - t0
        sp.done(f"{words} words ({elapsed:.0f}s)")
    works = [passage["base"] for passage in context["retrieval"]]
    return {"text": text, "words": words, "works": works}


def run(plan_items: list, assignment: dict, review_parsed: dict, opts: dict = None) -> dict:
    """Draft the full manuscript.

    Args:
        plan_items: All parsed plan items.
        assignment: Section assignment dict.
        review_parsed: Parsed review (from corpus/parse_review.py).
        opts: Options dict. Keys: backend, use_retrieval, use_style, restrict_works, targets.

    Returns:
        Dict with keys: sections (list of {key, label, text, words}), total_words, and works
        (the papers whose passages were retrieved, in the order first used).
    """
    from corpus.parse_review import full_prose

    given_opts = opts or {}
    word_targets = targets(given_opts.get("targets"))
    run_opts = dict(given_opts)
    run_opts["targets"] = word_targets
    review_text = full_prose(review_parsed)

    ui.step("Manuscript draft: step plan")
    to_write = 0
    for s in SECTIONS:
        section_items = items_for_section(s["key"], assignment, plan_items)
        ui.info(f"  {s['label']:<20} {len(section_items)} moves  ·  target {word_targets[s['key']]} words")
        if section_items:
            to_write += 1
    items.stage("Writing the sections")
    items.announce("total", to_write)

    sections_out, total = [], 0
    works = []
    for i, sec in enumerate(SECTIONS, 1):
        key, label = sec["key"], sec["label"]
        section_items = items_for_section(key, assignment, plan_items)
        ui.info(f"\n[{i}/{len(SECTIONS)}] {label}")
        if not section_items:
            ui.warn(f"No plan items assigned to {label}, skipping")
            sections_out.append({"key": key, "label": label, "text": "", "words": 0})
            continue
        items.announce("start", label)
        drafted = _draft_section(key, label, section_items, review_text, run_opts)
        items.announce("ok", label, f"{drafted['words']} words")
        total += drafted["words"]
        for base in drafted["works"]:
            if base not in works:
                works.append(base)
        sections_out.append({"key": key, "label": label, "text": drafted["text"], "words": drafted["words"]})

    return {"sections": sections_out, "total_words": total, "works": works}


def render_markdown(manuscript: dict) -> str:
    """Render assembled manuscript to markdown string."""
    parts = [f"## {s['label']}\n\n{s['text']}" for s in manuscript["sections"] if s["text"]]
    parts.append(f"\n---\n*Total: {manuscript['total_words']} words*")
    return "\n\n".join(parts)
