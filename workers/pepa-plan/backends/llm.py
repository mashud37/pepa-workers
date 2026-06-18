"""Route generation calls to the configured LLM backend."""
import config


def complete(system, prompt, max_tokens=4000, quality=False):
    """Send a completion. quality=True uses the review model (Sonnet) for outline,
    refine, and review; the default fast model (Haiku) labels moves."""
    from backends import anthropic_client
    model = config.review_model() if quality else config.anthropic_model()
    return anthropic_client.complete(system, prompt, max_tokens=max_tokens, model=model)
