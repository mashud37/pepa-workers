"""Unified LLM interface: route to configured backend."""
import config


def complete(system: str, prompt: str, max_tokens: int = 4000, backend: str = None) -> str:
    """Route a completion request to the configured backend.

    Args:
        system: System prompt.
        prompt: User prompt.
        max_tokens: Maximum response tokens.
        backend: 'anthropic' or 'vllm' (default: from config).

    Returns:
        Response text string.
    """
    b = backend or config.get("backend", "anthropic")
    if b == "vllm":
        from backends.vllm_client import complete as _complete
    else:
        from backends.anthropic_client import complete as _complete
    return _complete(system, prompt, max_tokens)
