"""Route generation calls to the configured LLM backend."""
import config

DEFAULT_MAX_TOKENS = 4000


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, quality=False):
    """Send a completion. quality=True uses the review model (Sonnet, WS1)."""
    from backends import anthropic_client
    model = config.setting("review_model") if quality else config.setting("anthropic_model")
    return anthropic_client.complete(system, prompt, max_tokens=max_tokens, model=model)
