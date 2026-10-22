"""Call Claude, Anthropic's API, as the default generation backend."""
import sys
import time

import config

_RETRYABLE = (429, 500, 502, 503, 529)
DEFAULT_MAX_TOKENS = 4000

# Older models take a sampling temperature and do not think unless asked. Newer ones think before
# they answer, spending the same output limit, so they get room for thinking and a set effort.
TEMPERATURE = 0.3
OLDER_MODELS = (
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-opus-4-6",
)
THINKING_TOKENS = 16000
EFFORT = "medium"

# A reply that still reaches its limit is continued in a follow-up turn, at most this many times.
CONTINUATIONS = 2
CONTINUE_PROMPT = "You reached the length limit. Continue from where the text above ends, starting a new paragraph, without repeating anything and without any preamble."


def whole_paragraphs(text):
    """The text up to its last finished paragraph, so a continuation starts cleanly on a new one."""
    end = text.rstrip().rfind("\n\n")
    if end == -1:
        return text.strip()
    return text[:end].strip()


def thinks(model):
    """Whether this model thinks before it answers, spending output tokens on it."""
    return not model.startswith(OLDER_MODELS)


def _sampling(model):
    """The extra request fields for this model: a temperature for an older model, an effort for a newer one."""
    if thinks(model):
        return {"output_config": {"effort": EFFORT}}
    return {"temperature": TEMPERATURE}


def _output_limit(model, answer_tokens):
    """The output limit for this model: the answer's own room, plus room for thinking when it thinks."""
    if thinks(model):
        return answer_tokens + THINKING_TOKENS
    return answer_tokens


def _send(client, model, system, messages, max_tokens):
    """One streamed request, retried on a busy or unreachable server.

    Returns:
        dict with "text", the answer, and "truncated", True when it stopped at the output limit.
    """
    import anthropic
    for attempt in range(3):
        try:
            with client.messages.stream(
                model=model,
                max_tokens=_output_limit(model, max_tokens),
                system=system,
                messages=messages,
                extra_body=_sampling(model),
            ) as stream:
                msg = stream.get_final_message()
            if msg.stop_reason == "refusal":
                raise SystemExit("The model declined to answer this request.")
            text = "".join(b.text for b in msg.content if b.type == "text")
            return {"text": text, "truncated": msg.stop_reason == "max_tokens"}
        except anthropic.APIStatusError as e:
            status = getattr(e, "status_code", None)
            if status in _RETRYABLE and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"Anthropic API error {status}: {getattr(e, 'message', e)}")
        except anthropic.APIConnectionError as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"Could not reach the Anthropic API: {e}")


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, model=None):
    """Send one prompt and return the whole answer, continuing it when it reaches the output limit."""
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic package missing. Run: pip install -r requirements.txt")

    key = config.setting("anthropic_api_key")
    if not key:
        raise SystemExit(
            "No ANTHROPIC_API_KEY. Set it in secrets.yaml or the ANTHROPIC_API_KEY env "
            f"var. Run: {config.COMMAND} install"
        )

    model = model or config.setting("anthropic_model")
    client = anthropic.Anthropic(api_key=key)
    messages = [{"role": "user", "content": prompt}]
    parts = []
    for round_number in range(1 + CONTINUATIONS):
        reply = _send(client, model, system, messages, max_tokens)
        kept = whole_paragraphs(reply["text"])
        last_round = round_number == CONTINUATIONS
        if not reply["truncated"] or last_round or not kept:
            parts.append(reply["text"].strip())
            break
        parts.append(kept)
        messages.append({"role": "assistant", "content": kept})
        messages.append({"role": "user", "content": CONTINUE_PROMPT})
    if reply["truncated"]:
        print("The model stopped at its length limit; the text ends where it stopped.", file=sys.stderr)
    return "\n\n".join(parts)
