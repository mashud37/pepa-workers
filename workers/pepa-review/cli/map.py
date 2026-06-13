"""WS4 — Corpus map: cluster all indexed works into thematic threads.

Uses pre-computed embeddings from the index. Clustering strategy follows
cs_ir_stats_reference.md §2.6: HDBSCAN on normalised dense embeddings
(auto-picks thread count, handles variable density); scikit-learn k-means
fallback; all-in-one absolute fallback.

For each thread the LLM (Sonnet) names the theme, writes a 2–3 sentence
discussion, and lists 6–8 key arguments drawn from the works. Output is a
single Markdown file in output/.
"""
import json
from datetime import datetime
from pathlib import Path

import config
from cli import ui, progress
from backends import llm, prompt as prompts


def run(n_threads=None):
    ui.header("Corpus map")

    idx = _load_index()
    records = idx["records"]
    vectors = idx["vectors"]
    n = len(records)
    ui.info(f"corpus: {n} works")

    import numpy as np
    vecs = np.array(vectors, dtype=float)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    vecs_norm = vecs / norms

    sp = progress.StepSpinner("clustering")
    sp.start()
    try:
        labels = _cluster(vecs_norm, n_threads)
        n_threads_found = len({l for l in labels if l >= 0})
        n_noise = sum(1 for l in labels if l < 0)
        sp.done(f"{n_threads_found} threads" + (f", {n_noise} uncategorized" if n_noise else ""))
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    clusters = {}
    noise = []
    for rec, label in zip(records, labels):
        if label < 0:
            noise.append(rec)
        else:
            clusters.setdefault(int(label), []).append(rec)

    sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))
    total = len(sorted_clusters) + (1 if noise else 0)
    ui.info(f"generating {total} thread reports…")

    sections = []
    for ci, (cluster_id, recs) in enumerate(sorted_clusters):
        sp2 = progress.StepSpinner(f"[{ci+1}/{total}] thread")
        sp2.start()
        try:
            section = _generate_thread(recs, vecs_norm, list(records).index(recs[0]) if len(recs) > 20 else None)
            sp2.done(section["name"][:45])
            sections.append(section)
        except Exception as e:
            sp2.done("error")
            raise SystemExit(str(e))

    if noise:
        sections.append({
            "name": "Uncategorized works",
            "records": noise,
            "arguments": [],
            "discussion": "_Works that did not cluster strongly with any thread._",
        })

    out = _write_map(sections, n)
    ui.ok(f"saved to {out.name}")
    ui.rule()
    for i, s in enumerate(sections, 1):
        ui.info(f"  {i:2}. {s['name']}  ({len(s['records'])} works)")


def _load_index():
    if not config.INDEX_FILE.exists():
        raise SystemExit("No index found. Run: python manage.py index")
    idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
    if not idx.get("records"):
        raise SystemExit("Index is empty.")
    return idx


def _cluster(vecs_norm, n_threads=None):
    n = len(vecs_norm)
    try:
        import hdbscan as hdb
        labels = hdb.HDBSCAN(min_cluster_size=max(3, n // 50),
                              metric="euclidean").fit_predict(vecs_norm)
        if len({l for l in labels if l >= 0}) >= 3:
            return labels
    except ImportError:
        pass
    try:
        from sklearn.cluster import KMeans
        k = n_threads if n_threads else max(4, min(25, n // 15))
        return KMeans(n_clusters=k, n_init="auto", random_state=42).fit_predict(vecs_norm)
    except ImportError:
        pass
    return [0] * n


def _most_central(records_in_cluster, all_records, vecs_norm, k=20):
    """Return the k records closest to the cluster centroid."""
    import numpy as np
    if len(records_in_cluster) <= k:
        return records_in_cluster
    idx_map = {id(r): i for i, r in enumerate(all_records)}
    indices = [idx_map[id(r)] for r in records_in_cluster if id(r) in idx_map]
    cluster_vecs = vecs_norm[indices]
    centroid = cluster_vecs.mean(axis=0)
    centroid /= (np.linalg.norm(centroid) + 1e-9)
    sims = cluster_vecs @ centroid
    top = sims.argsort()[::-1][:k]
    return [records_in_cluster[i] for i in top]


def _generate_thread(records, vecs_norm, _hint=None):
    response = llm.complete(
        prompts.map_system(),
        prompts.map_thread_prompt(records),
        max_tokens=800,
        quality=True,
    )
    return _parse_response(response, records)


def _parse_response(response, records):
    import re
    name, discussion, arguments = "", "", []

    m = re.search(r"\*\*Theme:\*\*\s*(.+)", response)
    if m:
        name = m.group(1).strip()

    m = re.search(r"\*\*Discussion:\*\*\s*(.+?)(?=\*\*Key arguments|\Z)", response, re.DOTALL)
    if m:
        discussion = m.group(1).strip()

    m = re.search(r"\*\*Key arguments:\*\*\s*(.+)", response, re.DOTALL)
    if m:
        for line in m.group(1).strip().splitlines():
            line = line.lstrip("-•· ").strip()
            if line:
                arguments.append(line)

    return {
        "name": name or "Unnamed thread",
        "records": records,
        "discussion": discussion,
        "arguments": arguments[:8],
    }


def _write_map(sections, total_works):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = config.OUTPUT_DIR / f"corpus_map_{ts}.md"

    lines = [
        "# Corpus Map",
        "",
        f"_{total_works} works · {len(sections)} threads_",
        "",
        "---",
        "",
    ]

    for i, s in enumerate(sections, 1):
        lines += [f"## {i}. {s['name']}", ""]
        lines += [f"**Works ({len(s['records'])}):**"]
        for r in sorted(s["records"], key=lambda x: x.get("authors", "")):
            lines.append(f"- {r.get('authors', '')} — {r.get('title', '')}")
        lines.append("")
        if s.get("arguments"):
            lines += ["**Key arguments:**"]
            for arg in s["arguments"]:
                lines.append(f"- {arg}")
            lines.append("")
        if s.get("discussion"):
            lines += ["**Discussion:**", "", s["discussion"], ""]
        lines += ["---", ""]

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
