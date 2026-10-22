#!/usr/bin/env python3
import argparse
import io
import sys

import config
from cli import install, menu, ui


def _build_parser():
    parser = argparse.ArgumentParser(prog=config.COMMAND, description="pepa-plan")
    parser.add_argument("--no-input", action="store_true", help="Never ask a question: each one takes its default answer")
    sub = parser.add_subparsers(dest="command")

    ab = sub.add_parser("abstract", help="Build skeleton library from pepa-sum corpus")
    ab.add_argument("--limit", type=int, default=None, metavar="N",
                    help="Use only the first N para files")
    ab.add_argument("--sample", type=int, default=None, metavar="N",
                    help="Use a random sample of N para files")
    ab.add_argument("--mode", default=None, choices=("auto", "serial", "parallel", "batch"),
                    help="Labelling execution mode (default: auto, picks by est. time)")
    ab.add_argument("--estimate", action="store_true", help="Print the papers to label, each mode's time and the cost as JSON, then stop")
    ab.add_argument("--more", type=int, default=0, help="With --estimate, count this many papers more than the corpus holds")
    ab.add_argument("--with-blueprints", action="store_true", help="Then build the within-section blueprints too")
    ab.add_argument("--approve-cost", nargs="?", type=float, const=float("inf"), default=None, metavar="DOLLARS", help="Spend without asking; with an amount, stop before spending if the estimate is higher")

    sub.add_parser("blueprint", help="Build within-section paragraph-progression blueprints")

    ol = sub.add_parser("outline", help="Generate a paragraph-by-paragraph outline")
    ol.add_argument("--input", default=None, metavar="FILE",
                    help="Path to idea file (default: pick from input/ or prompt)")
    ol.add_argument("--literature", default=None, metavar="FILE",
                    help="Optional literature notes file")
    ol.add_argument("--template", default=None, metavar="FILE",
                    help="Plan template to follow (default: pick, else a skeleton)")
    ol.add_argument("--skeleton-id", default=None, metavar="ID",
                    help="Skeleton ID to use (default: pick interactively)")
    ol.add_argument("--feedback", default=None, metavar="TEXT",
                    help="One scripted feedback pass (no interactive loop)")
    ol.add_argument("--no-skeleton", action="store_true", help="Let the model choose the structure instead of a learned skeleton")
    ol.add_argument("--revise", default=None, metavar="FILE", help="Rewrite this earlier outline to follow --feedback, as a new outline")
    ol.add_argument("-o", "--output", default=None, metavar="NAME", help="File name for the outline in output/ (default: from the time)")
    ol.add_argument("--estimate", action="store_true", help="Print the most the outline can cost as JSON, and stop")

    rv = sub.add_parser("review", help="Argumentation-flow feedback on idea or draft")
    rv.add_argument("--input", default=None, metavar="FILE",
                    help="Path to idea or draft file (default: pick from input/)")
    rv.add_argument("-o", "--output", default=None, metavar="NAME", help="File name for the feedback in output/ (default: from the time)")
    rv.add_argument("--estimate", action="store_true", help="Print the most the feedback can cost as JSON, and stop")

    tp = sub.add_parser("template", help="Manage plan templates (section/paragraph progressions)")
    tp.add_argument("--new", default=None, metavar="NAME",
                    help="Create a new template by copying the example")
    tp.add_argument("--list", action="store_true", help="List existing templates")

    cf = sub.add_parser("config", help="Show effective configuration")
    cf.add_argument("--json", action="store_true", help="Print the settings as one JSON line")
    sub.add_parser("install", help="Set up files and check dependencies")
    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()
    if args.no_input:
        sys.stdin = io.StringIO()

    if args.command is None:
        return menu.main()
    if args.command == "abstract" and args.estimate:
        from skeleton import build
        return build.print_estimate(limit=args.limit, sample=args.sample, mode=args.mode, more=args.more)
    elif args.command == "abstract":
        from cli import abstract
        return abstract.run(limit=args.limit, sample=args.sample, mode=args.mode, approved=args.approve_cost, with_blueprints=args.with_blueprints)
    elif args.command == "blueprint":
        from cli import blueprint
        return blueprint.run()
    elif args.command == "outline":
        from cli import outline
        return outline.run({
            "input_file": args.input,
            "literature_file": args.literature,
            "skeleton_id": args.skeleton_id,
            "feedback": args.feedback,
            "no_input": args.no_input,
            "template_file": args.template,
            "no_skeleton": args.no_skeleton,
            "revise_file": args.revise,
            "only_estimate": args.estimate,
            "output_name": args.output,
        })
    elif args.command == "template":
        from cli import templates
        return templates.run(new=args.new, show=args.list)
    elif args.command == "review":
        from cli import review
        return review.run(input_file=args.input, only_estimate=args.estimate, output_name=args.output)
    elif args.command == "config":
        from cli import show_config
        return show_config.run(as_json=args.json)
    elif args.command == "install":
        return install.run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Interrupted.", file=sys.stderr)
        sys.exit(0)
    except SystemExit as e:
        if isinstance(e.code, str):
            ui.error(e.code)
            sys.exit(1)
        raise
