"""BM25 keyword search over documents_fts, shared by manage.py and the Flask API."""
import re
import sqlite3

_AUTHOR_TOKEN_RE = re.compile(r"\bauthor:(\S+)")


def _split_inline_author(text: str) -> tuple[str, str | None]:
    m = _AUTHOR_TOKEN_RE.search(text)
    if not m:
        return text.strip(), None
    remainder = (text[:m.start()] + text[m.end():]).strip()
    return remainder, m.group(1)


def _match_expr(text: str, author: str | None) -> str:
    parts = []
    if text:
        parts.append(_AUTHOR_TOKEN_RE.sub(lambda m: f'authors_raw:{m.group(1)}', text))
    if author:
        parts.append(f'authors_raw:"{author}"')
    return " AND ".join(p for p in parts if p)


def _result(row, score=None, snippet=""):
    return {
        "id": row["id"],
        "title": row["title"],
        "authors_raw": row["authors_raw"],
        "has_text": bool(row["text_path"]),
        "has_sum": bool(row["sum_path"]),
        "text_path": row["text_path"],
        "sum_path": row["sum_path"],
        "snippet": snippet,
        "score": score,
    }


def search(db_path, query: str = "", author: str | None = None, limit: int = 20) -> list[dict]:
    """Rank documents by BM25 relevance to `query`, optionally filtered by author.

    Args:
        db_path: Path to the reader.db SQLite file.
        query: Free-text query. An inline `author:name` token is honored the
            same as the explicit `author` arg (FTS5 column-filter syntax).
        author: Explicit author filter, ANDed with any inline token.
        limit: Maximum number of rows to return.

    Returns:
        Result dicts ordered most-relevant first. `score` is the raw FTS5
        bm25() value (lower = more relevant), not a 0-1 similarity — it is
        None for the no-query browse path, which instead sorts by title.

    Raises:
        sqlite3.OperationalError: if the free-text query is not valid FTS5
            MATCH syntax (e.g. unbalanced quotes).
    """
    text, inline_author = _split_inline_author(query or "")
    author = author or inline_author

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        match_expr = _match_expr(text, author)
        if match_expr:
            rows = conn.execute(
                """
                SELECT d.id, d.title, d.authors_raw, d.text_path, d.sum_path,
                       bm25(documents_fts, 5.0, 2.0, 1.0) AS score,
                       snippet(documents_fts, 2, '[', ']', ' ... ', 12) AS snippet
                FROM documents_fts
                JOIN documents d ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (match_expr, limit),
            ).fetchall()
            return [_result(r, r["score"], r["snippet"]) for r in rows]

        rows = conn.execute(
            "SELECT id, title, authors_raw, text_path, sum_path FROM documents "
            "ORDER BY title LIMIT ?",
            (limit,),
        ).fetchall()
        return [_result(r) for r in rows]
    finally:
        conn.close()
