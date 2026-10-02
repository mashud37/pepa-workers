"""BM25 keyword search over the summaries and the prepared full text, shared by manage.py and the Flask API."""
import re
import sqlite3

# User-facing query prefixes -> real FTS5 column names. FTS5 natively supports
# `column:term` filters (applying to the single term that follows), so this is
# just an alias rewrite: the rest of the query's implicit-AND grammar handles
# combining a field filter with ordinary free-text terms, e.g.
# "lit:foucault author:aaker brand" -> "literature:foucault authors_raw:aaker AND brand".
_FIELD_ALIASES = {
    "author": "authors_raw",
    "title": "title",
    "context": "question_context",   # pepa-sum "Question & context"
    "empirical": "empirical_context",  # pepa-sum "Empirical context"
    "lit": "literature",             # pepa-sum "Literature drawn on"
    "methods": "methods",
    "arguments": "arguments",
    "conclusions": "conclusions",    # pepa-sum "Key conclusions"
    "discussion": "discussion",      # pepa-sum "Discussion items"
}
_FIELD_TOKEN_RE = re.compile(r"\b(" + "|".join(_FIELD_ALIASES) + r"):(\S+)")

# Column order/count must match documents_fts (index/schema.py) for bm25()
# weights and snippet()'s column index to line up.
_BM25_WEIGHTS = "5.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0"
DEFAULT_LIMIT = 20

SUMMARY_THEN_FULL_TEXT = f"""
WITH summary AS (
    SELECT rowid AS id,
           bm25(documents_fts, {_BM25_WEIGHTS}) AS score,
           snippet(documents_fts, -1, '[', ']', ' ... ', 12) AS snippet
    FROM documents_fts
    WHERE documents_fts MATCH ?
),
full_text AS (
    SELECT d.id, bm25(bodies_fts) AS score
    FROM bodies_fts
    JOIN documents d ON d.body_rowid = bodies_fts.rowid
    WHERE bodies_fts MATCH ?
)
SELECT d.id, d.stem, d.title, d.authors_raw, d.text_path, d.sum_path, found.score, found.snippet
FROM (
    SELECT id, score, snippet, 0 AS tier FROM summary
    UNION ALL
    SELECT id, score, '' AS snippet, 1 AS tier FROM full_text WHERE id NOT IN (SELECT id FROM summary)
) AS found
JOIN documents d ON d.id = found.id
ORDER BY found.tier, found.score
LIMIT ? OFFSET ?
"""

COUNT_SUMMARY_OR_FULL_TEXT = """
SELECT COUNT(*) FROM (
    SELECT rowid AS id FROM documents_fts WHERE documents_fts MATCH ?
    UNION
    SELECT d.id FROM bodies_fts
    JOIN documents d ON d.body_rowid = bodies_fts.rowid
    WHERE bodies_fts MATCH ?
)
"""


def _real_column(match) -> str:  # lint-style: ignore FN004
    """Rewrite one `alias:term` token into the FTS column name the index uses."""
    return f"{_FIELD_ALIASES[match.group(1)]}:{match.group(2)}"


def _match_expr(text: str, author: str | None) -> str:
    parts = []
    if text:
        stripped = text.strip()
        parts.append(_FIELD_TOKEN_RE.sub(_real_column, stripped))
    if author:
        parts.append(f'authors_raw:"{author}"')
    return " AND ".join(p for p in parts if p)


def _plain_words(text: str, author: str | None) -> bool:
    """True when a query is free text only: the full-text index has no fields to filter on."""
    return bool(text.strip()) and not author and not _FIELD_TOKEN_RE.search(text)


def _has_full_text(conn) -> bool:
    """True when the index holds the full-text table; an index not yet rebuilt has the summaries only."""
    found = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'bodies_fts'").fetchone()
    return found is not None


def _result(row, score=None, snippet=""):
    return {
        "id": row["id"],
        "stem": row["stem"],
        "title": row["title"],
        "authors_raw": row["authors_raw"],
        "has_text": bool(row["text_path"]),
        "has_sum": bool(row["sum_path"]),
        "text_path": row["text_path"],
        "sum_path": row["sum_path"],
        "snippet": snippet,
        "score": score,
    }


def count(db_path, query: str = "", author: str | None = None) -> int:
    """Total rows matching `query`/`author`, ignoring `limit`/`offset`, for pagination."""
    conn = sqlite3.connect(db_path)
    try:
        match_expr = _match_expr(query or "", author)
        if _plain_words(query or "", author) and _has_full_text(conn):
            row = conn.execute(COUNT_SUMMARY_OR_FULL_TEXT, (match_expr, match_expr)).fetchone()
        elif match_expr:
            row = conn.execute(
                "SELECT COUNT(*) FROM documents_fts WHERE documents_fts MATCH ?",
                (match_expr,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        return row[0]
    finally:
        conn.close()


def search(db_path, query: str = "", author: str | None = None,
           limit: int = DEFAULT_LIMIT, offset: int = 0) -> list[dict]:
    """Rank documents by BM25 relevance to `query`, optionally filtered by author.

    Args:
        db_path: Path to the reader.db SQLite file.
        query: Free-text query. Supports field-scoped tokens (FTS5 column
            filters under the hood): `author:`, `title:`, `context:`,
            `empirical:`, `lit:`, `methods:`, `arguments:`, `conclusions:`,
            `discussion:`, combinable with free text and each other, e.g.
            `lit:foucault author:aaker brand`.
        author: Explicit author filter, ANDed with any inline `author:` token.
        limit: Maximum number of rows to return.
        offset: Rows to skip, for paging past `limit` (see `count()` for the total).

    Returns:
        Result dicts ordered most-relevant first; for a free-text query, papers that match
        only in their prepared full text follow every summary match. `score` is the raw FTS5
        bm25() value (lower = more relevant), not a 0-1 similarity: it is
        None for the no-query browse path, which instead sorts by title.

    Raises:
        sqlite3.OperationalError: if the free-text query is not valid FTS5
            MATCH syntax (e.g. unbalanced quotes).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        match_expr = _match_expr(query or "", author)
        if _plain_words(query or "", author) and _has_full_text(conn):
            rows = conn.execute(SUMMARY_THEN_FULL_TEXT, (match_expr, match_expr, limit, offset)).fetchall()
            return [_result(r, r["score"], r["snippet"]) for r in rows]
        if match_expr:
            rows = conn.execute(
                f"""
                SELECT d.id, d.stem, d.title, d.authors_raw, d.text_path, d.sum_path,
                       bm25(documents_fts, {_BM25_WEIGHTS}) AS score,
                       snippet(documents_fts, -1, '[', ']', ' ... ', 12) AS snippet
                FROM documents_fts
                JOIN documents d ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ?
                ORDER BY score
                LIMIT ? OFFSET ?
                """,
                (match_expr, limit, offset),
            ).fetchall()
            return [_result(r, r["score"], r["snippet"]) for r in rows]

        rows = conn.execute(
            "SELECT id, stem, title, authors_raw, text_path, sum_path FROM documents "
            "ORDER BY title LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_result(r) for r in rows]
    finally:
        conn.close()
