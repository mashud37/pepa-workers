"""Estimate what a paid command costs before it runs, from the size of the briefs it will send.
The console shows these estimates before every paid step.
"""
import config

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
# The instructions every call sends besides the briefs.
PROMPT_CHARS = 3000


def brief_chars(record):
    """How many characters one paper's brief adds to a prompt."""
    total = 0
    for field in ["authors", "title", "question", "arguments_text", "conclusions", "literature"]:
        total += len(record.get(field, "") or "")
    return total


def brief_chars_mean(records):
    """The mean brief size over the given papers, or 0 when there are none."""
    if not records:
        return 0
    total = 0
    for record in records:
        total += brief_chars(record)
    return total // len(records)


def price_of(model):
    """The model's (input, output) price per million tokens, or None when it is not known here."""
    for name, price in PRICES_PER_MILLION.items():
        if model.startswith(name):
            return price
    return None


def estimate(calls, quality):
    """The cost of a list of calls, each {"input_chars", "output_tokens"}, on the fast or quality model.

    Returns:
        dict with "calls", "input_tokens", "output_tokens", "model", and "dollars", None when the
        model's price is not known here; a model on this computer is priced at nothing.
    """
    models = config.model_names()
    model = models["quality"] if quality else models["fast"]
    input_tokens = 0
    output_tokens = 0
    for call in calls:
        input_tokens += (call["input_chars"] + PROMPT_CHARS) // CHARS_PER_TOKEN
        output_tokens += call["output_tokens"]
    price = price_of(model)
    dollars = None
    if price is not None:
        dollars = (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
    base_url = config.setting("llm_base_url") or ""
    if config.backend() == "openai-compatible" and ("localhost" in base_url or "127.0.0.1" in base_url):
        dollars = 0.0
    return {
        "calls": len(calls),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
        "dollars": dollars,
    }
