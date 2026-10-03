"""Route generation calls to Claude or to any server that accepts OpenAI's chat format, including the self-hosted vLLM service."""
import config

DEFAULT_MAX_TOKENS = 4000


def complete(system: str, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, backend: str = None) -> str:
    """Route a completion request to the configured backend.

    Args:
        system: System prompt.
        prompt: User prompt.
        max_tokens: Maximum response tokens.
        backend: 'anthropic' or 'openai-compatible' (default: from config).

    Returns:
        Response text string.
    """
    chosen = backend or config.backend()
    if chosen == "openai-compatible":
        from backends import openai_client
        return openai_client.complete(system, prompt, max_tokens, config.llm_connection()["model"])
    from backends.anthropic_client import complete as _complete
    return _complete(system, prompt, max_tokens)
