#!/usr/bin/env python3
import argparse
import sys

from cli import eval_cmd, extract_cmd, install, refine_cmd, split_cmd, ui, validate_cmd
from cli import menu as menu_mod
from extract import config as cfg_mod


def _add_pipeline_parsers(sub) -> None:
    sub.add_parser("extract", help="Categorise and extract PDFs to markdown")
    v = sub.add_parser("validate", help="Grade book chapters, quarantine junk, renumber")
    v.add_argument("-n", "--dry-run", action="store_true", help="Report only, move nothing")
    sp = sub.add_parser("split", help="Manually correct chapter boundaries in any book")
    sp.add_argument("--file", metavar="PATH_OR_STEM",
                    help="Path or stem of a specific book (omit for interactive search)")
    rf = sub.add_parser("refine", help="Repair chapter files from text signals: merge "
                        "over-splits, split merged chapters, demote junk headings")
    rf.add_argument("--apply", action="store_true",
                    help="Write the repairs (default: diagnosis report only)")
    rf.add_argument("--book", metavar="STEM",
                    help="Only refine books whose stem contains STEM")
    sub.add_parser("install", help="Check dependencies")


def _add_eval_parsers(sub) -> None:
    lab = sub.add_parser("label", help="Create correctable segmentation tag files from PDFs")
    lab.add_argument("-i", "--input", help="Folder of PDFs (default: configured input folder)")
    sub.add_parser("score", help="Score segmentation against corrected tag files")
    lc = sub.add_parser("label-chapters",
                        help="Create correctable chapter-boundary gold files for books")
    lc.add_argument("-i", "--input", help="Folder of PDFs (default: selection.tsv "
                    "in data/eval/chapters)")
    sub.add_parser("score-chapters", help="Score chapter detection against corrected gold files")
    sub.add_parser("label-refine",
                   help="Create correctable unit gold files from current chapter files")
    sub.add_parser("score-refine", help="Score markdown refinement against corrected gold files")


def _add_biblio_parser(sub) -> None:
    b = sub.add_parser("biblio", help="Fetch bibliography from OpenAlex for pepa-sum papers")
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


def _run_biblio(cfg, args) -> None:
    run_cfg = dict(cfg)
    if args.corpus:
        run_cfg["biblio_corpus"] = args.corpus
    from cli import biblio_cmd
    biblio_cmd.run(run_cfg, zotero=args.zotero, cite=args.cite,
                   force=args.force, quiet=args.quiet)


def _dispatch(args, cfg) -> None:
    handlers = {
        "extract": lambda: extract_cmd.run(cfg),
        "split": lambda: split_cmd.run(cfg, file=args.file),
        "validate": lambda: validate_cmd.run(cfg, dry=args.dry_run),
        "install": lambda: install.run(),
        "refine": lambda: refine_cmd.run(cfg, apply=args.apply, book=args.book),
        "label": lambda: eval_cmd.label(cfg, args.input),
        "score": lambda: eval_cmd.score(cfg),
        "label-chapters": lambda: eval_cmd.label_chapters(cfg, args.input),
        "score-chapters": lambda: eval_cmd.score_chapters(cfg),
        "label-refine": lambda: eval_cmd.label_refine(cfg),
        "score-refine": lambda: eval_cmd.score_refine(cfg),
        "biblio": lambda: _run_biblio(cfg, args),
    }
    handlers[args.command]()


def main():
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Local PDF-to-markdown extraction pipeline",
    )
    sub = parser.add_subparsers(dest="command")
    _add_pipeline_parsers(sub)
    _add_eval_parsers(sub)
    _add_biblio_parser(sub)
    args = parser.parse_args()
    if args.command is None:
        return menu_mod.main()
    _dispatch(args, cfg_mod.load())


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
