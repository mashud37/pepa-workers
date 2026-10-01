"""Call the Cloud Run vLLM service as the bulk generation backend.
"""
import json
import time
import urllib.error
import urllib.request

import config

_TIMEOUT = 300
_READY_WAIT = 280
DEFAULT_MAX_TOKENS = 4000


def _vllm_ready(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url + "/healthz", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def complete(system: str, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, model: str = None) -> str:
    """Send a completion request to the vLLM proxy service.

    Args:
        system: System prompt.
        prompt: User prompt.
        max_tokens: Maximum response tokens.
        model: Ignored (model is set on the service).

    Returns:
        Response text string.
    """
    base = config.get("vllm_base_url")
    token = config.get("vllm_token")
    if not base:
        raise SystemExit("No vLLM service URL. Set vllm_base_url in secrets.yaml.")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    body = json.dumps({"messages": messages}).encode("utf-8")
    url = f"{base.rstrip('/')}/generate?token={token}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})

    deadline = time.time() + _READY_WAIT
    while True:
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read())["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 503 and time.time() < deadline:
                time.sleep(5)
                continue
            body_text = e.read().decode("utf-8", "replace")[:300]
            raise SystemExit(f"vLLM service error {e.code}: {body_text}")
        except urllib.error.URLError as e:
            raise SystemExit(f"Could not reach vLLM service: {e}")
