#!/usr/bin/env python3
import argparse
import io
import sys

import config
from cli import install, menu, ui


def _build_parser():
    parser = argparse.ArgumentParser(prog=config.COMMAND, description="pepa-review")
    parser.add_argument("--no-input", action="store_true", help="Never ask a question: each one takes its default answer")
    sub = parser.add_subparsers(dest="command")

    r = sub.add_parser("review", help="Assemble a literature review")
    r.add_argument("--input", default=None, metavar="FILE",
                   help="Path to outline file (default: pick from input/ or editor)")
    r.add_argument("--auto", action="store_true",
                   help="Auto-select works by similarity instead of prompting")
    r.add_argument("--list", default=None, metavar="FILE",
                   help="Path to a stem list (e.g. exported from pepa-reader) to select works from")

    g = sub.add_parser("gaps", help="Gap-check a draft against the corpus")
    g.add_argument("--input", default=None, metavar="FILE",
                   help="Path to draft file (default: pick from input/)")

    e = sub.add_parser("explore", help="Interactive discovery over the corpus")
    e.add_argument("--query", default=None, metavar="QUERY",
                   help="Initial query (default: interactive prompt)")

    mp = sub.add_parser("map", help="Generate corpus thematic map")
    mp.add_argument("--threads", type=int, default=None, metavar="N",
                    help="Target thread count for k-means fallback (default: auto)")

    tm = sub.add_parser("threadmap", help="Re-cluster one thread of a saved map in detail")
    tm.add_argument("--map", default=None, metavar="FILE",
                    help="Corpus map file in output/ (default: pick interactively)")
    tm.add_argument("--thread", default=None, metavar="N|NAME|all",
                    help="Thread number, name substring, or 'all' (default: pick interactively)")

    ix = sub.add_parser("index", help="Build/refresh the embedding index")
    ix.add_argument("--force", action="store_true", help="Rebuild from scratch")

    sub.add_parser("config", help="Show effective configuration")
    sub.add_parser("install", help="Set up files and check dependencies")

    bi = sub.add_parser("biblio", help="Bibliographic enrichment (ingest, export, stats, network)")
    bi.add_argument("subcmd", choices=["ingest", "export", "stats", "network"],
                    help="ingest | export | stats | network")
    bi.add_argument("--works", default=None, metavar="FILE",
                    help="Works metadata file (CSV or JSONL), required for ingest")
    bi.add_argument("--citations", default=None, metavar="FILE",
                    help="Citations edge-list file (CSV or JSONL), optional for ingest")
    bi.add_argument("--graph-type", default="citation", choices=["citation", "coupling"],
                    metavar="TYPE", help="citation (default) or coupling")
    bi.add_argument("--format", default="html", choices=["html", "graphml"],
                    metavar="FMT", help="html (default) or graphml")
    bi.add_argument("--output", default=None, metavar="DIR",
                    help="Output directory (default: output/)")

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()
    if args.no_input:
        sys.stdin = io.StringIO()

    if args.command is None:
        return menu.main()
    if args.command == "review":
        from cli import review
        review.run(outline_file=args.input, auto=args.auto, list_file=args.list)
    elif args.command == "gaps":
        from cli import gaps
        gaps.run(input_file=args.input)
    elif args.command == "explore":
        from cli import explore
        explore.run(query=args.query)
    elif args.command == "map":
        from cli import map as map_cmd
        map_cmd.run(n_threads=args.threads)
    elif args.command == "threadmap":
        from cli import thread_map
        thread_map.run(map_file=args.map, thread=args.thread)
    elif args.command == "index":
        from cli import index_cmd
        index_cmd.run(force=args.force)
    elif args.command == "config":
        from cli import show_config
        show_config.run()
    elif args.command == "install":
        install.run()
    elif args.command == "biblio":
        from cli import biblio_cmd
        biblio_cmd.run(args.subcmd, {
            "works_file": args.works,
            "citations_file": args.citations,
            "graph_type": args.graph_type,
            "fmt": args.format,
            "output_dir": args.output,
        })


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(0)
    except SystemExit as e:
        if isinstance(e.code, str):
            ui.error(e.code)
            sys.exit(1)
        raise
