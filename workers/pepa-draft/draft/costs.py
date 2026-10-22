"""Estimate the most a first draft costs, from the plan items and review text each section's call sends.
The console shows this estimate before a draft runs.
"""
import config
from backends.anthropic_client import thinks
from corpus.parse_review import full_prose
from draft import prompt as P
from draft.sections import items_for_section
from draft.template import SECTIONS, targets

# List prices in US dollars per million tokens, input then output; a model missing here has no known price.
PRICES_PER_MILLION = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}
# A conservative count: the newer tokenizers split English into about three characters a token.
CHARS_PER_TOKEN = 3
# The most of the review, of each retrieved passage and of each style example one call sends.
REVIEW_CHARS = 2000
PASSAGE_CHARS = 400
STYLE_CHARS = 1500
# A section's call may write three tokens a word of its target, and a call to lengthen it as many again.
TOKENS_PER_TARGET_WORD = 6
# Thinking is billed as output; a model that thinks is allowed this much per call at medium effort.
THINKING_TOKENS_PER_CALL = 4000
LOCAL_ADDRESSES = [
    "localhost",
    "127.0.0.1",
]


def price_of(model):
    """The model's (input, output) price per million tokens, or None when it is not known here."""
    for name, price in PRICES_PER_MILLION.items():
        if model.startswith(name):
            return price
    return None


def draft_estimate(plan_items, assignment, review_parsed):
    """The most drafting every section with plan items can cost, at list price.

    Returns:
        dict with "sections", "input_tokens", "output_tokens", "model", "dollars" (None when the
        price is not known here, 0 for a server on this computer) and "upto".
    """
    word_targets = targets()
    review_chars = min(len(full_prose(review_parsed)), REVIEW_CHARS)
    context_chars = review_chars + config.RETRIEVAL_K * PASSAGE_CHARS + config.STYLE_K * STYLE_CHARS
    model = draft_model_name()
    thinking = 0
    if thinks(model):
        thinking = THINKING_TOKENS_PER_CALL
    input_chars = 0
    output_tokens = 0
    drafted = 0
    for section in SECTIONS:
        items = items_for_section(section["key"], assignment, plan_items)
        if not items:
            continue
        drafted += 1
        item_chars = sum(len(item["text"]) + len(item["move"]) for item in items)
        input_chars += 2 * (context_chars + item_chars + len(P.SYSTEM_DRAFT) + len(P.SECTION_PROMPT))
        output_tokens += word_targets[section["key"]] * TOKENS_PER_TARGET_WORD + 2 * thinking
    input_tokens = input_chars // CHARS_PER_TOKEN
    price = price_of(model)
    dollars = None
    if price is not None:
        dollars = (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
    if config.backend() == "openai-compatible":
        for address in LOCAL_ADDRESSES:
            if address in (config.get("llm_base_url") or ""):
                dollars = 0.0
    return {
        "sections": drafted,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
        "dollars": dollars,
        "upto": True,
    }


def draft_model_name():
    """The model the configured backend drafts with."""
    if config.backend() == "openai-compatible":
        return config.get("llm_model") or ""
    return config.draft_model()
