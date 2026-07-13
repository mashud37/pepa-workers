#!/usr/bin/env python3
import argparse
import json
import sys

from cli import ui


def _cmd_index(args):
    from index.build import run
    run(force=args.force)


def _cmd_search(args):
    import config
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
        print(f"          {r['sum_path'] or r['text_path']}")

    shown_from = args.offset + 1
    shown_to = args.offset + len(results)
    more = f"  (--offset {shown_to} for more)" if shown_to < total else ""
    print(f"\nshowing {shown_from}-{shown_to} of {total}{more}", file=sys.stderr)


def _cmd_serve(args):
    import config
    from web.app import run
    run(port=args.port or config.PORT, open_browser=not args.no_browser)


def _cmd_open(args):
    from web.routes import open_document
    print(open_document(args.id, which=args.which))


def _cmd_install(args):
    from cli.install import run
    run()


def _bare(args):
    if not sys.stdout.isatty():
        print(
            "pepa-reader: not an interactive terminal. Use "
            '`python manage.py serve --no-browser` or `python manage.py search "..."`.',
            file=sys.stderr,
        )
        return 0
    import config
    from index.build import index_exists
    from index.build import run as build_index
    if not index_exists():
        build_index(force=False)
    from web.app import run
    run(port=config.PORT, open_browser=True)
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Read-only keyword search over pepa-prep and pepa-sum markdown output",
    )
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

    args = parser.parse_args()

    if args.command is None:
        return _bare(args)
    if args.command == "index":
        _cmd_index(args)
    elif args.command == "search":
        _cmd_search(args)
    elif args.command == "serve":
        _cmd_serve(args)
    elif args.command == "open":
        _cmd_open(args)
    elif args.command == "install":
        _cmd_install(args)
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
