"""Export biblio.db to two timestamped CSV files in output/: works with
DOI, venue, and year, and citations as a reference edge list, both UTF-8
with BOM for Excel.
"""
import csv
from datetime import datetime
from pathlib import Path

import config
from biblio.schema import connect


def export(output_dir=None):
    """Write works and citations CSVs.

    Returns:
        dict with keys "works_path" and "citations_path".
    """
    out = Path(output_dir) if output_dir else config.OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    con = connect()
    w_path = _write_works(con, out, ts)
    c_path = _write_citations(con, out, ts)
    con.close()
    return {"works_path": w_path, "citations_path": c_path}


def _write_works(con, out, ts):
    rows = con.execute("""
        SELECT base, doi, ext_id, title, authors, venue, year, type,
               cited_by_count, concepts, match_confidence
        FROM   works
        ORDER  BY authors, year
    """).fetchall()

    path = out / f"works_{ts}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "base",
            "doi",
            "ext_id",
            "title",
            "authors",
            "venue",
            "year",
            "type",
            "cited_by_count",
            "concepts",
            "match_confidence",
        ])
        for r in rows:
            w.writerow(list(r))
    return path


def _write_citations(con, out, ts):
    rows = con.execute("""
        SELECT c.citing_base,
               cw.authors       AS citing_authors,
               cw.year          AS citing_year,
               c.cited_base,
               c.cited_ext_id,
               c.cited_doi,
               c.cited_title,
               c.cited_authors,
               c.cited_year
        FROM   citations c
        LEFT JOIN works cw ON cw.base = c.citing_base
        ORDER  BY c.citing_base, c.cited_year
    """).fetchall()

    path = out / f"citations_{ts}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "citing_base",
            "citing_authors",
            "citing_year",
            "cited_base",
            "cited_ext_id",
            "cited_doi",
            "cited_title",
            "cited_authors",
            "cited_year",
        ])
        for r in rows:
            w.writerow(list(r))
    return path
