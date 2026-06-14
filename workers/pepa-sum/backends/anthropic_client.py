"""Claude (Anthropic) client for the comprehension layer — the default backend.

Pay-per-use, so idle cost is zero; far better quality and speed than the
self-hosted CPU model. The API key comes from ANTHROPIC_API_KEY (env or
env.yaml). Retries transient overload/rate-limit a couple of times.
"""
import threading
import time

import config

_RETRYABLE = (429, 500, 502, 503, 529)

_lock = threading.Lock()
_cached = {"key": None, "client": None}


def _client():
    """One thread-safe client, reused across calls (and threads) so concurrent
    rundown batches share its connection pool instead of each opening a new one."""
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic package missing. Run: pip install -r requirements.txt")

    key = config.anthropic_api_key()
    if not key:
        raise SystemExit(
            "No ANTHROPIC_API_KEY. Set it in env.yaml or the ANTHROPIC_API_KEY env "
            "var (run: python manage.py install)."
        )

    with _lock:
        if _cached["client"] is None or _cached["key"] != key:
            _cached["key"] = key
            _cached["client"] = anthropic.Anthropic(api_key=key)
        return _cached["client"]


def complete(system, prompt, max_tokens=2000):
    client = _client()
    import anthropic

    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=config.anthropic_model(),
                max_tokens=max_tokens,
                temperature=0.2,
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
