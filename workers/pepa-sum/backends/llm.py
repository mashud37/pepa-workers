"""Route text generation to the configured backend: Claude, any server that accepts OpenAI's
chat format, or the self-hosted Cloud Run service. Callers call complete() without knowing which is live.
"""
import config

DEFAULT_MAX_TOKENS = 2000


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, flag_truncation=False):
    backend = config.load('BACKEND')
    if backend == "cloudrun":
        from backends.summarizer import summarize
        return summarize(system, prompt)
    if backend == "openai-compatible":
        from backends import openai_client
        from backends.anthropic_client import Truncated
        reply = openai_client.complete(system, prompt, max_tokens)
        if flag_truncation and reply["truncated"]:
            raise Truncated(reply["text"])
        return reply["text"]
    from backends.anthropic_client import complete as _complete
    return _complete(system, prompt, max_tokens, flag_truncation=flag_truncation)
