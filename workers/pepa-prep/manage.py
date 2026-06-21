#!/usr/bin/env python3
import argparse
import sys

from cli import eval_cmd, extract_cmd, install, split_cmd, ui, validate_cmd
from cli import menu as menu_mod
from extract import config as cfg_mod


def main():
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Local PDF-to-markdown extraction pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("extract", help="Categorise and extract PDFs to markdown")

    v = sub.add_parser("validate", help="Grade book chapters, quarantine junk, renumber")
    v.add_argument("-n", "--dry-run", action="store_true", help="Report only, move nothing")

    sp = sub.add_parser("split", help="Manually mark chapter boundaries in single-block books")
    sp.add_argument("--file", metavar="PATH_OR_STEM",
                    help="Path or stem of a specific single-block file (omit for interactive list)")

    sub.add_parser("install", help="Check dependencies")

    lab = sub.add_parser("label", help="Create correctable segmentation tag files from PDFs")
    lab.add_argument("-i", "--input", help="Folder of PDFs (default: configured input folder)")

    sub.add_parser("score", help="Score segmentation against corrected tag files")

    b = sub.add_parser("biblio", help="Fetch bibliography from Crossref for pepa-sum papers")
    b.add_argument("--zotero", metavar="FILE",
                   help="Zotero CSL-JSON export (omit to auto-detect in input/)")
    b.add_argument("--corpus", metavar="DIR",
                   help="pepa-sum output folder (default: biblio_corpus in config.yaml)")
    b.add_argument("--cite", action="store_true",
                   help="Also fetch citation networks from OpenCitations")
    b.add_argument("-f", "--force", action="store_true",
                   help="Overwrite existing biblio JSON files")
    b.add_argument("-q", "--quiet", action="store_true",
                   help="Suppress per-paper detail lines")

    args = parser.parse_args()

    if args.command is None:
        return menu_mod.main()

    cfg = cfg_mod.load()

    if args.command == "extract":
        extract_cmd.run(cfg)
    elif args.command == "split":
        split_cmd.run(cfg, file=args.file)
    elif args.command == "validate":
        validate_cmd.run(cfg, dry=args.dry_run)
    elif args.command == "install":
        install.run()
    elif args.command == "label":
        eval_cmd.label(cfg, args.input)
    elif args.command == "score":
        eval_cmd.score(cfg)
    elif args.command == "biblio":
        if args.corpus:
            cfg["biblio_corpus"] = args.corpus
        from cli import biblio_cmd
        biblio_cmd.run(cfg, zotero=args.zotero, cite=args.cite,
                       force=args.force, quiet=args.quiet)


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(0)
    except SystemExit as e:
        if isinstance(e.code, str):
            ui.error(e.code)
            sys.exit(1)
        raise
