"""Build citation, coupling, and cocitation graph views from biblio.db, export each as
GraphML or HTML, and store PageRank and authority scores back to biblio.db.
"""
from datetime import datetime
from pathlib import Path

import config
from biblio import store
from biblio.schema import connect

_PALETTE = [
    "#e74c3c",
    "#3498db",
    "#2ecc71",
    "#f39c12",
    "#9b59b6",
    "#1abc9c",
    "#e67e22",
    "#34495e",
    "#16a085",
    "#8e44ad",
    "#d35400",
    "#27ae60",
    "#2980b9",
    "#c0392b",
    "#7f8c8d",
]


def build_citation_graph():
    """Return networkx DiGraph of internal citation edges (corpus → corpus only)."""
    nx = _require_networkx()
    con = connect()
    works = {r["base"]: dict(r) for r in con.execute("SELECT * FROM works").fetchall()}
    edges = con.execute(
        "SELECT citing_base, cited_base FROM citations WHERE cited_base IS NOT NULL"
    ).fetchall()
    con.close()

    G = nx.DiGraph()
    for base, w in works.items():
        G.add_node(base, authors=w.get("authors") or base,
                   title=w.get("title") or "",
                   year=w.get("year") or 0,
                   venue=w.get("venue") or "")
    for e in edges:
        if e["citing_base"] in G and e["cited_base"] in G:
            G.add_edge(e["citing_base"], e["cited_base"])
    return G


def build_coupling_graph():
    """Return networkx Graph of bibliographic coupling edges."""
    nx = _require_networkx()
    pairs = store.coupling_pairs()
    con = connect()
    works = {r["base"]: dict(r) for r in con.execute("SELECT * FROM works").fetchall()}
    con.close()

    G = nx.Graph()
    for base, w in works.items():
        G.add_node(base, authors=w.get("authors") or base, title=w.get("title") or "")
    for base_a, base_b, shared in pairs:
        G.add_edge(base_a, base_b, weight=shared)
    return G


def pagerank(G=None):
    """Return {base: pagerank_score} over the citation DiGraph."""
    nx = _require_networkx()
    if G is None:
        G = build_citation_graph()
    if G.number_of_edges() == 0:
        return {n: 0.0 for n in G.nodes}
    return nx.pagerank(G, alpha=0.85)


def export_graph(graph_type="citation", fmt="html", output_dir=None):
    """Build and export a derived graph. graph_type: citation | coupling.

    Returns the output Path.
    """
    if graph_type == "coupling":
        G = build_coupling_graph()
    else:
        G = build_citation_graph()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(output_dir) if output_dir else config.OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        return _export_html(G, graph_type, ts, out)
    return _export_graphml(G, graph_type, ts, out)


def _export_graphml(G, kind, ts, out):
    nx = _require_networkx()
    path = out / f"biblio_{kind}_{ts}.graphml"
    nx.write_graphml(G, str(path))
    return path


def _export_html(G, kind, ts, out):
    try:
        from pyvis.network import Network
    except ImportError:
        raise SystemExit("pyvis not installed. Run: pip install pyvis")
    directed = kind == "citation"
    net = Network(height="800px", width="100%", bgcolor="#1a1a2e",
                  font_color="white", directed=directed)
    for node, data in G.nodes(data=True):
        label = (data.get("authors") or node)[:20]
        title = f"{data.get('authors','')}\n{data.get('title','')[:80]}"
        if data.get("year"):
            title += f"\n{data['year']}"
        net.add_node(node, label=label, title=title, color=_PALETTE[hash(node) % len(_PALETTE)])
    for src, dst, edata in G.edges(data=True):
        net.add_edge(src, dst, value=edata.get("weight", 1))
    path = out / f"biblio_{kind}_{ts}.html"
    net.save_graph(str(path))
    return path


def _require_networkx():
    try:
        import networkx as nx
        return nx
    except ImportError:
        raise SystemExit("networkx not installed. Run: pip install networkx")
