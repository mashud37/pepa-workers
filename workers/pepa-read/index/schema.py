"""SQLite schema: one row per (stem, chapter) document, FTS5 for BM25 search.

Each pepa-sum section (see index/scan.py SECTION_FIELDS) is its own column,
not one concatenated blob, so a query can target a specific field (e.g.
`lit:foucault`) via FTS5's native `column:term` filter syntax. Those columns
are carried on `documents` too (not just `documents_fts`) because FTS5's
external-content mode (content='documents') re-derives old column text from
the content table by name on every DELETE/snippet() call — it does not keep
its own copy. Without same-named columns there, those calls fail with
"no such column: ...".
"""
from index.scan import SECTION_FIELDS

SCHEMA_VERSION = 2

CREATE_DOCUMENTS = f"""
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    stem TEXT NOT NULL,
    chapter TEXT,
    title TEXT,
    authors_raw TEXT,
    {", ".join(f"{f} TEXT" for f in SECTION_FIELDS)},
    text_path TEXT,
    sum_path TEXT,
    text_mtime REAL,
    sum_mtime REAL,
    indexed_at REAL,
    UNIQUE(stem, chapter)
)
"""

CREATE_FTS = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, authors_raw, {", ".join(SECTION_FIELDS)},
    content='documents', content_rowid='id'
)
"""


def ensure_schema(conn) -> bool:
    """Create the schema, wiping stale tables from an older SCHEMA_VERSION first.

    Returns True if a migration (table drop) happened, so the caller can warn
    that a full reindex is needed — the data is fully rebuildable from the
    pepa-prep/pepa-sum source files, so dropping it is safe, just not free.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    migrated = 0 < version < SCHEMA_VERSION
    if version < SCHEMA_VERSION:
        conn.execute("DROP TABLE IF EXISTS documents_fts")
        conn.execute("DROP TABLE IF EXISTS documents")
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.execute(CREATE_DOCUMENTS)
    conn.execute(CREATE_FTS)
    conn.commit()
    return migrated
