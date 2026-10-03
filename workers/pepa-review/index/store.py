"""Build and query the sum_-level embedding index, one record per paper
in data/index.json with its dense vector, retrieved by cosine or
BM25+dense RRF when rank_bm25 is installed.
"""
import json
import re

import config
from corpus.metadata import work_list
from corpus.parse_sum import parse_sum
from index.embeddings import embed

_CHECKPOINT_EVERY = 100
RETRIEVE_TOP_K = 8
RRF_K = 60
# Each paper's closest papers, written beside the index so a page can show them without loading it.
RELATED_FILE = config.DATA_DIR / "related.json"
RELATED_COUNT = 10
RELATED_ROWS_AT_ONCE = 1000


def build_index(force=False, progress_cb=None, status_cb=None):
    """Embed all sum_ briefs and persist to data/index.json.

    Skips papers already in the index unless force=True. Calls
    progress_cb(i, total, label) per paper and status_cb(msg) at phase changes.

    Returns:
        dict with keys "n_records" (total records now in the index) and
        "model_used" (the "provider/model_string" the index was built with).
    """
    existing = _load_raw() or {}
    existing_bases = {r["base"] for r in existing.get("records", [])}

    all_works = work_list()
    to_index = all_works if force else [w for w in all_works if w["base"] not in existing_bases]

    if not to_index:
        if existing.get("records") and not RELATED_FILE.exists():
            write_related(existing["records"], existing["vectors"])
        return {
            "n_records": len(existing.get("records", [])),
            "model_used": existing.get("model", ""),
        }

    base_records = [] if force else list(existing.get("records", []))
    base_vectors = [] if force else list(existing.get("vectors", []))

    embedded = _embed_new_works(to_index, base_records, base_vectors, progress_cb)
    new_records = embedded["records"]
    new_vectors = embedded["vectors"]
    model = embedded["model"]

    if force or not existing:
        records, vectors = new_records, new_vectors
    else:
        built_with = existing.get("model", "")
        if built_with and built_with != model:
            raise SystemExit(
                f"Index was built with {built_with} embeddings but the active "
                f"setting is {model}. Re-run: {config.COMMAND} index --force"
            )
        records = base_records + new_records
        vectors = base_vectors + new_vectors

    if status_cb:
        status_cb("saving index")
    _write_index(records, vectors, model)
    if status_cb:
        status_cb("finding related papers")
    write_related(records, vectors)
    return {"n_records": len(records), "model_used": model}


def write_related(records, vectors):
    """Record each paper's closest papers by cosine similarity, as {base: [[base, score], ...]}.

    The similarities are worked out a block of rows at a time, so a large library never holds
    the whole papers-by-papers table in memory.
    """
    import numpy as np
    matrix = np.array(vectors, dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    count = min(RELATED_COUNT, len(records) - 1)
    related = {}
    RELATED_FILE.parent.mkdir(parents=True, exist_ok=True)
    if count < 1:
        RELATED_FILE.write_text(json.dumps(related), encoding="utf-8")
        return
    for start in range(0, len(records), RELATED_ROWS_AT_ONCE):
        block = matrix[start:start + RELATED_ROWS_AT_ONCE] @ matrix.T
        for offset, scores in enumerate(block):
            scores[start + offset] = -1.0
            best = np.argpartition(scores, -count)[-count:]
            best = best[np.argsort(scores[best])[::-1]]
            related[records[start + offset]["base"]] = [[records[i]["base"], round(float(scores[i]), 3)] for i in best]
    RELATED_FILE.write_text(json.dumps(related), encoding="utf-8")


def _embed_new_works(to_index, base_records, base_vectors, progress_cb):
    """Embed each work not yet in the index, checkpointing along the way.

    Returns:
        dict with keys "records", "vectors", and "model" for the works
        embedded in this call.
    """
    new_records, new_vectors, model = [], [], ""
    for i, work in enumerate(to_index):
        if progress_cb:
            progress_cb(i + 1, len(to_index), work["authors"])
        parsed = parse_sum(work["sum_path"])
        text = _brief_text(parsed)
        embedded = embed([text])
        vecs = embedded["vectors"]
        model = embedded["model"]
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

    return {"records": new_records, "vectors": new_vectors, "model": model}


def retrieve(query, k=RETRIEVE_TOP_K, restrict_bases=None):
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

    q_vec = embed([query])["vectors"]
    q = np.array(q_vec[0], dtype=float)
    mat = np.array(vectors, dtype=float)
    sims = mat @ q / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-9)
    top = np.argsort(sims)[::-1][:k]
    return [dict(records[i], score=float(sims[i])) for i in top]


def retrieve_hybrid(query, k=RETRIEVE_TOP_K, restrict_bases=None):
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

    q_vec = embed([query])["vectors"]
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
    return _normalise_whitespace(quote) in _normalise_whitespace(source_text)


def _normalise_whitespace(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def _brief_text(parsed):
    parts = [
        parsed.get("title", ""),
        parsed.get("question", ""),
        parsed.get("arguments_text", ""),
        parsed.get("conclusions", ""),
    ]
    text = "\n\n".join(p for p in parts if p)
    return text[:5000]


def _rrf(rankings, rrf_k=RRF_K):
    from collections import defaultdict
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] += 1.0 / (rrf_k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)


def _write_index(records, vectors, model):
    provider = model.split("/", 1)[0] if model else ""
    dim = len(vectors[0]) if vectors else 0
    data = {
        "provider": provider,
        "model": model,
        "dim": dim,
        "records": records,
        "vectors": vectors,
    }
    config.INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.INDEX_FILE.write_text(json.dumps(data), encoding="utf-8")


def _load_raw():
    if not config.INDEX_FILE.exists():
        return None
    return json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))


def _require_index():
    idx = _load_raw()
    if not idx:
        raise SystemExit(f"No index found. Run: {config.COMMAND} index")
    return idx


def _check_provider(idx):
    """Refuse a query embedded by another provider or model than the one that built the index."""
    embed_cfg = config.embed_config()
    active = f"{embed_cfg['provider']}/{embed_cfg['model']}"
    built_with = idx.get("model", "")
    if built_with and embed_cfg["provider"] and built_with != active:
        raise SystemExit(
            f"Index was built with {built_with} embeddings but the active "
            f"setting is {active}. Re-run: {config.COMMAND} index --force"
        )
