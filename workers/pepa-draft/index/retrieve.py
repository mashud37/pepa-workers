"""Read-only cosine retrieval against a pepa-review embedding index."""
import json
from pathlib import Path

import config


def _load(index_path: Path = None) -> dict:
    p = index_path or config.review_index_file()
    if not p.exists():
        raise SystemExit(
            f"Review index not found at {p}.\n"
            "Build it in pepa-review with: python manage.py index\n"
            "Or set review_index in secrets.yaml."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def retrieve(query: str, k: int = None, restrict_bases: set = None, index_path: Path = None) -> list[dict]:
    """Return top-k records by cosine similarity.

    Args:
        query: Text to search for.
        k: Number of results (default: config.RETRIEVAL_K).
        restrict_bases: Optional set of citation keys to filter to.
        index_path: Override path to index.json.

    Returns:
        List of record dicts with added 'score' key.
    """
    import numpy as np
    k = k or config.RETRIEVAL_K
    idx = _load(index_path)
    records = idx["records"]
    vectors = idx["vectors"]

    if restrict_bases:
        pairs = [(r, v) for r, v in zip(records, vectors) if r["base"] in restrict_bases]
        if not pairs:
            return []
        records, vectors = zip(*pairs)

    q_vec = _embed_one(query, idx.get("provider", ""))
    q = np.array(q_vec, dtype=float)
    mat = np.array(vectors, dtype=float)
    sims = mat @ q / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-9)
    top = np.argsort(sims)[::-1][:k]
    return [dict(records[i], score=float(sims[i])) for i in top]


def _embed_one(text: str, provider: str) -> list[float]:
    provider_active, model = config.embed_config()
    if provider_active == "gemini":
        return _gemini_embed(text, model)
    if provider_active == "ollama":
        return _ollama_embed(text, model)
    raise SystemExit(
        "No embedding provider configured. Add gemini_api_key or ollama_base_url to secrets.yaml."
    )


def _gemini_embed(text: str, model: str) -> list[float]:
    import json as _json
    import urllib.request
    key = config.gemini_api_key()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={key}"
    body = _json.dumps({"model": f"models/{model}", "content": {"parts": [{"text": text}]}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return _json.loads(resp.read())["embedding"]["values"]


def _ollama_embed(text: str, model: str) -> list[float]:
    import json as _json
    import urllib.request
    base = config.ollama_base_url().rstrip("/")
    body = _json.dumps({"model": model, "prompt": text}).encode()
    req = urllib.request.Request(f"{base}/api/embeddings", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return _json.loads(resp.read())["embedding"]
