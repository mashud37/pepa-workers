"""Route text generation to the configured backend: `anthropic` calls Claude
Haiku, `cloudrun` calls the self-hosted Qwen service. Callers call complete()
without knowing which is live.
"""
import config

DEFAULT_MAX_TOKENS = 2000


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, flag_truncation=False):
    if config.load('BACKEND') == "cloudrun":
        from backends.summarizer import summarize
        return summarize(system, prompt)
    from backends.anthropic_client import complete as _complete
    return _complete(system, prompt, max_tokens, flag_truncation=flag_truncation)
