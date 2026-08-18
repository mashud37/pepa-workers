"""Define the SQLite schema for bibliographic enrichment: works and
citations tables keyed on `base`, the pepa-sum filename stem, so they join
cleanly to index.json records.
"""
import sqlite3
import config


DDL = """
CREATE TABLE IF NOT EXISTS works (
    base             TEXT PRIMARY KEY,
    doi              TEXT,
    ext_id           TEXT,
    title            TEXT,
    authors          TEXT,
    venue            TEXT,
    year             INTEGER,
    type             TEXT,
    cited_by_count   INTEGER,
    concepts         TEXT,
    match_confidence REAL DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS works_ext_id ON works(ext_id);
CREATE INDEX IF NOT EXISTS works_doi    ON works(doi);

CREATE TABLE IF NOT EXISTS citations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    citing_base      TEXT NOT NULL,
    cited_ext_id     TEXT,
    cited_doi        TEXT,
    cited_title      TEXT,
    cited_authors    TEXT,
    cited_year       INTEGER,
    cited_base       TEXT
);

CREATE INDEX IF NOT EXISTS citations_citing ON citations(citing_base);
CREATE INDEX IF NOT EXISTS citations_cited  ON citations(cited_base);
"""


def connect(path=None):
    """Return an open sqlite3 connection with row_factory set."""
    db_path = path or config.BIBLIO_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def ensure_schema(con):
    con.executescript(DDL)
    con.commit()
