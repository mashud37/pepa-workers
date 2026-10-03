#!/usr/bin/env python3
import argparse
import io
import json
import sys

import config
from cli import ui


def _cmd_search(args):
    from index import files
    from search.query import count, search
    try:
        results = search(config.DB_PATH, args.query, author=args.author,
                          limit=args.limit, offset=args.offset)
        total = count(config.DB_PATH, args.query, author=args.author)
    except Exception as e:
        raise SystemExit(str(e))

    if args.json:
        print(json.dumps({"results": results, "total": total, "offset": args.offset}, indent=2))
        return
    if not results:
        print("no results", file=sys.stderr)
        return
    for r in results:
        flags = ("T" if r["has_text"] else "-") + ("S" if r["has_sum"] else "-")
        print(f"[{r['id']:>5}] {flags}  {r['stem']}")
        print(f"          {r['title']}  -- {r['authors_raw'] or '?'}")
        print(f"          {files.sum_file(r['sum_path']) or files.text_file(r['text_path'])}")

    shown_from = args.offset + 1
    shown_to = args.offset + len(results)
    more = f"  (--offset {shown_to} for more)" if shown_to < total else ""
    print(f"\nshowing {shown_from}-{shown_to} of {total}{more}", file=sys.stderr)


def _list_conn():
    import sqlite3

    from index.schema import ensure_schema
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def _find_list(conn, name):
    from index import lists as list_store
    row = list_store.get_list_by_name(conn, name)
    if row is None:
        raise SystemExit(f"no list named '{name}'")
    return row


def _cmd_lists(args):
    from index import lists as list_store
    conn = _list_conn()
    try:
        summaries = list_store.list_summaries(conn)
    finally:
        conn.close()
    if not summaries:
        print("no lists yet", file=sys.stderr)
        return
    for s in summaries:
        print(f"{s['name']}  ({s['count']} item{'s' if s['count'] != 1 else ''})")


def _cmd_list_show(args):
    from index import lists as list_store
    conn = _list_conn()
    try:
        row = _find_list(conn, args.name)
        items = list_store.list_items(conn, row["id"])
    finally:
        conn.close()
    if not items:
        print("(empty)", file=sys.stderr)
        return
    for it in items:
        print(f"{it['stem']}  {it['title']}  -- {it['authors_raw'] or '?'}")


def _cmd_list_export(args):
    from index import lists as list_store
    conn = _list_conn()
    try:
        row = _find_list(conn, args.name)
        stems = list_store.export_stems(conn, row["id"])
    finally:
        conn.close()
    body = "\n".join(stems) + ("\n" if stems else "")
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(body, encoding="utf-8")
        print(f"wrote {len(stems)} stem(s) to {args.output}", file=sys.stderr)
    else:
        print(body, end="")


def _cmd_list_delete(args):
    from cli import ui
    from index import lists as list_store
    conn = _list_conn()
    try:
        row = _find_list(conn, args.name)
        if not args.yes and not ui.confirm(f"Delete list '{args.name}' ({row['id']})?", default_yes=False):
            return
        list_store.delete_list(conn, row["id"])
    finally:
        conn.close()
    ui.ok(f"deleted list '{args.name}'")


def _bare(args):
    if not sys.stdout.isatty():
        print(
            "pepa-read: not an interactive terminal. Use "
            f'`{config.COMMAND} serve --no-browser` or `{config.COMMAND} search "..."`.',
            file=sys.stderr,
        )
        return 0
    from index.build import index_exists
    from index.build import run as build_index
    if not index_exists():
        build_index(force=False)
    from web.app import run
    run(port=config.PORT, open_browser=True)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=config.COMMAND,
        description="Read-only keyword search over pepa-prep and pepa-sum markdown output",
    )
    parser.add_argument("--no-input", action="store_true", help="Never ask a question: each one takes its default answer")
    sub = parser.add_subparsers(dest="command")

    ix = sub.add_parser("index", help="Scan pepa-prep/pepa-sum output and build the search index")
    ix.add_argument("--force", action="store_true", help="Reindex every file, ignoring mtimes")

    se = sub.add_parser("search", help="One-shot keyword search")
    se.add_argument("query", help='Free-text query, e.g. "brand personality" or '
                                   '"lit:foucault author:aaker" (field tokens: author/title/'
                                   'context/empirical/lit/methods/arguments/conclusions/discussion)')
    se.add_argument("--author", default=None, metavar="NAME", help="Filter by author")
    se.add_argument("--limit", type=int, default=20, metavar="N")
    se.add_argument("--offset", type=int, default=0, metavar="N", help="Skip the first N results")
    se.add_argument("--json", action="store_true", help="Emit JSON instead of a table")

    sv = sub.add_parser("serve", help="Start the local web UI")
    sv.add_argument("--port", type=int, default=None, metavar="N")
    sv.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")

    op = sub.add_parser("open", help="Open a document in its default Windows app")
    op.add_argument("id", type=int)
    op.add_argument("--which", choices=["text", "sum"], default=None,
                     help="Which file to open when both exist (default: summary, else text)")

    sub.add_parser("install", help="Check dependencies and source directories")

    sub.add_parser("lists", help="Show all literature lists and their item counts")

    ls = sub.add_parser("list-show", help="Show the documents in a literature list")
    ls.add_argument("name", help="List name")

    le = sub.add_parser("list-export", help="Export a list's document stems, one per line")
    le.add_argument("name", help="List name")
    le.add_argument("-o", "--output", default=None, metavar="FILE",
                     help="Write to this file instead of stdout")

    ld = sub.add_parser("list-delete", help="Delete a literature list")
    ld.add_argument("name", help="List name")
    ld.add_argument("-y", "--yes", action="store_true", help="Delete without asking")

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()
    if args.no_input:
        sys.stdin = io.StringIO()

    if args.command is None:
        return _bare(args)
    if args.command == "index":
        from index.build import run
        run(force=args.force)
    elif args.command == "search":
        _cmd_search(args)
    elif args.command == "serve":
        from web.app import run
        run(port=args.port or config.PORT, open_browser=not args.no_browser)
    elif args.command == "open":
        from web.routes import open_document
        print(open_document(args.id, which=args.which))
    elif args.command == "install":
        from cli.install import run
        run()
    elif args.command == "lists":
        _cmd_lists(args)
    elif args.command == "list-show":
        _cmd_list_show(args)
    elif args.command == "list-export":
        _cmd_list_export(args)
    elif args.command == "list-delete":
        _cmd_list_delete(args)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(0)
    except SystemExit as e:
        if isinstance(e.code, str):
            ui.error(e.code)
            sys.exit(1)
        raise
