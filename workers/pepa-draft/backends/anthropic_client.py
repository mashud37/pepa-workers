"""Call Claude as the primary generation backend.
"""
import sys
import time

import config

_RETRYABLE = (429, 500, 502, 503, 529)
DEFAULT_MAX_TOKENS = 4000

# Older models do not think unless asked. Newer ones think before they answer, spending the same
# output limit, so they get room for thinking and a set effort.
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


def _send(client, model, system, messages, max_tokens):
    """One streamed request.

    Returns:
        dict with "text", the answer, and "truncated", True when it stopped at the output limit.
    """
    limit = max_tokens
    extra = {}
    if thinks(model):
        limit = max_tokens + THINKING_TOKENS
        extra = {"output_config": {"effort": EFFORT}}
    with client.messages.stream(
        model=model,
        max_tokens=limit,
        system=system,
        messages=messages,
        extra_body=extra,
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise SystemExit("The model declined to write this section.")
    text = "".join(b.text for b in msg.content if b.type == "text")
    return {"text": text, "truncated": msg.stop_reason == "max_tokens"}


def _send_with_retries(client, model, system, messages, max_tokens):
    """_send, tried again twice on a busy or unreachable server."""
    import anthropic
    for attempt in range(3):
        try:
            return _send(client, model, system, messages, max_tokens)
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


def complete(system: str, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, model: str = None) -> str:
    """Send a completion request to the Anthropic API, continuing the answer when it reaches the output limit.

    Args:
        system: System prompt.
        prompt: User prompt.
        max_tokens: Room for the answer; a model that thinks gets more for its thinking.
        model: Model ID override (default: config.draft_model()).

    Returns:
        Response text string.
    """
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic package missing. Run: pip install -r requirements.txt")

    key = config.get("anthropic_api_key")
    if not key:
        raise SystemExit("No ANTHROPIC_API_KEY. Set it in secrets.yaml or env var.")

    model = model or config.draft_model()
    client = anthropic.Anthropic(api_key=key)
    messages = [{"role": "user", "content": prompt}]
    parts = []
    for round_number in range(1 + CONTINUATIONS):
        reply = _send_with_retries(client, model, system, messages, max_tokens)
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
