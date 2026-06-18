"""Consensus clustering of indexed works (cs_ir_stats_reference §2, §3, §5).

Pure clustering math shared by the corpus map (cli/map.py) and the targeted
sub-clustering used during literature-review selection (cli/review.py). No CLI or
LLM concerns live here.

Pipeline:
  1. Ensemble features — dense embeddings + title TF-IDF->SVD + literature TF-IDF->SVD (§3.1).
  2. UMAP reduction to a low-dim cosine manifold (§5.4).
  3. Parameter selection by silhouette over a min_cluster_size band (§2).
  4. Consensus clustering — HDBSCAN + spherical k-means + Ward fused via a co-association
     matrix; final labels by average-linkage agglomerative on (1 - C) (§2.4/§2.6).
  5. Confidence-aware assignment from the co-association profile (§2.3).
  6. c-TF-IDF per thread (§3.5) for naming and near-duplicate-thread merging.

Each stage degrades gracefully when an optional library is absent (dependencies.md).
"""
import numpy as np

import config


def cluster_records(records, vecs, n_threads=None):
    """Cluster `records` (with parallel `vecs`) into thematic threads.

    Returns a dict: primary/secondary map record index -> thread id (secondary is
    None unless a work bridges two threads), outliers is a list of record indices,
    terms maps thread id -> distinctive c-TF-IDF terms, strength maps record index ->
    mean co-association, vecs_norm is the row-normalised vector matrix (for centrality),
    and stats carries silhouette + mean consensus.
    """
    vecs = np.asarray(vecs, dtype=float)
    vecs_norm = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
    texts = [pool_text(r) for r in records]

    try:
        features = ensemble_features(records, vecs_norm)
    except Exception:
        features = vecs_norm

    coords = reduce_dims(features)
    min_cs, k, sil = select_params(coords, n_threads)
    labels, coassoc, strength = consensus_cluster(coords, k, min_cs)
    primary, secondary, outliers = assign(coassoc, labels)
    primary, secondary, terms = merge_threads(primary, secondary, coords, texts)

    return {
        "primary":   primary,
        "secondary": secondary,
        "outliers":  outliers,
        "terms":     terms,
        "strength":  strength,
        "vecs_norm": vecs_norm,
        "stats": {
            "silhouette": sil,
            "consensus":  float(np.mean(list(strength.values()))) if strength else 0.0,
        },
    }


# ── features ────────────────────────────────────────────────────────────────

def pool_text(r):
    return " ".join(p for p in (r.get("title", ""), r.get("question", ""),
                                r.get("arguments_text", "")) if p)


