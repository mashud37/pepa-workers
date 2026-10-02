"""Route generation calls to the configured backend: Claude, any server that accepts OpenAI's chat format, or the Cloud Run vLLM service."""
import config

DEFAULT_MAX_TOKENS = 4000


def complete(system: str, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, backend: str = None) -> str:
    """Route a completion request to the configured backend.

    Args:
        system: System prompt.
        prompt: User prompt.
        max_tokens: Maximum response tokens.
        backend: 'anthropic', 'openai-compatible' or 'vllm' (default: from config).

    Returns:
        Response text string.
    """
    chosen = backend or config.backend()
    if chosen == "openai-compatible":
        from backends import openai_client
        return openai_client.complete(system, prompt, max_tokens, config.llm_connection()["model"])
    if chosen == "vllm":
        from backends.vllm_client import complete as _complete
    else:
        from backends.anthropic_client import complete as _complete
    return _complete(system, prompt, max_tokens)
