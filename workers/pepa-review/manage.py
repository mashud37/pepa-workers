#!/usr/bin/env python3
import sys
import argparse
from cli import menu, install, ui


def main():
    parser = argparse.ArgumentParser(prog="manage.py", description="pepa-review")
    sub = parser.add_subparsers(dest="command")

    r = sub.add_parser("review", help="Assemble a literature review (WS1)")
    r.add_argument("--input", default=None, metavar="FILE",
                   help="Path to outline file (default: pick from input/ or editor)")
    r.add_argument("--auto", action="store_true",
                   help="Auto-select works by similarity instead of prompting")

    g = sub.add_parser("gaps", help="Gap-check a draft against the corpus (WS2)")
    g.add_argument("--input", default=None, metavar="FILE",
                   help="Path to draft file (default: pick from input/)")

    e = sub.add_parser("explore", help="Interactive discovery over the corpus (WS3)")
    e.add_argument("--query", default=None, metavar="QUERY",
                   help="Initial query (default: interactive prompt)")

    mp = sub.add_parser("map", help="Generate corpus thematic map (WS4)")
    mp.add_argument("--threads", type=int, default=None, metavar="N",
                    help="Target thread count for k-means fallback (default: auto)")

    ix = sub.add_parser("index", help="Build/refresh the embedding index")
    ix.add_argument("--force", action="store_true", help="Rebuild from scratch")

    sub.add_parser("config", help="Show effective configuration")
    sub.add_parser("install", help="Set up files and check dependencies")

    args = parser.parse_args()

    if args.command is None:
        return menu.main()
    if args.command == "review":
        from cli import review
        review.run(outline_file=args.input, auto=args.auto)
    elif args.command == "gaps":
        from cli import gaps
        gaps.run(input_file=args.input)
    elif args.command == "explore":
        from cli import explore
        explore.run(query=args.query)
    elif args.command == "map":
        from cli import map as map_cmd
        map_cmd.run(n_threads=args.threads)
    elif args.command == "index":
        from cli import index_cmd
        index_cmd.run(force=args.force)
    elif args.command == "config":
        from cli import show_config
        show_config.run()
    elif args.command == "install":
        install.run()


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
