"""HTTP routes: search page, JSON search API, document viewer, open-in-app."""
import os
import sqlite3
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request
from markupsafe import escape

import config
from index import lists as list_store
from index.schema import ensure_schema
from search.query import count, search

bp = Blueprint("reader", __name__)


def _connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    # Cheap and idempotent (CREATE TABLE IF NOT EXISTS) — covers reader.db files
    # built before the lists/list_items tables existed, without a full reindex.
    ensure_schema(conn)
    return conn

_VIEW_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body>
<div class="viewer">
  <div class="page-header">
    <button id="back-btn" class="link-btn">&larr; back to search</button>
    <button id="theme-toggle" class="theme-toggle" title="Toggle light/dark theme"
            aria-label="Toggle theme">&#9789;</button>
  </div>
  <h1>{title}</h1>
  <p class="meta">{authors}</p>
  <div class="open-actions">{open_buttons}</div>
  <span id="open-status"></span>
  <div class="content">{content}</div>
</div>
<script src="/static/theme.js"></script>
<script>
document.getElementById("back-btn").addEventListener("click", () => {{
  if (document.referrer && document.referrer.includes(location.host)) {{
    history.back();
  }} else {{
    location.href = "/";
  }}
}});
document.querySelectorAll(".open-btn").forEach((btn) => {{
  btn.addEventListener("click", async () => {{
    const status = document.getElementById("open-status");
    status.textContent = " opening...";
    const res = await fetch(`/open/${{btn.dataset.id}}?which=${{btn.dataset.which}}`, {{method: "POST"}});
    const data = await res.json();
    status.textContent = data.ok ? " opened" : ` failed: ${{data.error}}`;
  }});
}});
</script>
</body></html>"""


def _doc_row(doc_id: int):
    conn = _connect()
    try:
        return conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    finally:
        conn.close()


def open_document(doc_id: int, which: str | None = None) -> str:
    """Open a document's file in its default Windows app; used by both the
    CLI `open` command and the POST /open/<id> route.

    Args:
        doc_id: The document's row id.
        which: "text" or "sum" to pick a specific file when both exist;
            None falls back to the summary if present, else the raw text.
    """
    row = _doc_row(doc_id)
    if row is None:
        raise SystemExit(f"no document with id {doc_id}")
    if which == "text":
        path = row["text_path"]
    elif which == "sum":
        path = row["sum_path"]
    else:
        path = row["sum_path"] or row["text_path"]
    if not path:
        label = {"text": "text", "sum": "summary"}.get(which, "text/summary")
        raise SystemExit(f"document {doc_id} has no {label} file on disk")
    try:
        os.startfile(path)
    except OSError:
        raise SystemExit(f"{path} is indexed but missing on disk — the file may have moved; "
                          "try reindexing") from None
    return path


@bp.route("/")
def index():
    return render_template("search.html")


@bp.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    author = request.args.get("author") or None
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    try:
        results = search(config.DB_PATH, q, author=author, limit=limit, offset=offset)
        total = count(config.DB_PATH, q, author=author)
    except sqlite3.OperationalError as e:
        return jsonify({"error": str(e)}), 400
    conn = _connect()
    try:
        memberships = list_store.memberships_for(conn, [r["id"] for r in results])
    finally:
        conn.close()
    for r in results:
        r["lists"] = memberships.get(r["id"], [])
    return jsonify({"results": results, "total": total, "offset": offset, "limit": limit})


def _open_buttons_html(doc_id: int, has_text: bool, has_sum: bool) -> str:
    buttons = []
    if has_text:
        buttons.append(
            f'<button class="open-btn" data-id="{doc_id}" data-which="text" '
            'title="Launch the pepa-prep text file in its default Windows app">Open text</button>'
        )
    if has_sum:
        buttons.append(
            f'<button class="open-btn" data-id="{doc_id}" data-which="sum" '
            'title="Launch the pepa-sum summary file in its default Windows app">Open summary</button>'
        )
    return "\n    ".join(buttons)


@bp.route("/view/<int:doc_id>")
def view(doc_id):
    row = _doc_row(doc_id)
    if row is None:
        return f"no document with id {doc_id}", 404
    which = request.args.get("which")
    if which == "text":
        path, label = row["text_path"], "text"
    elif which == "sum":
        path, label = row["sum_path"], "summary"
    else:
        path, label = (row["sum_path"], "summary") if row["sum_path"] else (row["text_path"], "text")
    if not path:
        return f"document {doc_id} has no {'text' if which == 'text' else 'summary'} file on disk", 404
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return f"{path} is indexed but missing on disk — the file may have moved; try reindexing", 404
    try:
        import markdown
        content = markdown.markdown(text)
    except ImportError:
        content = f"<pre>{escape(text)}</pre>"
    return _VIEW_PAGE.format(
        title=escape(row["title"] or row["stem"]),
        authors=escape(f"{row['authors_raw'] or ''} · viewing: {label}"),
        doc_id=doc_id,
        open_buttons=_open_buttons_html(doc_id, bool(row["text_path"]), bool(row["sum_path"])),
        content=content,
    )


@bp.route("/open/<int:doc_id>", methods=["POST"])
def open_route(doc_id):
    which = request.args.get("which")
    try:
        path = open_document(doc_id, which=which)
    except SystemExit as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    return jsonify({"ok": True, "path": str(path)})


# ── literature lists ───────────────────────────────────────────────────────

@bp.route("/api/lists", methods=["GET"])
def api_lists():
    conn = _connect()
    try:
        return jsonify({"lists": list_store.list_summaries(conn)})
    finally:
        conn.close()


@bp.route("/api/lists", methods=["POST"])
def api_lists_create():
    name = (request.get_json(silent=True) or {}).get("name", "")
    conn = _connect()
    try:
        list_id = list_store.create_list(conn, name)
    except (ValueError, list_store.DuplicateListName) as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    finally:
        conn.close()
    return jsonify({"ok": True, "id": list_id, "name": name.strip()})


@bp.route("/api/lists/<int:list_id>", methods=["PATCH"])
def api_lists_rename(list_id):
    name = (request.get_json(silent=True) or {}).get("name", "")
    conn = _connect()
    try:
        list_store.rename_list(conn, list_id, name)
    except (ValueError, list_store.DuplicateListName) as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    finally:
        conn.close()
    return jsonify({"ok": True})


@bp.route("/api/lists/<int:list_id>", methods=["DELETE"])
def api_lists_delete(list_id):
    conn = _connect()
    try:
        list_store.delete_list(conn, list_id)
    finally:
        conn.close()
    return jsonify({"ok": True})


@bp.route("/api/lists/<int:list_id>/items", methods=["GET"])
def api_list_items(list_id):
    conn = _connect()
    try:
        items = list_store.list_items(conn, list_id)
        memberships = list_store.memberships_for(conn, [i["id"] for i in items])
    finally:
        conn.close()
    for i in items:
        i["lists"] = memberships.get(i["id"], [])
    return jsonify({"items": items})


@bp.route("/api/lists/<int:list_id>/items/<int:doc_id>", methods=["POST"])
def api_list_item_add(list_id, doc_id):
    conn = _connect()
    try:
        list_store.add_item(conn, list_id, doc_id)
    finally:
        conn.close()
    return jsonify({"ok": True})


@bp.route("/api/lists/<int:list_id>/items/<int:doc_id>", methods=["DELETE"])
def api_list_item_remove(list_id, doc_id):
    conn = _connect()
    try:
        list_store.remove_item(conn, list_id, doc_id)
    finally:
        conn.close()
    return jsonify({"ok": True})


@bp.route("/list/<int:list_id>/export")
def list_export(list_id):
    conn = _connect()
    try:
        row = list_store.get_list_by_id(conn, list_id)
        if row is None:
            return f"no list with id {list_id}", 404
        stems = list_store.export_stems(conn, list_id)
    finally:
        conn.close()
    body = "\n".join(stems) + ("\n" if stems else "")
    return Response(
        body,
        mimetype="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{row["name"]}.txt"'},
    )
