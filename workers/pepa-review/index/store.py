"""Build and query the sum_-level embedding index.

Index unit: one sum_ brief per paper. Records stored in data/index.json alongside
their dense vectors, stamped with provider/model/dim. Cosine retrieval is the
default; BM25+dense RRF is available when rank_bm25 is installed.

Adapted from cli-chat/cli/projects.py.
"""
import json
import re
import config
from index.embeddings import embed
from corpus.metadata import work_list
from corpus.parse_sum import parse_sum


_CHECKPOINT_EVERY = 100


def build_index(force=False, progress_cb=None, status_cb=None):
    """Embed all sum_ briefs and persist to data/index.json.

    Skips papers already in the index unless force=True. Calls
    progress_cb(i, total, label) per paper and status_cb(msg) at phase changes.
    Returns (total_records, model_string).
    """
    existing = _load_raw() or {}
    existing_bases = {r["base"] for r in existing.get("records", [])}

    all_works = work_list()
    to_index = all_works if force else [w for w in all_works if w["base"] not in existing_bases]

    if not to_index:
        return len(existing.get("records", [])), existing.get("model", "")

    base_records = [] if force else list(existing.get("records", []))
    base_vectors = [] if force else list(existing.get("vectors", []))

    new_records, new_vectors, model = [], [], ""
    for i, work in enumerate(to_index):
        if progress_cb:
            progress_cb(i + 1, len(to_index), work["authors"])
        parsed = parse_sum(work["sum_path"])
        text = _brief_text(parsed)
        vecs, model = embed([text])
        new_records.append({
            "base":           work["base"],
            "authors":        work["authors"],
            "title":          work["title"],
            "sum_path":       work["sum_path"],
            "para_path":      work["para_path"],
            "quote_path":     work["quote_path"],
            "text":           text,
            "question":       parsed.get("question", ""),
            "arguments_text": parsed.get("arguments_text", ""),
            "conclusions":    parsed.get("conclusions", ""),
            "literature":     parsed.get("literature", ""),
        })
        new_vectors.append(vecs[0])

        if (i + 1) % _CHECKPOINT_EVERY == 0:
            _write_index(base_records + new_records, base_vectors + new_vectors, model)

    provider = model.split("/", 1)[0]

    if force or not existing:
        records, vectors = new_records, new_vectors
    else:
        cur_provider = existing.get("provider", "")
        if cur_provider and cur_provider != provider:
            raise SystemExit(
                f"Index was built with '{cur_provider}' embeddings but the active "
                f"provider is now '{provider}'. Re-run: python manage.py index --force"
            )
        records = base_records + new_records
        vectors = base_vectors + new_vectors

    if status_cb:
        status_cb("saving index")
    _write_index(records, vectors, model)
    return len(records), model


def retrieve(query, k=8, restrict_bases=None):
    """Return top-k records by cosine similarity to query.

    restrict_bases: optional set of base strings to filter to.
    Each record is a dict with an added 'score' key.
    """
    import numpy as np
    idx = _require_index()
    _check_provider(idx)

    records = idx["records"]
    vectors = idx["vectors"]

    if restrict_bases:
        pairs = [(r, v) for r, v in zip(records, vectors) if r["base"] in restrict_bases]
        if not pairs:
            return []
        records, vectors = zip(*pairs)

    q_vec, _ = embed([query])
    q = np.array(q_vec[0], dtype=float)
    mat = np.array(vectors, dtype=float)
    sims = mat @ q / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-9)
    top = np.argsort(sims)[::-1][:k]
    return [dict(records[i], score=float(sims[i])) for i in top]


def retrieve_hybrid(query, k=8, restrict_bases=None):
    """BM25 + dense RRF. Falls back to cosine-only if rank_bm25 is not installed."""
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return retrieve(query, k, restrict_bases)

    import numpy as np
    idx = _require_index()
    _check_provider(idx)

    records = idx["records"]
    vectors = idx["vectors"]

    if restrict_bases:
        pairs = [(r, v) for r, v in zip(records, vectors) if r["base"] in restrict_bases]
        if not pairs:
            return []
        records, vectors = zip(*pairs)

    q_vec, _ = embed([query])
    q = np.array(q_vec[0], dtype=float)
    mat = np.array(vectors, dtype=float)
    sims = mat @ q / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-9)
    dense_rank = list(np.argsort(sims)[::-1])

    tokenized = [r["text"].lower().split() for r in records]
    bm25_scores = BM25Okapi(tokenized).get_scores(query.lower().split())
    bm25_rank = list(np.argsort(bm25_scores)[::-1])

    fused_indices = _rrf([dense_rank, bm25_rank])[:k]
    return [dict(records[i], score=float(sims[i])) for i in fused_indices]


def verify_quote(quote, source_text):
    """Return True if quote appears verbatim (whitespace-insensitive) in source_text."""
    def norm(s):
        return re.sub(r"\s+", " ", s).strip().lower()
    return norm(quote) in norm(source_text)


def _brief_text(parsed):
    parts = [
        parsed.get("title", ""),
        parsed.get("question", ""),
        parsed.get("arguments_text", ""),
        parsed.get("conclusions", ""),
    ]
    text = "\n\n".join(p for p in parts if p)
    return text[:5000]


def _rrf(rankings, rrf_k=60):
    from collections import defaultdict
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] += 1.0 / (rrf_k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)


def _write_index(records, vectors, model):
    provider = model.split("/", 1)[0] if model else ""
    dim = len(vectors[0]) if vectors else 0
    data = {"provider": provider, "model": model, "dim": dim,
            "records": records, "vectors": vectors}
    config.INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.INDEX_FILE.write_text(json.dumps(data), encoding="utf-8")


def _load_raw():
    if not config.INDEX_FILE.exists():
        return None
    return json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))


def _require_index():
    idx = _load_raw()
    if not idx:
        raise SystemExit("No index found. Run: python manage.py index")
    return idx


def _check_provider(idx):
    provider, _ = config.embed_config()
    cur = idx.get("provider", "")
    if cur and provider and cur != provider:
        raise SystemExit(
            f"Index was built with '{cur}' embeddings but the active "
            f"provider is now '{provider}'. Re-run: python manage.py index --force"
        )
