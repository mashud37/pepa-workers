"""Route generation calls to the configured backend: Claude, or any server that accepts OpenAI's chat format."""
import config

DEFAULT_MAX_TOKENS = 4000


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, quality=False):
    """Send a completion. quality=True uses the quality model for the literature review."""
    models = config.model_names()
    model = models["quality"] if quality else models["fast"]
    if config.backend() == "openai-compatible":
        from backends import openai_client
        return openai_client.complete(system, prompt, max_tokens, model)
    from backends import anthropic_client
    return anthropic_client.complete(system, prompt, max_tokens=max_tokens, model=model)
