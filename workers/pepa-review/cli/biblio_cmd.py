"""Bibliographic enrichment commands (all require use_biblio=true in secrets.yaml).

Subcommands
  ingest   — load upstream works + citations CSV/JSONL into biblio.db
  export   — write works.csv + citations.csv to output/
  stats    — print summary counts
  network  — build and export citation or coupling graph
"""
import sys
from pathlib import Path

import config
from cli import ui, progress


def run(subcmd, works_file=None, citations_file=None,
        graph_type="citation", fmt="html", output_dir=None):
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

    def on_progress(i, total, label):
        sp._label = f"[{i}/{total}] {label[:18]}"

    try:
        from biblio.ingest import ingest
        n_works, n_cit, n_resolved = ingest(
            works_path, cit_path, progress_cb=on_progress
        )
        sp.done(f"{n_works} works")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    ui.ok(f"{n_works} works stored")
    if cit_path:
        ui.ok(f"{n_cit} citation edges stored")
        ui.ok(f"{n_resolved} edges resolved to corpus works (internal graph)")
    ui.info("biblio.db ready — set use_biblio: true in secrets.yaml to activate enrichment")


def _export(output_dir):
    ui.header("Export document reference")
    _require_db()

    sp = progress.StepSpinner("exporting CSVs")
    sp.start()
    try:
        from biblio.export import export
        w_path, c_path = export(output_dir)
        sp.done("done")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    ui.ok(f"works:     {w_path.name}")
    ui.ok(f"citations: {c_path.name}")
    ui.info(f"in {w_path.parent}")


def _stats():
    ui.header("Bibliographic data — statistics")
    _require_db()

    from biblio.store import stats
    s = stats()
    if not s:
        ui.warn("biblio.db is empty — run: python manage.py biblio ingest")
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
        ui.warn("Enrichment is off — set use_biblio: true in secrets.yaml to activate")


def _network(graph_type, fmt, output_dir):
    ui.header(f"Citation network — {graph_type}")
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
        raise SystemExit(f"No {prompt} provided and no TTY — pass it as an argument.")
    raw = ui.ask(f"{prompt} path")
    if not raw:
        raise SystemExit("No file provided.")
    return raw
