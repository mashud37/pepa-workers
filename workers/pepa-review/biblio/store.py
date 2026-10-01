"""Provide query helpers over biblio.db, returning plain dicts or lists of
dicts so callers avoid sqlite3.Row and connection management, degrading to
None or [] when data is absent.
"""
import config
from biblio.schema import connect


def metadata(base):
    """Return the works row for `base` as a dict, or None."""
    if not config.BIBLIO_DB.exists():
        return None
    con = connect()
    row = con.execute("SELECT * FROM works WHERE base = ?", (base,)).fetchone()
    con.close()
    return dict(row) if row else None


def references(base):
    """Return citation rows where citing_base = `base` (what this work cites)."""
    return _citations_where("citing_base", base)


def citers(base):
    """Return citation rows where cited_base = `base` (what cites this work)."""
    return _citations_where("cited_base", base)


def authority_scores(min_confidence=None):
    """Return {base: {"cited_by_count": N, "in_degree": N}} for all works.

    in_degree = number of corpus papers that cite this work (internal edges only).
    Rows below min_confidence (default config.BIBLIO_MIN_CONFIDENCE) are excluded
    from the results to keep low-quality matches out of ranking.
    """
    if not config.BIBLIO_DB.exists():
        return {}
    threshold = min_confidence if min_confidence is not None else config.BIBLIO_MIN_CONFIDENCE
    con = connect()
    works = con.execute(
        "SELECT base, cited_by_count FROM works WHERE match_confidence >= ?",
        (threshold,)
    ).fetchall()
    in_deg = con.execute(
        "SELECT cited_base, COUNT(*) AS cnt FROM citations "
        "WHERE cited_base IS NOT NULL GROUP BY cited_base"
    ).fetchall()
    con.close()

    scores = {row["base"]: {"cited_by_count": row["cited_by_count"] or 0, "in_degree": 0}
              for row in works}
    for row in in_deg:
        if row["cited_base"] in scores:
            scores[row["cited_base"]]["in_degree"] = row["cnt"]
    return scores


def work_signals(min_confidence=None):
    """Return {base: {"year": int|None, "cited_by_count": int}} for review anchoring.

    Pulls year + citation count in one query so the review can pick anchors
    (older, highly-cited) without N per-work metadata() calls. Rows below
    min_confidence (default config.BIBLIO_MIN_CONFIDENCE) are excluded.
    """
    if not config.BIBLIO_DB.exists():
        return {}
    threshold = min_confidence if min_confidence is not None else config.BIBLIO_MIN_CONFIDENCE
    con = connect()
    rows = con.execute(
        "SELECT base, year, cited_by_count FROM works WHERE match_confidence >= ?",
        (threshold,)
    ).fetchall()
    con.close()
    return {r["base"]: {"year": r["year"], "cited_by_count": r["cited_by_count"] or 0}
            for r in rows}


def coupling_pairs(min_shared=None):
    """Return [(base_a, base_b, shared_count), ...] for bibliographic coupling.

    Two corpus papers are coupled when they share ≥ min_shared cited works
    (default config.BIBLIO_COUPLING_THRESHOLD).
    """
    if not config.BIBLIO_DB.exists():
        return []
    threshold = min_shared if min_shared is not None else config.BIBLIO_COUPLING_THRESHOLD
    con = connect()
    rows = con.execute("""
        SELECT a.citing_base AS base_a,
               b.citing_base AS base_b,
               COUNT(*)      AS shared
        FROM   citations a
        JOIN   citations b
               ON  (a.cited_ext_id IS NOT NULL AND a.cited_ext_id = b.cited_ext_id)
                OR (a.cited_doi    IS NOT NULL AND a.cited_doi    = b.cited_doi)
        WHERE  a.citing_base < b.citing_base
        GROUP  BY a.citing_base, b.citing_base
        HAVING shared >= ?
    """, (threshold,)).fetchall()
    con.close()
    return [(r["base_a"], r["base_b"], r["shared"]) for r in rows]


def cocitation_pairs():
    """Return [(cited_a, cited_b, count), ...] for co-citation.

    Two cited works are co-cited when they appear together in ≥1 corpus paper's
    reference list.  cited_a / cited_b are cited_ext_id values (may be external
    to the corpus).
    """
    if not config.BIBLIO_DB.exists():
        return []
    con = connect()
    rows = con.execute("""
        SELECT a.cited_ext_id AS cited_a,
               b.cited_ext_id AS cited_b,
               COUNT(DISTINCT a.citing_base) AS cnt
        FROM   citations a
        JOIN   citations b
               ON  a.citing_base = b.citing_base
               AND a.cited_ext_id < b.cited_ext_id
        WHERE  a.cited_ext_id IS NOT NULL
           AND b.cited_ext_id IS NOT NULL
        GROUP  BY a.cited_ext_id, b.cited_ext_id
        HAVING cnt >= 2
    """).fetchall()
    con.close()
    return [(r["cited_a"], r["cited_b"], r["cnt"]) for r in rows]


def stats():
    """Return summary counts dict for the biblio_cmd stats display."""
    if not config.BIBLIO_DB.exists():
        return None
    con = connect()
    n_works      = con.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    n_with_doi   = con.execute("SELECT COUNT(*) FROM works WHERE doi IS NOT NULL").fetchone()[0]
    n_cit        = con.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
    n_internal   = con.execute("SELECT COUNT(*) FROM citations WHERE cited_base IS NOT NULL").fetchone()[0]
    n_corpus_cit = con.execute(
        "SELECT COUNT(DISTINCT citing_base) FROM citations WHERE cited_base IS NOT NULL"
    ).fetchone()[0]
    con.close()
    return {
        "works": n_works,
        "with_doi": n_with_doi,
        "citations": n_cit,
        "internal_edges": n_internal,
        "corpus_works_with_refs": n_corpus_cit,
    }


def _citations_where(col, value):
    if not config.BIBLIO_DB.exists():
        return []
    con = connect()
    rows = con.execute(f"SELECT * FROM citations WHERE {col} = ?", (value,)).fetchall()
    con.close()
    return [dict(r) for r in rows]
