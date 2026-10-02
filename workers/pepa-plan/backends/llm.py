"""Route generation calls to the configured backend: Claude, or any server that accepts OpenAI's chat format."""
import config

DEFAULT_MAX_TOKENS = 4000


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, quality=False):
    """Send a completion. quality=True uses the quality model for outline,
    refine, and review; the default fast model labels moves."""
    settings = config.load()
    if settings["backend"] == "openai-compatible":
        from backends import openai_client
        return openai_client.complete(system, prompt, max_tokens, quality)["text"]
    from backends import anthropic_client
    model = settings["review_model"] if quality else settings["anthropic_model"]
    return anthropic_client.complete(system, prompt, max_tokens=max_tokens, model=model)
