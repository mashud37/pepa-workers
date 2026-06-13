"""Claude (Anthropic) client — default generation backend.

Adapted from pepa-sum/backends/anthropic_client.py.
"""
import time
import config

_RETRYABLE = (429, 500, 502, 503, 529)


def complete(system, prompt, max_tokens=4000, model=None):
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic package missing. Run: pip install -r requirements.txt")

    key = config.anthropic_api_key()
    if not key:
        raise SystemExit(
            "No ANTHROPIC_API_KEY. Set it in secrets.yaml or the ANTHROPIC_API_KEY env "
            "var. Run: python manage.py install"
        )

    _model = model or config.anthropic_model()
    client = anthropic.Anthropic(api_key=key)
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=_model,
                max_tokens=max_tokens,
                temperature=0.3,
                system=system,
                messages=[{"role": "user", "content": prompt}],
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
