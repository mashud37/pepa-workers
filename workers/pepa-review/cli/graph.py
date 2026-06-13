"""WS4 — Knowledge graph over the sum_ corpus.

Clusters works by embedding similarity and builds a kNN graph. Exports as
GraphML (networkx) or standalone HTML (pyvis), both lazy-optional deps.

Clustering strategy (cs_ir_stats_reference.md §2):
  - HDBSCAN if installed (density-based, auto-picks cluster count, handles
    variable density — the recommended recipe for embedding-based text clustering)
  - otherwise cosine k-means via scikit-learn (good baseline, needs k up front)
  - absolute fallback: all assigned to cluster 0

For incremental updates (--update), new works are assigned to the nearest
existing cluster centroid rather than re-clustering everything.
"""
import json
from datetime import datetime
from pathlib import Path

import config
from cli import ui, progress


def run(force=False, export_format="html", update=False):
    ui.header("Knowledge graph")

    idx = _load_index()
    records = idx["records"]
    vectors = idx["vectors"]
    ui.info(f"index: {len(records)} works")

    graph_data = None
    if update and config.GRAPH_FILE.exists():
        existing = json.loads(config.GRAPH_FILE.read_text(encoding="utf-8"))
        existing_bases = {n["base"] for n in existing.get("nodes", [])}
        new_recs = [r for r in records if r["base"] not in existing_bases]
        if not new_recs:
            ui.info("No new works since last graph build.")
            graph_data = existing
        else:
            ui.info(f"Adding {len(new_recs)} new works incrementally…")
            graph_data = _update_graph(existing, new_recs, records, vectors)

    if not graph_data:
        ui.step(f"Building graph from {len(records)} works…")
        graph_data = _build_graph(records, vectors)

    _save_graph(graph_data)
    n_clusters = len({n.get("cluster", 0) for n in graph_data["nodes"]})
    ui.ok(
        f"graph: {len(graph_data['nodes'])} nodes, "
        f"{len(graph_data['edges'])} edges, {n_clusters} clusters"
    )

    sp = progress.StepSpinner(f"exporting {export_format}")
    sp.start()
    try:
        out = _export(graph_data, export_format)
        sp.done(str(out.name))
    except SystemExit:
        sp.done("error")
        raise

    ui.ok(f"exported to {out}")
    _open_file(out)


def _load_index():
    if not config.INDEX_FILE.exists():
        raise SystemExit("No index found. Run: python manage.py index")
    idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
    if not idx.get("records"):
        raise SystemExit("Index is empty.")
    return idx


def _build_graph(records, vectors):
    import numpy as np
    vecs = np.array(vectors, dtype=float)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    vecs_norm = vecs / norms

    labels = _cluster(vecs_norm)

    sim = vecs_norm @ vecs_norm.T
    threshold = 0.70
    edges = []
    n = len(records)
    for i in range(n):
        for j in range(i + 1, n):
            w = float(sim[i, j])
            if w >= threshold:
                edges.append({"source": records[i]["base"],
                               "target": records[j]["base"],
                               "weight": round(w, 4)})

    nodes = [
        {"base": r["base"], "authors": r["authors"],
         "title": r["title"], "cluster": int(labels[i])}
        for i, r in enumerate(records)
    ]
    return {"nodes": nodes, "edges": edges}


