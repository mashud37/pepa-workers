"""Read-only cosine retrieval against a pepa-review embedding index."""
import json
from pathlib import Path

import config

NO_KEY = "no-key"
# pepa-review keeps the index's vectors beside it, in index_vectors.npy.
VECTORS_ENDING = "_vectors.npy"


def _load(index_path: Path = None) -> dict:
    p = index_path or config.review_index_file()
    if not p.exists():
        raise SystemExit(
            f"Review index not found at {p}.\n"
            f"Build it in pepa-review with: {config.REVIEW_COMMAND} index\n"
            "Or set review_index in secrets.yaml."
        )
    import numpy as np
    index = json.loads(p.read_text(encoding="utf-8"))
    if "vectors" not in index:
        index["vectors"] = np.load(p.with_name(p.stem + VECTORS_ENDING))
    return index


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

    q_vec = _embed_one(query, idx)
    q = np.array(q_vec, dtype=float)
    mat = np.array(vectors, dtype=float)
    sims = mat @ q / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-9)
    top = np.argsort(sims)[::-1][:k]
    return [dict(records[i], score=float(sims[i])) for i in top]


def _embed_one(text: str, index: dict) -> list[float]:
    """Embed the query with the model that built the index, so both sides of the comparison match."""
    provider = index.get("provider", "")
    model = index.get("model", "").split("/", 1)[-1]
    if provider not in config.EMBED_NEEDS:
        raise SystemExit(
            f"The review index does not name its embedding model. Rebuild it in pepa-review: {config.REVIEW_COMMAND} index --force"
        )
    needed = config.EMBED_NEEDS[provider]
    if not config.get(needed):
        raise SystemExit(f"The review index was built with {provider} embeddings. Add {needed} to secrets.yaml.")
    return embed_text(text, provider, model)


def embed_text(text: str, provider: str, model: str) -> list[float]:
    """Embed one text with the named provider and model."""
    if provider == "gemini":
        return _gemini_embed(text, model)
    if provider == "ollama":
        return _ollama_embed(text, model)
    return _compatible_embed(text, model)


def _compatible_embed(text: str, model: str) -> list[float]:
    import openai
    client = openai.OpenAI(
        base_url=config.get("embed_base_url"),
        api_key=config.get("embed_api_key") or NO_KEY,
        timeout=60,
        max_retries=4,
    )
    try:
        reply = client.embeddings.create(model=model, input=[text])
    except openai.APIError as error:
        raise SystemExit(f"Embedding server error: {error}")
    return reply.data[0].embedding


def _gemini_embed(text: str, model: str) -> list[float]:
    import json as _json
    import urllib.request
    key = config.get("gemini_api_key")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={key}"
    body = _json.dumps({"model": f"models/{model}", "content": {"parts": [{"text": text}]}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return _json.loads(resp.read())["embedding"]["values"]


def _ollama_embed(text: str, model: str) -> list[float]:
    import json as _json
    import urllib.request
    base = config.get("ollama_base_url").rstrip("/")
    body = _json.dumps({"model": model, "prompt": text}).encode()
    req = urllib.request.Request(f"{base}/api/embeddings", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return _json.loads(resp.read())["embedding"]
