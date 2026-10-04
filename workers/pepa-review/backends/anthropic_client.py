"""Call Claude, Anthropic's API, as the default generation backend."""
import time

import config

_RETRYABLE = (429, 500, 502, 503, 529)
DEFAULT_MAX_TOKENS = 4000

# Models that still take a sampling temperature; newer ones refuse one and run on their default.
TEMPERATURE = 0.3
TEMPERATURE_MODELS = (
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-opus-4-6",
)


def _sampling(model):
    """The temperature to send for this model, as request fields; empty for a model that refuses one."""
    if model.startswith(TEMPERATURE_MODELS):
        return {"temperature": TEMPERATURE}
    return {}


def complete(system, prompt, max_tokens=DEFAULT_MAX_TOKENS, model=None):
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

    _model = model or config.setting("anthropic_model")
    client = anthropic.Anthropic(api_key=key)
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                extra_body=_sampling(_model),
            )
            return "".join(
                b.text for b in msg.content if getattr(b, "type", None) == "text"
            ).strip()
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
