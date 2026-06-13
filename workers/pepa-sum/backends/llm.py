"""One entry point for text generation, routed to the configured backend.

`anthropic` (default) calls Claude Haiku; `cloudrun` calls the self-hosted
Qwen service. Callers use complete() and never know which is live.
"""
import config


def complete(system, prompt, max_tokens=2000):
    if config.backend() == "cloudrun":
        from backends.summarizer import summarize
        return summarize(system, prompt)
    from backends.anthropic_client import complete as _complete
    return _complete(system, prompt, max_tokens)
