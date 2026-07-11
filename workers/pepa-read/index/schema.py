"""SQLite schema: one row per (stem, chapter) document, FTS5 for BM25 search.

`body` is carried on `documents` (not just `documents_fts`) because FTS5's
external-content mode (content='documents') re-derives old column text from
the content table by name on every DELETE/snippet() call — it does not keep
its own copy. Without a same-named `body` column there, those calls fail
with "no such column: body". `body` here is the short, curated string built
from the pepa-sum sections (or the title, doc-only) — not the raw full text,
so this stays lean.
"""

CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    stem TEXT NOT NULL,
    chapter TEXT,
    title TEXT,
    authors_raw TEXT,
    body TEXT,
    text_path TEXT,
    sum_path TEXT,
    text_mtime REAL,
    sum_mtime REAL,
    indexed_at REAL,
    UNIQUE(stem, chapter)
)
"""

CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, authors_raw, body,
    content='documents', content_rowid='id'
)
"""


def ensure_schema(conn):
    conn.execute(CREATE_DOCUMENTS)
    conn.execute(CREATE_FTS)
    conn.commit()
