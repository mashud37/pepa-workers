"""Route text generation to Claude or to any server that accepts OpenAI's chat format, including
the self-hosted Cloud Run service. Callers call complete() without knowing which is live.
"""
import config

DEFAULT_MAX_TOKENS = 2000


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, flag_truncation=False):
    if config.load('BACKEND') == "openai-compatible":
        from backends import openai_client
        from backends.anthropic_client import Truncated
        reply = openai_client.complete(system, prompt, max_tokens)
        if flag_truncation and reply["truncated"]:
            raise Truncated(reply["text"])
        return reply["text"]
    from backends.anthropic_client import complete as _complete
    return _complete(system, prompt, max_tokens, flag_truncation=flag_truncation)
