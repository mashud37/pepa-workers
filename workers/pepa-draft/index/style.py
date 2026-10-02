"""Author style index: embed writing samples, retrieve by cosine similarity."""
import json
from pathlib import Path

import config


def build(sample_paths: list[Path], force: bool = False, profile: str = None) -> int:
    """Embed writing samples and save to the profile's style index.

    Args:
        sample_paths: List of text file paths.
        force: Rebuild all, even if already indexed.
        profile: Profile name (default: active profile).

    Returns:
        Total number of paragraphs indexed.
    """
    model = active_model()
    existing = _load(profile)
    if force or not existing:
        existing = {"records": [], "vectors": []}
    _check_model(existing, model)
    existing_paths = {r["path"] for r in existing["records"]}

    records, vectors = list(existing["records"]), list(existing["vectors"])

    for path in sample_paths:
        if not force and str(path) in existing_paths:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.split()) >= 20]
        for para in paragraphs:
            vec = _embed_one(para)
            records.append({"path": str(path), "text": para})
            vectors.append(vec)

    data = {"model": model, "records": records, "vectors": vectors}
    path = config.style_index_file(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return len(records)


def retrieve(query: str, k: int = None, profile: str = None) -> list[str]:
    """Return k most similar writing sample paragraphs from a style profile.

    Args:
        query: Context text for similarity search.
        k: Number of samples (default: config.STYLE_K).
        profile: Profile name (default: active profile).

    Returns:
        List of paragraph strings.
    """
    import numpy as np
    k = k or config.STYLE_K
    idx = _load(profile)
    if not idx or not idx["records"]:
        return []
    _check_model(idx, active_model())
    q = np.array(_embed_one(query), dtype=float)
    mat = np.array(idx["vectors"], dtype=float)
    sims = mat @ q / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-9)
    top = np.argsort(sims)[::-1][:k]
    return [idx["records"][i]["text"] for i in top]


def list_samples(profile: str = None) -> list[str]:
    idx = _load(profile)
    if not idx:
        return []
    return sorted({r["path"] for r in idx["records"]})


def active_model() -> str:
    """The provider and model the style index embeds with now, as "provider/model"."""
    embed = config.embed_config()
    if embed["provider"] is None:
        raise SystemExit(
            "No embedding provider configured. Set embed_provider in secrets.yaml (gemini, ollama, "
            "or openai-compatible) and its key or address."
        )
    return f"{embed['provider']}/{embed['model']}"


def _check_model(idx: dict, model: str) -> None:
    built_with = idx.get("model")
    if built_with and built_with != model:
        raise SystemExit(
            f"This style profile was built with {built_with} embeddings but the active setting is "
            f"{model}. Rebuild it: python manage.py style build"
        )


def _embed_one(text: str) -> list[float]:
    from index.retrieve import embed_text
    provider, model = active_model().split("/", 1)
    return embed_text(text, provider, model)


def _load(profile: str = None) -> dict | None:
    p = config.style_index_file(profile)
    if not p.exists():
        # fall back to legacy file for the default profile
        if (profile is None or profile == "default") and config.STYLE_INDEX_FILE.exists():
            return json.loads(config.STYLE_INDEX_FILE.read_text(encoding="utf-8"))
        return None
    return json.loads(p.read_text(encoding="utf-8"))

