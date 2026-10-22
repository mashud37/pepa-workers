"""Estimate what the quality calls of an outline or a feedback run cost, from the size of the prompts they send.
The console shows these estimates before every paid step.
"""
import config
from backends.anthropic_client import thinks

# A conservative count: the newer tokenizers split English into about three characters a token.
CHARS_PER_TOKEN = 3
# Thinking is billed as output; a model that thinks is allowed this much per call at medium effort.
THINKING_TOKENS_PER_CALL = 4000
LOCAL_ADDRESSES = [
    "localhost",
    "127.0.0.1",
]


def thinking_tokens(model):
    """The output tokens one call to this model is expected to spend thinking."""
    if thinks(model):
        return THINKING_TOKENS_PER_CALL
    return 0


def estimate(calls):
    """The most a list of quality calls can cost, each {"input_chars", "output_tokens"}.

    Returns:
        dict with "calls", "input_tokens", "output_tokens", "model", "dollars" (None when the
        model's price is not known here, 0 for a server on this computer) and "upto".
    """
    model = config.model_names()["quality"] or ""
    input_tokens = 0
    output_tokens = 0
    for call in calls:
        input_tokens += call["input_chars"] // CHARS_PER_TOKEN
        output_tokens += call["output_tokens"] + thinking_tokens(model)
    price = config.price_per_mtok(model)
    dollars = None
    if price is not None:
        dollars = (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
    base_url = config.get("llm_base_url") or ""
    if config.load()["backend"] == "openai-compatible":
        for address in LOCAL_ADDRESSES:
            if address in base_url:
                dollars = 0.0
    return {
        "calls": len(calls),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
        "dollars": dollars,
        "upto": True,
    }