def _update_graph(existing, new_recs, all_records, all_vectors):
    """Assign new records to nearest existing cluster and extend the graph."""
    import numpy as np

    by_base = {r["base"]: v for r, v in zip(all_records, all_vectors)}
    existing_nodes = {n["base"]: n for n in existing["nodes"]}
    existing_edges = {(e["source"], e["target"]): e for e in existing["edges"]}

    clusters = {}
    for n in existing["nodes"]:
        c = n.get("cluster", 0)
        clusters.setdefault(c, []).append(by_base[n["base"]])
    centroids = {c: np.mean(vs, axis=0) for c, vs in clusters.items()}

    new_vecs = np.array([by_base[r["base"]] for r in new_recs], dtype=float)
    norms = np.linalg.norm(new_vecs, axis=1, keepdims=True) + 1e-9
    new_vecs_norm = new_vecs / norms

    for i, r in enumerate(new_recs):
        best_c = min(centroids,
                     key=lambda c: np.linalg.norm(new_vecs_norm[i] - centroids[c]))
        existing_nodes[r["base"]] = {
            "base": r["base"], "authors": r["authors"],
            "title": r["title"], "cluster": int(best_c),
        }

    all_bases = list(existing_nodes.keys())
    all_vecs = np.array([by_base.get(b, [0.0] * 768) for b in all_bases], dtype=float)
    all_vecs_norm = all_vecs / (np.linalg.norm(all_vecs, axis=1, keepdims=True) + 1e-9)
    sim = all_vecs_norm @ all_vecs_norm.T
    threshold = 0.70
    edges = dict(existing_edges)
    n = len(all_bases)
    for i in range(n):
        for j in range(i + 1, n):
            w = float(sim[i, j])
            if w >= threshold:
                key = (all_bases[i], all_bases[j])
                edges[key] = {"source": all_bases[i], "target": all_bases[j],
                              "weight": round(w, 4)}

    return {"nodes": list(existing_nodes.values()), "edges": list(edges.values())}


def _cluster(vecs_norm):
    n = len(vecs_norm)
    try:
        import hdbscan
        labels = hdbscan.HDBSCAN(min_cluster_size=5, metric="euclidean").fit_predict(vecs_norm)
        labels[labels < 0] = labels.max() + 1
        return labels
    except ImportError:
        pass
    try:
        from sklearn.cluster import KMeans
        k = max(3, min(25, n // 15))
        return KMeans(n_clusters=k, n_init="auto", random_state=42).fit_predict(vecs_norm)
    except ImportError:
        return [0] * n


def _open_file(path):
    import webbrowser
    webbrowser.open(path.resolve().as_uri())


def _save_graph(graph_data):
    config.GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.GRAPH_FILE.write_text(json.dumps(graph_data), encoding="utf-8")


def _export(graph_data, fmt):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "html":
        return _export_html(graph_data, ts)
    return _export_graphml(graph_data, ts)


def _export_graphml(graph_data, ts):
    try:
        import networkx as nx
    except ImportError:
        raise SystemExit("networkx not installed. Run: pip install networkx")
    G = nx.Graph()
    for node in graph_data["nodes"]:
        G.add_node(node["base"], authors=node["authors"],
                   title=node["title"], cluster=str(node.get("cluster", 0)))
    for edge in graph_data["edges"]:
        G.add_edge(edge["source"], edge["target"], weight=edge["weight"])
    out = config.OUTPUT_DIR / f"graph_{ts}.graphml"
    nx.write_graphml(G, str(out))
    return out


def _export_html(graph_data, ts):
    try:
        from pyvis.network import Network
    except ImportError:
        raise SystemExit("pyvis not installed. Run: pip install pyvis")
    PALETTE = [
        "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
        "#1abc9c", "#e67e22", "#34495e", "#16a085", "#8e44ad",
        "#d35400", "#27ae60", "#2980b9", "#c0392b", "#7f8c8d",
    ]
    net = Network(height="800px", width="100%", bgcolor="#1a1a2e", font_color="white")
    for node in graph_data["nodes"]:
        c = node.get("cluster", 0)
        net.add_node(
            node["base"],
            label=node["authors"][:20],
            title=f"{node['authors']}\n{node['title'][:80]}\nCluster {c}",
            color=PALETTE[c % len(PALETTE)],
        )
    for edge in graph_data["edges"]:
        net.add_edge(edge["source"], edge["target"], value=edge["weight"])
    out = config.OUTPUT_DIR / f"graph_{ts}.html"
    net.save_graph(str(out))
    return out
