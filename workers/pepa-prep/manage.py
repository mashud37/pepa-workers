#!/usr/bin/env python3
import argparse
import io
import sys

from cli import config_cmd, extract_cmd, install, refine_cmd, split_cmd, ui, validate_cmd
from cli import menu as menu_mod
from extract import config as cfg_mod

if cfg_mod.EVALUATION_SHIPPED:
    from cli import eval_cmd


def _add_pipeline_parsers(sub) -> None:
    ex = sub.add_parser("extract", help="Categorise and extract PDFs to markdown")
    ex.add_argument("--file", metavar="NAME", help="Only the PDF with this file name")
    ex.add_argument("-f", "--force", action="store_true", help="Prepare again, replacing earlier output")
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
    cf = sub.add_parser("config", help="Show the settings; any flag saves it without asking")
    cf.add_argument("--input-folder", default=None, metavar="DIR", help="Folder of PDFs to prepare")
    cf.add_argument("--output-folder", default=None, metavar="DIR", help="Folder for the markdown")
    cf.add_argument("--subfolders", default=None, choices=("on", "off"), dest="scan_subfolders", help="Also read PDFs inside the input folder's folders")
    cf.add_argument("--workers", type=int, default=None, metavar="N", help="Parallel threads")
    cf.add_argument("--book-page-threshold", type=int, default=None, metavar="N", help="PDFs over this many pages take the book route")
    cf.add_argument("--max-chapters", type=int, default=None, metavar="N", help="More chapters than this and a book becomes one flagged file")
    cf.add_argument("--ocr-dpi", type=int, default=None, metavar="N", help="OCR resolution")
    cf.add_argument("--tesseract", default=None, dest="tesseract_cmd", metavar="PATH", help="Tesseract executable")
    cf.add_argument("--json", action="store_true", help="Print the settings as one JSON line")
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


def _dispatch(args, cfg):
    handlers = {
        "extract": lambda: extract_cmd.run(cfg, file=args.file, force=args.force),
        "split": lambda: split_cmd.run(cfg, file=args.file),
        "validate": lambda: validate_cmd.run(cfg, dry=args.dry_run),
        "install": lambda: install.run(),
        "config": lambda: config_cmd.run(cfg, {
            "input_folder": args.input_folder,
            "output_folder": args.output_folder,
            "scan_subfolders": args.scan_subfolders,
            "workers": args.workers,
            "book_page_threshold": args.book_page_threshold,
            "max_chapters": args.max_chapters,
            "ocr_dpi": args.ocr_dpi,
            "tesseract_cmd": args.tesseract_cmd,
        }, as_json=args.json),
        "refine": lambda: refine_cmd.run(cfg, apply=args.apply, book=args.book),
        "label": lambda: eval_cmd.label(cfg, args.input),
        "score": lambda: eval_cmd.score(cfg),
        "label-chapters": lambda: eval_cmd.label_chapters(cfg, args.input),
        "score-chapters": lambda: eval_cmd.score_chapters(cfg),
        "label-refine": lambda: eval_cmd.label_refine(cfg),
        "score-refine": lambda: eval_cmd.score_refine(cfg),
    }
    return handlers[args.command]()


def main():
    parser = argparse.ArgumentParser(
        prog=cfg_mod.COMMAND,
        description="Local PDF-to-markdown extraction pipeline",
    )
    parser.add_argument("--no-input", action="store_true", help="Never ask a question: each one takes its default answer")
    sub = parser.add_subparsers(dest="command")
    _add_pipeline_parsers(sub)
    if cfg_mod.EVALUATION_SHIPPED:
        _add_eval_parsers(sub)
    args = parser.parse_args()
    if args.no_input:
        sys.stdin = io.StringIO()
    if args.command is None:
        return menu_mod.main()
    return _dispatch(args, cfg_mod.load())


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("\n\n  Interrupted.", file=sys.stderr)
        sys.exit(0)
    except SystemExit as e:
        if isinstance(e.code, str):
            ui.error(e.code)
            sys.exit(1)
        raise
