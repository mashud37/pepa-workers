"""Route generation calls to the configured LLM backend."""
import config

DEFAULT_MAX_TOKENS = 4000


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, quality=False):
    """Send a completion. quality=True uses the review model (Sonnet) for outline,
    refine, and review; the default fast model (Haiku) labels moves."""
    from backends import anthropic_client
    settings = config.load()
    model = settings["review_model"] if quality else settings["anthropic_model"]
    return anthropic_client.complete(system, prompt, max_tokens=max_tokens, model=model)
