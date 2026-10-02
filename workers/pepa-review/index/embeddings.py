"""Embed texts with the provider named in embed_provider: Gemini, Ollama, or any server that
accepts OpenAI's embeddings format.
"""
import json
import urllib.request

import config

TEXTS_PER_REQUEST = 10
NO_KEY = "no-key"


def _gemini(model, texts):
    import time
    import urllib.error
    key = config.setting("gemini_api_key")
    out = []
    for t in texts:
        url = (
            f"https://generativelanguage.googleapis.com/v1/models/"
            f"{model}:embedContent?key={key}"
        )
        body = {"model": f"models/{model}", "content": {"parts": [{"text": t}]}}
        data = json.dumps(body).encode()
        for attempt in range(5):
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    out.append(json.load(r)["embedding"]["values"])
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 503) and attempt < 4:
                    time.sleep(min(2 ** attempt, 60))
                    continue
                body_bytes = e.read()
                try:
                    detail = json.loads(body_bytes).get("error", {}).get("message", body_bytes.decode())
                except Exception:
                    detail = body_bytes.decode(errors="replace")
                raise RuntimeError(f"Gemini embed API {e.code}: {detail}")
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


def _compatible(model, texts):
    import openai
    client = openai.OpenAI(
        base_url=config.setting("embed_base_url"),
        api_key=config.setting("embed_api_key") or NO_KEY,
        timeout=300,
        max_retries=4,
    )
    out = []
    for start in range(0, len(texts), TEXTS_PER_REQUEST):
        chunk = texts[start:start + TEXTS_PER_REQUEST]
        try:
            reply = client.embeddings.create(model=model, input=chunk)
        except openai.APIError as error:
            raise RuntimeError(f"Embedding server error: {error}")
        for item in reply.data:
            out.append(item.embedding)
    return out


def embed(texts):
    """Embed a list of texts.

    Returns:
        dict with keys "vectors" (list of embedding vectors) and "model"
        (the "provider/model_string" that produced them).
    """
    embed_cfg = config.embed_config()
    provider = embed_cfg["provider"]
    model = embed_cfg["model"]
    if provider is None:
        raise SystemExit(config.EMBED_MISSING)
    if provider == "gemini":
        vectors = _gemini(model, texts)
    elif provider == "ollama":
        vectors = _ollama(config.setting("ollama_base_url"), model, texts)
    else:
        vectors = _compatible(model, texts)
    return {"vectors": vectors, "model": f"{provider}/{model}"}
