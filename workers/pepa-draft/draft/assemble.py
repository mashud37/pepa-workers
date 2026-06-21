"""Orchestrate full manuscript drafting across all sections."""
import time

from cli import ui
from cli.progress import StepSpinner
from draft.sections import items_for_section
from draft.template import SECTIONS, targets


def _retrieve_for_section(label, items, restrict_works):
    sp = StepSpinner(f"retrieving literature ({label})")
    sp.start()
    passages = []
    try:
        from index.retrieve import retrieve
        query = " ".join(item["text"][:100] for item in items[:3])
        passages = retrieve(query, restrict_bases=restrict_works)
    except SystemExit:
        pass
    finally:
        sp.done(f"{len(passages)} passages")
    return passages


def _style_for_section(items, label, profile=None):
    try:
        from index.style import retrieve as style_retrieve
        query = items[0]["text"] if items else label
        return style_retrieve(query, profile=profile)
    except Exception:
        return []


def _draft_section(key, label, items, review_text, opts):
    from draft.section import draft as draft_section
    backend = opts.get("backend")
    context = {
        "review_text": review_text,
        "retrieval": _retrieve_for_section(label, items, opts.get("restrict_works")) if opts.get("use_retrieval", True) else [],
        "style": _style_for_section(items, label, opts.get("style_profile")) if opts.get("use_style", True) else [],
    }
    sp = StepSpinner(f"drafting {label}")
    sp.start()
    t0 = time.perf_counter()
    text, words = "", 0
    try:
        text, words = draft_section(key, items, context, target=opts.get("targets", {}).get(key), backend=backend)
    finally:
        elapsed = time.perf_counter() - t0
        sp.done(f"{words} words ({elapsed:.0f}s)")
    return text, words


def run(plan_items: list, assignment: dict, review_parsed: dict, opts: dict = None) -> dict:
    """Draft the full manuscript.

    Args:
        plan_items: All parsed plan items.
        assignment: Section assignment dict.
        review_parsed: Parsed review (from corpus/parse_review.py).
        opts: Options dict. Keys: backend, use_retrieval, use_style, restrict_works, targets.

    Returns:
        Dict with keys: sections (list of {key, label, text, words}), total_words.
    """
    from corpus.parse_review import full_prose

    opts = opts or {}
    word_targets = targets(opts.get("targets"))
    opts["targets"] = word_targets
    review_text = full_prose(review_parsed)

    ui.step("Manuscript draft — step plan")
    for s in SECTIONS:
        items = items_for_section(s["key"], assignment, plan_items)
        ui.info(f"  {s['label']:<20} {len(items)} moves  ·  target {word_targets[s['key']]} words")

    sections_out, total = [], 0
    for i, sec in enumerate(SECTIONS, 1):
        key, label = sec["key"], sec["label"]
        items = items_for_section(key, assignment, plan_items)
        ui.info(f"\n[{i}/{len(SECTIONS)}] {label}")
        if not items:
            ui.warn(f"No plan items assigned to {label} — skipping")
            sections_out.append({"key": key, "label": label, "text": "", "words": 0})
            continue
        text, words = _draft_section(key, label, items, review_text, opts)
        total += words
        sections_out.append({"key": key, "label": label, "text": text, "words": words})

    return {"sections": sections_out, "total_words": total}


def render_markdown(manuscript: dict) -> str:
    """Render assembled manuscript to markdown string."""
    parts = [f"## {s['label']}\n\n{s['text']}" for s in manuscript["sections"] if s["text"]]
    parts.append(f"\n---\n*Total: {manuscript['total_words']} words*")
    return "\n\n".join(parts)
