"""Draft one manuscript section with word-count control."""
import config
from draft import prompt as P
from draft import word_count as wc
from draft.template import section_label


def _build_prompt(section_key, plan_items, context, target):
    label = section_label(section_key)
    n_paragraphs = max(1, round(target / 200))
    words_per_para = target // n_paragraphs
    system = P.SYSTEM_DRAFT.format(
        target_words=target, n_paragraphs=n_paragraphs, words_per_para=words_per_para
    )
    parts = []
    if context.get("style"):
        parts.append(P.STYLE_PREAMBLE.format(examples="\n\n".join(context["style"])))
    if context.get("retrieval"):
        passages = "\n\n".join(
            f"[{r.get('authors', '')}] {r.get('text', '')[:400]}" for r in context["retrieval"]
        )
        parts.append(P.RETRIEVAL_PREAMBLE.format(passages=passages))
    plan_text = "\n".join(
        f"{item['index']}. [{item['move']}]: {item['text']}" for item in plan_items
    )
    review_ctx = f"Literature review context:\n{context.get('review_text', '')[:2000]}\n"
    user = "".join(parts) + P.SECTION_PROMPT.format(
        section_label=label, review_context=review_ctx, plan_items=plan_text
    )
    return {"system": system, "user": user, "label": label}


def draft(section_key: str, plan_items: list, context: dict = None, target: int = None, backend: str = None) -> dict:
    """Draft a single manuscript section.

    Args:
        section_key: Section key (e.g. 'introduction').
        plan_items: Plan items assigned to this section.
        context: Dict with optional keys: review_text, retrieval, style.
        target: Target word count (default: config.SECTION_TARGETS[section_key]).
        backend: LLM backend ('anthropic' or 'openai-compatible').

    Returns:
        Dict with keys text and words.
    """
    from backends import llm

    context = context or {}
    target = target or config.SECTION_TARGETS.get(section_key, 500)
    prompt = _build_prompt(section_key, plan_items, context, target)
    system, user, label = prompt["system"], prompt["user"], prompt["label"]

    text = llm.complete(system, user, max_tokens=target * 3, backend=backend)
    actual = wc.count(text)

    tolerance = config.WORD_COUNT_TOLERANCE
    if actual > target * (1 + tolerance):
        text = wc.trim_to_target(text, target)
        actual = wc.count(text)

    if actual < target * (1 - tolerance) and plan_items:
        deficit = target - actual
        expand = P.EXPAND_PROMPT.format(
            section_label=label, current_words=actual, target_words=target, deficit=deficit
        )
        addition = llm.complete(system, expand, max_tokens=deficit * 3, backend=backend)
        text = text.rstrip() + "\n\n" + addition.strip()
        actual = wc.count(text)

    return {"text": text, "words": actual}
