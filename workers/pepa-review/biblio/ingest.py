"""Ingest upstream works and citations files (CSV or JSONL) into
biblio.db, resolving cited works that are themselves in the corpus into an
internal citation network. Idempotent: existing rows are replaced.
"""
import csv
import json
from pathlib import Path

from biblio.schema import connect, ensure_schema


def ingest(works_path, citations_path=None, progress_cb=None):
    """Load works and (optionally) citations into biblio.db.

    Returns:
        dict with keys "n_works", "n_citations", and "n_resolved", where
        n_resolved is the number of citation edges whose cited_base was
        resolved to a corpus work.
    """
    con = connect()
    ensure_schema(con)

    works_path = Path(works_path)
    works_rows = _load_file(works_path)
    n_works = _upsert_works(con, works_rows, progress_cb)

    n_citations = 0
    n_resolved = 0
    if citations_path:
        cit_rows = _load_file(Path(citations_path))
        citation_result = _upsert_citations(con, cit_rows)
        n_citations = citation_result["n_citations"]
        n_resolved = citation_result["n_resolved"]

    con.close()
    return {"n_works": n_works, "n_citations": n_citations, "n_resolved": n_resolved}


def resolve_cited_bases(con=None):
    """Fill cited_base for citation rows whose cited_ext_id or cited_doi
    matches a works row.  Safe to call repeatedly."""
    _own = con is None
    if _own:
        con = connect()
    con.execute("""
        UPDATE citations
        SET cited_base = (
            SELECT w.base FROM works w
            WHERE (citations.cited_ext_id IS NOT NULL AND w.ext_id = citations.cited_ext_id)
               OR (citations.cited_doi    IS NOT NULL AND w.doi    = citations.cited_doi)
            LIMIT 1
        )
        WHERE cited_base IS NULL
    """)
    changed = con.execute("SELECT changes()").fetchone()[0]
    con.commit()
    if _own:
        con.close()
    return changed


def _load_file(path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    if suffix in (".jsonl", ".ndjson"):
        return _read_jsonl(path)
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else [data]
    raise SystemExit(f"Unsupported file format: {path.suffix}  (expected .csv, .jsonl, .json)")


def _read_jsonl(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _upsert_works(con, rows, progress_cb):
    fields = (
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
    )
    sql = f"""
        INSERT OR REPLACE INTO works ({', '.join(fields)})
        VALUES ({', '.join('?' for _ in fields)})
    """
    total = len(rows)
    for i, row in enumerate(rows, 1):
        vals = (
            _str(row, "base"),
            _str(row, "doi"),
            _str(row, "ext_id"),
            _str(row, "title"),
            _str(row, "authors"),
            _str(row, "venue"),
            _int(row, "year"),
            _str(row, "type"),
            _int(row, "cited_by_count"),
            _str(row, "concepts"),
            _float(row, "match_confidence", 1.0),
        )
        con.execute(sql, vals)
        if progress_cb:
            progress_cb(i, total, _str(row, "base") or "")
    con.commit()
    return total


def _upsert_citations(con, rows):
    sql = """
        INSERT OR IGNORE INTO citations
            (citing_base, cited_ext_id, cited_doi, cited_title, cited_authors, cited_year, cited_base)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    for row in rows:
        con.execute(sql, (
            _str(row, "citing_base"),
            _str(row, "cited_ext_id"),
            _str(row, "cited_doi"),
            _str(row, "cited_title"),
            _str(row, "cited_authors"),
            _int(row, "cited_year"),
            _str(row, "cited_base"),
        ))
    con.commit()
    n = len(rows)
    resolved = resolve_cited_bases(con)
    return {"n_citations": n, "n_resolved": resolved}


def _str(row, key):
    v = row.get(key)
    return str(v).strip() if v not in (None, "", "NULL", "null") else None


def _int(row, key):
    v = row.get(key)
    try:
        return int(v) if v not in (None, "", "NULL", "null") else None
    except (ValueError, TypeError):
        return None


def _float(row, key, default=None):
    v = row.get(key)
    try:
        return float(v) if v not in (None, "", "NULL", "null") else default
    except (ValueError, TypeError):
        return default
