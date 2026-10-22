#!/usr/bin/env python3
import argparse
import io
import sys

import config
from cli import install, menu, ui


def _handle_draft(args):
    from cli import draft_cmd
    skip = set()
    if args.no_retrieval:
        skip.add("retrieval")
    if args.no_style:
        skip.add("style")
    draft_cmd.run({
        "review_file": args.review,
        "plan_file": args.plan,
        "sections_file": args.sections,
        "backend": args.backend,
        "skip": skip,
        "style_profile": args.style_profile,
        "accept_sections": args.accept_sections,
        "only_estimate": args.estimate,
        "output_name": args.output,
    })


def _handle_sections(args):
    from cli import sections_cmd
    sections_cmd.run(plan_file=args.plan, reset=args.reset)


def _handle_style(args):
    from cli import style_cmd
    style_cmd.run(action=args.action, file_path=args.file, profile=args.profile)


def _handle_config(args):
    from cli import config_cmd
    config_cmd.run(as_json=args.json)


def _handle_setup(args):
    from cli import setup_cmd
    setup_cmd.run({
        "llm_base_url": args.llm_base_url,
        "llm_model": args.llm_model,
        "ollama_base_url": args.ollama_base_url,
        "review_index": args.review_index,
    })


_HANDLERS = {
    "draft": _handle_draft,
    "sections": _handle_sections,
    "style": _handle_style,
    "config": _handle_config,
    "setup": _handle_setup,
    "install": lambda _: install.run(),
}


def main():
    parser = argparse.ArgumentParser(prog=config.COMMAND, description="pepa-draft: academic manuscript drafting")
    parser.add_argument("--no-input", action="store_true", help="Never ask a question: each one takes its default answer")
    sub = parser.add_subparsers(dest="command")

    dr = sub.add_parser("draft", help="Write a full manuscript draft")
    dr.add_argument("--review", default=None, metavar="FILE")
    dr.add_argument("--plan", default=None, metavar="FILE")
    dr.add_argument("--sections", default=None, metavar="FILE")
    dr.add_argument("--backend", default=None, choices=("anthropic", "openai-compatible"))
    dr.add_argument("--no-retrieval", action="store_true")
    dr.add_argument("--no-style", action="store_true")
    dr.add_argument("--style-profile", default=None, metavar="PROFILE")
    dr.add_argument("--accept-sections", action="store_true", help="Draft with the outline's sections as its move labels place them, without asking")
    dr.add_argument("-o", "--output", default=None, metavar="NAME", help="File name for the draft in output/ (default: from the time)")
    dr.add_argument("--estimate", action="store_true", help="Print the most the draft can cost as JSON, and stop")

    sc = sub.add_parser("sections", help="Assign plan paragraphs to manuscript sections")
    sc.add_argument("--plan", default=None, metavar="FILE")
    sc.add_argument("--reset", action="store_true")

    st = sub.add_parser("style", help="Manage author writing samples for style matching")
    st.add_argument("action", nargs="?", choices=("add", "list", "remove", "build", "switch", "list-profiles"))
    st.add_argument("--file", default=None, metavar="FILE")
    st.add_argument("--profile", default=None, metavar="PROFILE")

    cf = sub.add_parser("config", help="Show effective configuration")
    cf.add_argument("--json", action="store_true", help="Print the settings as one JSON line")

    su = sub.add_parser("setup", help="Configure API keys and paths; any flag saves without asking (keys only interactively or from the environment)")
    su.add_argument("--llm-base-url", default=None, metavar="URL", help="OpenAI-compatible server address")
    su.add_argument("--llm-model", default=None, metavar="NAME", help="OpenAI-compatible model name")
    su.add_argument("--ollama-base-url", default=None, metavar="URL", help="Ollama base URL for embeddings")
    su.add_argument("--review-index", default=None, metavar="FILE", help="Path to pepa-review index.json")
    sub.add_parser("install", help="Set up files and check dependencies")

    args = parser.parse_args()
    if args.no_input:
        sys.stdin = io.StringIO()
    if args.command is None:
        return menu.main()
    handler = _HANDLERS.get(args.command)
    if handler:
        return handler(args)


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
