"""Run bibliographic enrichment subcommands: ingest, export, stats, and
network, all requiring use_biblio=true in secrets.yaml.
"""
import sys
from functools import partial
from pathlib import Path

import config
from cli import ui, progress


def run(subcmd, options=None):
    """Dispatch a biblio subcommand.

    Args:
        subcmd: one of "ingest", "export", "stats", "network".
        options: dict with keys "works_file", "citations_file",
            "graph_type", "fmt", "output_dir", all optional.
    """
    options = options or {}
    works_file = options.get("works_file")
    citations_file = options.get("citations_file")
    graph_type = options.get("graph_type", "citation")
    fmt = options.get("fmt", "html")
    output_dir = options.get("output_dir")

    if subcmd == "ingest":
        _ingest(works_file, citations_file)
    elif subcmd == "export":
        _export(output_dir)
    elif subcmd == "stats":
        _stats()
    elif subcmd == "network":
        _network(graph_type, fmt, output_dir)
    else:
        raise SystemExit(f"Unknown biblio subcommand: {subcmd}")


def _report_ingest_progress(sp, i, total, label):
    sp._label = f"[{i}/{total}] {label[:18]}"


def _ingest(works_file, citations_file):
    ui.header("Bibliographic ingest")

    if not works_file:
        works_file = _pick_file("works file (CSV or JSONL)")
    works_path = Path(works_file)
    if not works_path.exists():
        raise SystemExit(f"File not found: {works_path}")

    cit_path = None
    if citations_file:
        cit_path = Path(citations_file)
        if not cit_path.exists():
            raise SystemExit(f"File not found: {cit_path}")

    ui.info(f"works:     {works_path.name}")
    if cit_path:
        ui.info(f"citations: {cit_path.name}")

    sp = progress.StepSpinner("ingesting works")
    sp.start()

    try:
        from biblio.ingest import ingest
        result = ingest(works_path, cit_path, progress_cb=partial(_report_ingest_progress, sp))
        sp.done(f"{result['n_works']} works")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    ui.ok(f"{result['n_works']} works stored")
    if cit_path:
        ui.ok(f"{result['n_citations']} citation edges stored")
        ui.ok(f"{result['n_resolved']} edges resolved to corpus works (internal graph)")
    ui.info("biblio.db ready: set use_biblio: true in secrets.yaml to activate enrichment")


def _export(output_dir):
    ui.header("Export document reference")
    _require_db()

    sp = progress.StepSpinner("exporting CSVs")
    sp.start()
    try:
        from biblio.export import export
        paths = export(output_dir)
        sp.done("done")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    ui.ok(f"works:     {paths['works_path'].name}")
    ui.ok(f"citations: {paths['citations_path'].name}")
    ui.info(f"in {paths['works_path'].parent}")


def _stats():
    ui.header("Bibliographic data: statistics")
    _require_db()

    from biblio.store import stats
    s = stats()
    if not s:
        ui.warn("biblio.db is empty. Run: python manage.py biblio ingest")
        return

    ui.step("Works")
    ui.info(f"total in biblio.db:  {s['works']}")
    ui.info(f"with DOI:            {s['with_doi']}")
    if s["works"]:
        pct = round(100 * s["with_doi"] / s["works"])
        ui.info(f"DOI coverage:        {pct}%")

    ui.step("Citations")
    ui.info(f"total reference edges:          {s['citations']}")
    ui.info(f"internal edges (corpus→corpus): {s['internal_edges']}")
    ui.info(f"corpus works with ≥1 ref:       {s['corpus_works_with_refs']}")

    enrichment = "on" if config.use_biblio() else "off"
    ui.step("Toggle")
    ui.info(f"use_biblio: {enrichment}")
    if not config.use_biblio():
        ui.warn("Enrichment is off: set use_biblio: true in secrets.yaml to activate")


def _network(graph_type, fmt, output_dir):
    ui.header(f"Citation network: {graph_type}")
    _require_db()

    sp = progress.StepSpinner(f"building {graph_type} graph")
    sp.start()
    try:
        from biblio.network import export_graph
        out_path = export_graph(graph_type=graph_type, fmt=fmt, output_dir=output_dir)
        sp.done(str(out_path.name))
    except SystemExit:
        sp.done("error")
        raise
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    ui.ok(f"exported: {out_path}")
    import webbrowser
    if fmt == "html":
        webbrowser.open(out_path.resolve().as_uri())


def _require_db():
    if not config.BIBLIO_DB.exists():
        raise SystemExit(
            "biblio.db not found. Run: python manage.py biblio ingest <works-file>"
        )


def _pick_file(prompt):
    if not sys.stdin.isatty():
        raise SystemExit(f"No {prompt} provided and no TTY. Pass it as an argument.")
    raw = ui.ask(f"{prompt} path")
    if not raw:
        raise SystemExit("No file provided.")
    return raw
