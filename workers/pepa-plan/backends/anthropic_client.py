"""Claude (Anthropic) client — default generation backend.

Adapted from pepa-sum/backends/anthropic_client.py.
"""
import config


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
    # max_retries lets the SDK back off (with jitter) on 429/5xx — important
    # under the concurrent move-labelling pool, where 429s are more likely.
    client = anthropic.Anthropic(api_key=key, max_retries=5)
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
        raise SystemExit(f"Anthropic API error {status}: {getattr(e, 'message', e)}")
    except anthropic.APIConnectionError as e:
        raise SystemExit(f"Could not reach the Anthropic API: {e}")
