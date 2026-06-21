#!/usr/bin/env python3
import argparse
import sys

from cli import install, menu, ui


def _handle_draft(args):
    from cli import draft_cmd
    skip = set()
    if args.no_retrieval:
        skip.add("retrieval")
    if args.no_style:
        skip.add("style")
    draft_cmd.run(review_file=args.review, plan_file=args.plan,
                  sections_file=args.sections, backend=args.backend, skip=skip,
                  style_profile=args.style_profile)


def _handle_sections(args):
    from cli import sections_cmd
    sections_cmd.run(plan_file=args.plan, reset=args.reset)


def _handle_style(args):
    from cli import style_cmd
    style_cmd.run(action=args.action, file_path=args.file, profile=args.profile)


def _handle_config(_args):
    from cli import config_cmd
    config_cmd.run()


def _handle_setup(_args):
    from cli import setup_cmd
    setup_cmd.run()


_HANDLERS = {
    "draft": _handle_draft,
    "sections": _handle_sections,
    "style": _handle_style,
    "config": _handle_config,
    "setup": _handle_setup,
    "install": lambda _: install.run(),
}


def main():
    parser = argparse.ArgumentParser(prog="manage.py", description="pepa-draft — academic manuscript drafting")
    sub = parser.add_subparsers(dest="command")

    dr = sub.add_parser("draft", help="Write a full manuscript draft")
    dr.add_argument("--review", default=None, metavar="FILE")
    dr.add_argument("--plan", default=None, metavar="FILE")
    dr.add_argument("--sections", default=None, metavar="FILE")
    dr.add_argument("--backend", default=None, choices=("anthropic", "vllm"))
    dr.add_argument("--no-retrieval", action="store_true")
    dr.add_argument("--no-style", action="store_true")
    dr.add_argument("--style-profile", default=None, metavar="PROFILE")

    sc = sub.add_parser("sections", help="Assign plan paragraphs to manuscript sections")
    sc.add_argument("--plan", default=None, metavar="FILE")
    sc.add_argument("--reset", action="store_true")

    st = sub.add_parser("style", help="Manage author writing samples for style matching")
    st.add_argument("action", nargs="?", choices=("add", "list", "remove", "build", "switch", "list-profiles"))
    st.add_argument("--file", default=None, metavar="FILE")
    st.add_argument("--profile", default=None, metavar="PROFILE")

    sub.add_parser("config", help="Show effective configuration")
    sub.add_parser("setup", help="Configure API keys and paths interactively")
    sub.add_parser("install", help="Set up files and check dependencies")

    args = parser.parse_args()
    if args.command is None:
        return menu.main()
    handler = _HANDLERS.get(args.command)
    if handler:
        handler(args)


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