def ensemble_features(records, vecs_norm):
    """Dense embeddings (weighted) + title TF-IDF->SVD + literature TF-IDF->SVD (§3.1, §2.1)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.preprocessing import normalize

    titles = [r.get("title", r["base"]) for r in records]
    literature = [r.get("literature", "") for r in records]

    def tfidf_svd(texts, n_components=40):
        vec = TfidfVectorizer(stop_words="english", min_df=2, max_df=0.9, ngram_range=(1, 2))
        X = vec.fit_transform(texts)
        k = min(n_components, X.shape[1] - 1, X.shape[0] - 1)
        if k < 2:
            return np.zeros((len(texts), n_components))
        return normalize(TruncatedSVD(n_components=k, random_state=42).fit_transform(X))

    combined = np.hstack([
        vecs_norm * config.MAP_WEIGHT_DENSE,
        tfidf_svd(titles) * config.MAP_WEIGHT_TITLE,
        tfidf_svd(literature) * config.MAP_WEIGHT_LITERATURE,
    ])
    return normalize(combined)


def reduce_dims(features):
    """UMAP -> low-dim cosine manifold (§5.4). Degrade to TruncatedSVD, then raw."""
    n = len(features)
    dim = min(config.MAP_UMAP_DIM, n - 2)
    if dim < 2:
        return features
    try:
        import umap
        return umap.UMAP(n_components=dim, n_neighbors=min(15, n - 1),
                         min_dist=0.0, metric="cosine", random_state=42).fit_transform(features)
    except Exception:
        pass
    try:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.preprocessing import normalize
        return normalize(TruncatedSVD(n_components=dim, random_state=42).fit_transform(features))
    except Exception:
        return features


# ── parameter selection (§2 validation) ──────────────────────────────────────

def select_params(coords, n_threads=None):
    """Pick thread count by silhouette over a band; return (min_cs, k, silhouette).

    Silhouette alone collapses to k=2 on a single-domain corpus, so the sweep is
    bounded to a useful band (config MAP_MIN/MAX_THREADS, scaled by n). HDBSCAN's
    min_cluster_size is then derived from k so its votes match that granularity.
    """
    n = len(coords)
    if n_threads:
        k = int(n_threads)
        return _min_cs_for(n, k), k, _silhouette_for_k(coords, k)

    lo = max(config.MAP_MIN_THREADS, n // 40)
    hi = min(config.MAP_MAX_THREADS, max(lo + 1, n // 8))
    best = None
    for k in range(lo, hi + 1, 2):
        if k >= n:
            break
        sil = _silhouette_for_k(coords, k)
        if best is None or sil > best[2]:
            best = (_min_cs_for(n, k), k, sil)
    if best is None:
        k = max(5, min(25, n // 15))
        return _min_cs_for(n, k), k, _silhouette_for_k(coords, k)
    return best


def _min_cs_for(n, k):
    return max(3, n // (k * 3))


def _silhouette_for_k(coords, k):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    if k < 2 or k >= len(coords):
        return 0.0
    labels = KMeans(n_clusters=k, n_init="auto", random_state=42).fit_predict(coords)
    return float(silhouette_score(coords, labels))


# ── consensus clustering (ensemble / co-association) ──────────────────────────

def consensus_cluster(coords, k, min_cs):
    """Fuse HDBSCAN + spherical k-means + Ward via a co-association matrix.

    Returns (labels, coassoc, strength) where coassoc[i,j] is the fraction of base
    clusterers placing i,j together and strength[i] is mean co-association to clustermates.
    """
    from sklearn.cluster import KMeans, AgglomerativeClustering
    from sklearn.preprocessing import normalize
    n = len(coords)

    runs = []
    try:
        import hdbscan as hdb
        runs.append(hdb.HDBSCAN(min_cluster_size=min_cs, metric="euclidean").fit_predict(coords))
    except ImportError:
        pass
    runs.append(KMeans(n_clusters=k, n_init="auto", random_state=42).fit_predict(normalize(coords)))
    runs.append(AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(coords))

    coassoc = np.zeros((n, n))
    contributing = 0
    for labels in runs:
        labels = np.asarray(labels)
        valid = labels >= 0
        same = (labels[:, None] == labels[None, :]) & valid[:, None] & valid[None, :]
        coassoc += same
        contributing += 1
    coassoc /= max(contributing, 1)
    np.fill_diagonal(coassoc, 1.0)

    dist = 1.0 - coassoc
    final = AgglomerativeClustering(n_clusters=k, metric="precomputed",
                                    linkage="average").fit_predict(dist)

    strength = {}
    for i in range(n):
        mates = [j for j in range(n) if final[j] == final[i] and j != i]
        strength[i] = float(coassoc[i, mates].mean()) if mates else 1.0
    return list(final), coassoc, strength


# ── confidence-aware assignment (§2.3 soft idea) ──────────────────────────────

def assign(coassoc, labels):
    """From the co-association profile assign primary/secondary threads + outliers.

    Returns (primary, secondary, outliers): primary/secondary map record index -> thread
    label (secondary is None unless the work bridges two threads); outliers is a list of
    record indices that aligned with no thread above MAP_OUTLIER_THRESHOLD.
    """
    labels = np.array(labels)
    clusters = sorted(set(labels))
    n = len(labels)

    primary, secondary, outliers = {}, {}, []
    for i in range(n):
        profile = {c: float(coassoc[i, labels == c].mean()) for c in clusters}
        ranked = sorted(profile.items(), key=lambda kv: -kv[1])
        best_c, best_v = ranked[0]
        if best_v < config.MAP_OUTLIER_THRESHOLD:
            outliers.append(i)
            continue
        primary[i] = best_c
        if len(ranked) > 1:
            second_c, second_v = ranked[1]
            if second_v >= config.MAP_MULTI_MARGIN * best_v and second_v >= config.MAP_OUTLIER_THRESHOLD:
                secondary[i] = second_c
            else:
                secondary[i] = None
        else:
            secondary[i] = None
    return primary, secondary, outliers


# ── c-TF-IDF + thread merging (§3.5, §1.5) ────────────────────────────────────

def ctfidf(thread_members, texts, top_n=12):
    """Class-based TF-IDF: top distinctive terms per thread (BERTopic §3.5)."""
    from sklearn.feature_extraction.text import CountVectorizer
    tids = sorted(thread_members)
    docs = [" ".join(texts[i] for i in thread_members[t]) for t in tids]
    cv = CountVectorizer(stop_words="english", min_df=1, ngram_range=(1, 2))
    tf = cv.fit_transform(docs).toarray().astype(float)
    terms = np.array(cv.get_feature_names_out())

    tf_sum = tf.sum(axis=1, keepdims=True) + 1e-9
    tf_norm = tf / tf_sum
    avg = tf.sum(axis=0) + 1e-9
    idf = np.log(1.0 + tf.shape[0] / (np.count_nonzero(tf, axis=0) + 1e-9))
    ctf = tf_norm * idf * (avg.sum() / avg)
    return {t: list(terms[ctf[r].argsort()[::-1][:top_n]]) for r, t in enumerate(tids)}


def merge_threads(primary, secondary, coords, texts):
    """Merge near-duplicate threads (centroid cosine AND top-term Jaccard above config)."""
    members = {}
    for i, t in primary.items():
        members.setdefault(t, []).append(i)
    if len(members) < 2:
        return primary, secondary, ctfidf(members, texts)

    terms = ctfidf(members, texts)
    tids = list(members)
    cents = {t: coords[members[t]].mean(axis=0) for t in tids}

    def cos(a, b):
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    def jacc(a, b):
        sa, sb = set(a), set(b)
        return len(sa & sb) / len(sa | sb) if (sa or sb) else 0.0

    remap = {t: t for t in tids}
    for ai in range(len(tids)):
        for bi in range(ai + 1, len(tids)):
            a, b = tids[ai], tids[bi]
            ra, rb = _root(remap, a), _root(remap, b)
            if ra == rb:
                continue
            if (cos(cents[a], cents[b]) >= config.MAP_MERGE_SIM
                    and jacc(terms[a], terms[b]) >= config.MAP_MERGE_TERM_J):
                remap[max(ra, rb)] = min(ra, rb)

    primary = {i: _root(remap, t) for i, t in primary.items()}
    secondary = {i: (_root(remap, s) if s is not None else None) for i, s in secondary.items()}
    secondary = {i: (s if s != primary[i] else None) for i, s in secondary.items()}

    members = {}
    for i, t in primary.items():
        members.setdefault(t, []).append(i)
    return primary, secondary, ctfidf(members, texts)


def _root(remap, t):
    while remap[t] != t:
        t = remap[t]
    return t


# ── representative members ────────────────────────────────────────────────────

def most_central(members, base_to_idx, vecs_norm, k=20):
    if len(members) <= k:
        return members
    indices = [base_to_idx[r["base"]] for r in members if r["base"] in base_to_idx]
    cluster_vecs = vecs_norm[indices]
    centroid = cluster_vecs.mean(axis=0)
    centroid /= (np.linalg.norm(centroid) + 1e-9)
    sims = cluster_vecs @ centroid
    top = sims.argsort()[::-1][:k]
    return [members[i] for i in top]
