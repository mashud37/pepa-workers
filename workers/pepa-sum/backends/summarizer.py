"""Client for the Cloud Run summariser service (stdlib HTTP, per policy).

POSTs {system, prompt} to {BASE_URL}/summarize?token=JOB_TOKEN and returns the
model's Markdown. The service runs the instruction-tuned model and scales to
zero between calls, so the first request after idle pays a cold start.
"""
import json
import urllib.error
import urllib.request

import config

# CPU generation on a cold instance is slow; give it room before giving up.
_TIMEOUT = 900


def summarize(system, prompt):
    base = config.base_url()
    token = config.job_token()
    if not base:
        raise SystemExit(
            "No summariser endpoint configured. Deploy the service "
            "(python manage.py deploy) or set BASE_URL in env.yaml."
        )

    url = f"{base.rstrip('/')}/summarize?token={token}"
    payload = json.dumps({"system": system, "prompt": prompt}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Summariser returned HTTP {e.code}: {e.reason}. "
                         "Check the token and that the service is deployed.")
    except urllib.error.URLError as e:
        raise SystemExit(f"Could not reach the summariser at {base}: {e.reason}.")

    summary = (data.get("summary") or "").strip()
    if not summary:
        raise SystemExit("Summariser returned an empty response.")
    return summary
