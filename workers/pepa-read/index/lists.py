"""Named literature lists — user curation on top of the read-only search index.

A document can belong to any number of named lists. Membership is stored in
`list_items` (see index/schema.py); nothing here touches `documents` or
`documents_fts`, so it is independent of reindexing.
"""
import time


class DuplicateListName(Exception):
    pass


def list_summaries(conn):
    """Return [{id, name, count}, ...] ordered by name."""
    rows = conn.execute(
        "SELECT l.id, l.name, COUNT(li.document_id) AS count "
        "FROM lists l LEFT JOIN list_items li ON li.list_id = l.id "
        "GROUP BY l.id ORDER BY l.name COLLATE NOCASE"
    ).fetchall()
    return [{"id": r[0], "name": r[1], "count": r[2]} for r in rows]


def get_list_by_name(conn, name):
    return conn.execute("SELECT id, name FROM lists WHERE name = ?", (name,)).fetchone()


def get_list_by_id(conn, list_id):
    return conn.execute("SELECT id, name FROM lists WHERE id = ?", (list_id,)).fetchone()


def create_list(conn, name):
    name = name.strip()
    if not name:
        raise ValueError("list name cannot be blank")
    if get_list_by_name(conn, name):
        raise DuplicateListName(f"a list named '{name}' already exists")
    cur = conn.execute(
        "INSERT INTO lists (name, created_at) VALUES (?, ?)", (name, time.time())
    )
    conn.commit()
    return cur.lastrowid


def rename_list(conn, list_id, name):
    name = name.strip()
    if not name:
        raise ValueError("list name cannot be blank")
    existing = get_list_by_name(conn, name)
    if existing and existing[0] != list_id:
        raise DuplicateListName(f"a list named '{name}' already exists")
    conn.execute("UPDATE lists SET name = ? WHERE id = ?", (name, list_id))
    conn.commit()


def delete_list(conn, list_id):
    conn.execute("DELETE FROM list_items WHERE list_id = ?", (list_id,))
    conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    conn.commit()


def add_item(conn, list_id, doc_id):
    conn.execute(
        "INSERT OR IGNORE INTO list_items (list_id, document_id, added_at) VALUES (?, ?, ?)",
        (list_id, doc_id, time.time()),
    )
    conn.commit()


def remove_item(conn, list_id, doc_id):
    conn.execute(
        "DELETE FROM list_items WHERE list_id = ? AND document_id = ?", (list_id, doc_id)
    )
    conn.commit()


def list_items(conn, list_id):
    """Return the documents in a list, in the same shape as a search result row."""
    rows = conn.execute(
        "SELECT d.id, d.stem, d.title, d.authors_raw, d.text_path, d.sum_path "
        "FROM list_items li JOIN documents d ON d.id = li.document_id "
        "WHERE li.list_id = ? ORDER BY li.added_at",
        (list_id,),
    ).fetchall()
    return [
        {
            "id": r[0], "stem": r[1], "title": r[2], "authors_raw": r[3],
            "has_text": bool(r[4]), "has_sum": bool(r[5]),
            "text_path": r[4], "sum_path": r[5], "snippet": "", "score": None,
        }
        for r in rows
    ]


def memberships_for(conn, doc_ids):
    """Return {document_id: [list_id, ...]} for the given ids, for annotating search results."""
    if not doc_ids:
        return {}
    placeholders = ", ".join("?" * len(doc_ids))
    rows = conn.execute(
        f"SELECT document_id, list_id FROM list_items WHERE document_id IN ({placeholders})",
        list(doc_ids),
    ).fetchall()
    out = {}
    for doc_id, list_id in rows:
        out.setdefault(doc_id, []).append(list_id)
    return out


def export_stems(conn, list_id):
    """Return the sorted, deduplicated `stem` values of a list's documents."""
    rows = conn.execute(
        "SELECT DISTINCT d.stem FROM list_items li "
        "JOIN documents d ON d.id = li.document_id "
        "WHERE li.list_id = ? ORDER BY d.stem",
        (list_id,),
    ).fetchall()
    return [r[0] for r in rows]
