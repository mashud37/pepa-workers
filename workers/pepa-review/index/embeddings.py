"""Embed texts via Gemini (default) or Ollama — stdlib HTTP only.

Adapted from cli-chat/backends/embeddings.py. Provider is determined by config:
Ollama wins if ollama_base_url is set; Gemini is the default with gemini_api_key.
"""
import json
import urllib.request
import config


def _gemini(model, texts):
    import urllib.error
    key = config.gemini_api_key()
    out = []
    for t in texts:
        url = (
            f"https://generativelanguage.googleapis.com/v1/models/"
            f"{model}:embedContent?key={key}"
        )
        body = {"model": f"models/{model}", "content": {"parts": [{"text": t}]}}
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out.append(json.load(r)["embedding"]["values"])
        except urllib.error.HTTPError as e:
            body_bytes = e.read()
            try:
                detail = json.loads(body_bytes).get("error", {}).get("message", body_bytes.decode())
            except Exception:
                detail = body_bytes.decode(errors="replace")
            raise SystemExit(f"Gemini embed API {e.code}: {detail}")
    return out


def _ollama(base_url, model, texts):
    base = base_url.rstrip("/")
    out = []
    for t in texts:
        body = {"model": model, "prompt": t}
        req = urllib.request.Request(
            base + "/api/embeddings",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            out.append(json.load(r)["embedding"])
    return out


def embed(texts):
    """Embed a list of texts. Returns (vectors, provider/model_string)."""
    provider, model = config.embed_config()
    if provider is None:
        raise SystemExit(
            "No embedding provider configured.\n"
            "Add gemini_api_key to secrets.yaml or set the GEMINI_API_KEY env var.\n"
            "Run: python manage.py install"
        )
    if provider == "gemini":
        return _gemini(model, texts), f"gemini/{model}"
    return _ollama(config.ollama_base_url(), model, texts), f"ollama/{model}"
