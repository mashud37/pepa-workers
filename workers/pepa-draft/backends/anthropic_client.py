"""Claude (Anthropic) client — primary generation backend."""
import time

import config

_RETRYABLE = (429, 500, 502, 503, 529)


def _call_once(client, model, system, prompt, max_tokens):
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()


def complete(system: str, prompt: str, max_tokens: int = 4000, model: str = None) -> str:
    """Send a completion request to the Anthropic API.

    Args:
        system: System prompt.
        prompt: User prompt.
        max_tokens: Maximum response tokens.
        model: Model ID override (default: config.draft_model()).

    Returns:
        Response text string.
    """
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic package missing. Run: pip install -r requirements.txt")

    key = config.anthropic_api_key()
    if not key:
        raise SystemExit("No ANTHROPIC_API_KEY. Set it in secrets.yaml or env var.")

    _model = model or config.draft_model()
    client = anthropic.Anthropic(api_key=key)
    for attempt in range(3):
        try:
            return _call_once(client, _model, system, prompt, max_tokens)
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
