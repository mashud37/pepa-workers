"""HTTP routes: search page, JSON search API, document viewer, open-in-app."""
import os
import sqlite3
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request
from markupsafe import escape

import config
from search.query import search

bp = Blueprint("reader", __name__)

_VIEW_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body>
<div class="viewer">
  <p><a href="/">&larr; back to search</a></p>
  <h1>{title}</h1>
  <p class="meta">{authors}</p>
  <button id="open-btn" data-id="{doc_id}">Open in app</button>
  <span id="open-status"></span>
  <div class="content">{content}</div>
</div>
<script>
document.getElementById("open-btn").addEventListener("click", async (e) => {{
  const status = document.getElementById("open-status");
  status.textContent = " opening...";
  const res = await fetch(`/open/${{e.target.dataset.id}}`, {{method: "POST"}});
  const data = await res.json();
  status.textContent = data.ok ? " opened" : ` failed: ${{data.error}}`;
}});
</script>
</body></html>"""


def _doc_row(doc_id: int):
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    finally:
        conn.close()


def open_document(doc_id: int) -> str:
    """Open a document's file in its default Windows app; used by both the
    CLI `open` command and the POST /open/<id> route."""
    row = _doc_row(doc_id)
    if row is None:
        raise SystemExit(f"no document with id {doc_id}")
    path = row["sum_path"] or row["text_path"]
    if not path:
        raise SystemExit(f"document {doc_id} has no file on disk")
    os.startfile(path)
    return path


@bp.route("/")
def index():
    return render_template("search.html")


@bp.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    author = request.args.get("author") or None
    limit = request.args.get("limit", 20, type=int)
    try:
        results = search(config.DB_PATH, q, author=author, limit=limit)
    except sqlite3.OperationalError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(results)


@bp.route("/view/<int:doc_id>")
def view(doc_id):
    row = _doc_row(doc_id)
    if row is None:
        return f"no document with id {doc_id}", 404
    path = row["sum_path"] or row["text_path"]
    text = Path(path).read_text(encoding="utf-8", errors="ignore") if path else "(no file on disk)"
    try:
        import markdown
        content = markdown.markdown(text)
    except ImportError:
        content = f"<pre>{escape(text)}</pre>"
    return _VIEW_PAGE.format(
        title=escape(row["title"] or row["stem"]),
        authors=escape(row["authors_raw"] or ""),
        doc_id=doc_id,
        content=content,
    )


@bp.route("/open/<int:doc_id>", methods=["POST"])
def open_route(doc_id):
    try:
        path = open_document(doc_id)
    except SystemExit as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    return jsonify({"ok": True, "path": str(path)})
