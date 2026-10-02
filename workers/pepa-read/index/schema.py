"""Define the SQLite schema: one row per (stem, chapter) document, FTS5 for BM25 search over
each pepa-sum section and, in a second index, over the prepared full text.
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
    body_rowid INTEGER,
    UNIQUE(stem, chapter)
)
"""

CREATE_FTS = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, authors_raw, {", ".join(SECTION_FIELDS)},
    content='documents', content_rowid='id'
)
"""

CREATE_BODIES_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS bodies_fts USING fts5(body, content='')
"""

# User-curated literature lists, kept out of the SCHEMA_VERSION migration
# below (which drops/rebuilds `documents`/`documents_fts`, both fully
# rebuildable from source files) because list membership is user state that
# a reindex or schema bump must never wipe.
CREATE_LISTS = """
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at REAL
)
"""

CREATE_LIST_ITEMS = """
CREATE TABLE IF NOT EXISTS list_items (
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    added_at REAL,
    PRIMARY KEY (list_id, document_id)
)
"""


def ensure_schema(conn) -> bool:
    """Create the schema, wiping stale tables from an older SCHEMA_VERSION first.

    Returns True if a migration (table drop) happened, so the caller can warn
    that a full reindex is needed: the data is fully rebuildable from the
    pepa-prep/pepa-sum source files, so dropping it is safe, just not free.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    migrated = 0 < version < SCHEMA_VERSION
    if version < SCHEMA_VERSION:
        conn.execute("DROP TABLE IF EXISTS documents_fts")
        conn.execute("DROP TABLE IF EXISTS bodies_fts")
        conn.execute("DROP TABLE IF EXISTS documents")
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.execute(CREATE_DOCUMENTS)
    conn.execute(CREATE_FTS)
    conn.execute(CREATE_BODIES_FTS)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(documents)")]
    if "body_rowid" not in columns:
        conn.execute("ALTER TABLE documents ADD COLUMN body_rowid INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS documents_body ON documents(body_rowid)")
    conn.execute(CREATE_LISTS)
    conn.execute(CREATE_LIST_ITEMS)
    conn.commit()
    return migrated
