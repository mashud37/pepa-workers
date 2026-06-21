#!/usr/bin/env python3
import argparse
import sys

from cli import install, menu, ui


def main():
    parser = argparse.ArgumentParser(prog="manage.py", description="pepa-plan")
    sub = parser.add_subparsers(dest="command")

    ab = sub.add_parser("abstract", help="Build skeleton library from pepa-sum corpus")
    ab.add_argument("--limit", type=int, default=None, metavar="N",
                    help="Use only the first N para files")
    ab.add_argument("--sample", type=int, default=None, metavar="N",
                    help="Use a random sample of N para files")
    ab.add_argument("--mode", default=None, choices=("auto", "serial", "parallel", "batch"),
                    help="Labelling execution mode (default: auto, picks by est. time)")

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
    ol.add_argument("--no-input", action="store_true",
                    help="First shot only; skip interactive feedback loop")

    rv = sub.add_parser("review", help="Argumentation-flow feedback on idea or draft")
    rv.add_argument("--input", default=None, metavar="FILE",
                    help="Path to idea or draft file (default: pick from input/)")

    tp = sub.add_parser("template", help="Manage plan templates (section/paragraph progressions)")
    tp.add_argument("--new", default=None, metavar="NAME",
                    help="Create a new template by copying the example")
    tp.add_argument("--list", action="store_true", help="List existing templates")

    sub.add_parser("config", help="Show effective configuration")
    sub.add_parser("install", help="Set up files and check dependencies")

    args = parser.parse_args()

    if args.command is None:
        return menu.main()
    if args.command == "abstract":
        from cli import abstract
        abstract.run(limit=args.limit, sample=args.sample, mode=args.mode)
    elif args.command == "blueprint":
        from cli import blueprint
        blueprint.run()
    elif args.command == "outline":
        from cli import outline
        outline.run(
            input_file=args.input,
            literature_file=args.literature,
            skeleton_id=args.skeleton_id,
            feedback=args.feedback,
            no_input=args.no_input,
            template_file=args.template,
        )
    elif args.command == "template":
        from cli import templates
        templates.run(new=args.new, show=args.list)
    elif args.command == "review":
        from cli import review
        review.run(input_file=args.input)
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
