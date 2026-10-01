"""Scan pepa-prep/pepa-sum output and upsert into the SQLite search
index. Incremental by default: a (stem, chapter) row is skipped once its
stored text_mtime/sum_mtime match the files on disk.
"""
import sqlite3
import time

import config
from cli import ui
from index import scan
from index.scan import SECTION_FIELDS
from index.schema import ensure_schema

_BATCH = 200


def index_exists() -> bool:
    if not config.DB_PATH.exists():
        return False
    conn = sqlite3.connect(config.DB_PATH)
    try:
        n = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        return n > 0
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def _connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    if ensure_schema(conn):
        ui.warn("index schema upgraded, existing rows were cleared, doing a full reindex")
    return conn


def _existing_row(conn, stem, chapter):
    return conn.execute(
        "SELECT id, text_mtime, sum_mtime FROM documents WHERE stem = ? AND chapter IS ?",
        (stem, chapter),
    ).fetchone()


def _upsert(conn, doc):
    """Write one document row and its search-index entry, returning the row id.

    Args:
        doc: one document's fields, keyed as the `documents` columns are named
            (`stem`, `chapter`, `title`, `authors`, `sections`, `text_path`,
            `sum_path`, `text_mtime`, `sum_mtime`).

    Returns:
        The `documents.id` of the row written.
    """
    stem = doc["stem"]
    chapter = doc["chapter"]
    title = doc["title"]
    authors = doc["authors"]
    text_path = doc["text_path"]
    sum_path = doc["sum_path"]
    text_mtime = doc["text_mtime"]
    sum_mtime = doc["sum_mtime"]
    now = time.time()
    section_values = [doc["sections"].get(f, "") for f in SECTION_FIELDS]
    row = _existing_row(conn, stem, chapter)
    if row:
        doc_id = row[0]
        # Delete the FTS entry before overwriting `documents`: external-content
        # FTS5 re-tokenizes the CURRENT content-table row to know what to
        # remove, so this must run against the old values, not the new ones.
        conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
        set_clause = ", ".join(f"{f}=?" for f in SECTION_FIELDS)
        update_values = (title, authors, *section_values, text_path, sum_path, text_mtime, sum_mtime, now, doc_id)
        conn.execute(
            f"UPDATE documents SET title=?, authors_raw=?, {set_clause}, text_path=?, "
            "sum_path=?, text_mtime=?, sum_mtime=?, indexed_at=? WHERE id=?",
            update_values,
        )
    else:
        col_names = ["stem", "chapter", "title", "authors_raw", *SECTION_FIELDS, "text_path", "sum_path", "text_mtime", "sum_mtime", "indexed_at"]
        placeholders = ", ".join("?" * len(col_names))
        insert_values = (stem, chapter, title, authors, *section_values, text_path, sum_path, text_mtime, sum_mtime, now)
        cur = conn.execute(
            f"INSERT INTO documents ({', '.join(col_names)}) VALUES ({placeholders})",
            insert_values,
        )
        doc_id = cur.lastrowid
    fts_col_names = ["rowid", "title", "authors_raw", *SECTION_FIELDS]
    fts_placeholders = ", ".join("?" * len(fts_col_names))
    conn.execute(
        f"INSERT INTO documents_fts ({', '.join(fts_col_names)}) VALUES ({fts_placeholders})",
        (doc_id, title or "", authors or "", *section_values),
    )
    return doc_id


def _scan_text_dir(text_dir):
    docs = {}
    if not text_dir.exists():
        raise SystemExit(f"text directory not found: {text_dir}")
    ui.info("scanning directory...")
    files = sorted(text_dir.glob("text_*.md"))
    total = len(files)
    for i, path in enumerate(files, 1):
        if i % _BATCH == 0 or i == total:
            ui.info(f"[{i}/{total}] {path.name}")
        found = scan.text_stem_and_chapter(path.name)
        entry = docs.setdefault((found["stem"], found["chapter"]), {})
        entry["text_path"] = path
        entry["text_mtime"] = path.stat().st_mtime
    ui.ok(f"{total} text file(s) found")
    return docs


def _scan_sum_dir(sum_dir, docs):
    if not sum_dir.exists():
        raise SystemExit(f"sum directory not found: {sum_dir}")
    ui.info("scanning directory...")
    files = sorted(sum_dir.glob("sum_*.md"))
    total = len(files)
    for i, path in enumerate(files, 1):
        if i % _BATCH == 0 or i == total:
            ui.info(f"[{i}/{total}] {path.name}")
        found = scan.sum_stem_and_chapter(path.name)
        entry = docs.setdefault((found["stem"], found["chapter"]), {})
        entry["sum_path"] = path
        entry["sum_mtime"] = path.stat().st_mtime
    ui.ok(f"{total} sum file(s) found")


def run(force: bool = False):
    ui.header("pepa-reader index")
    print("  1) scan pepa-prep  2) scan pepa-sum  3) build search index")

    ui.step("1/3 scan pepa-prep")
    docs = _scan_text_dir(config.TEXT_DIR)

    ui.step("2/3 scan pepa-sum")
    _scan_sum_dir(config.SUM_DIR, docs)

    ui.step("3/3 build search index")
    conn = _connect()
    items = sorted(docs.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))
    n_docs = len(items)
    indexed = skipped = 0
    for i, ((book_stem, chapter), d) in enumerate(items, 1):
        if i % _BATCH == 0 or i == n_docs:
            ui.info(f"[{i}/{n_docs}] {book_stem}")

        text_path = d.get("text_path")
        sum_path = d.get("sum_path")
        text_mtime = d.get("text_mtime")
        sum_mtime = d.get("sum_mtime")

        existing = _existing_row(conn, book_stem, chapter)
        if not force and existing:
            _, old_text_mtime, old_sum_mtime = existing
            if old_text_mtime == text_mtime and old_sum_mtime == sum_mtime:
                skipped += 1
                continue

        title = scan.title_from_sum(sum_path) if sum_path else None
        if not title and text_path:
            title = scan.title_from_text(text_path)
        if not title:
            title = book_stem
        sections = scan.parse_sum_sections(sum_path) if sum_path else {}
        authors = scan.authors_raw(book_stem)

        _upsert(conn, {
            "stem": book_stem,
            "chapter": chapter,
            "title": title,
            "authors": authors,
            "sections": sections,
            "text_path": text_path.name if text_path else None,
            "sum_path": sum_path.name if sum_path else None,
            "text_mtime": text_mtime,
            "sum_mtime": sum_mtime,
        })
        indexed += 1

        if i % _BATCH == 0:
            conn.commit()

    conn.commit()
    conn.close()
    ui.ok(f"indexed {indexed} document(s), {skipped} unchanged, {n_docs} total "
          f"-> {config.DB_PATH}")
