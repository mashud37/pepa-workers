#!/usr/bin/env python3
"""Build the pepa-workers package from the apps in workers/. No arguments opens the menu."""
import argparse
import sys
from functools import partial

from cli import bundle_cmd, check_cmd, docs_cmd, install, smoke_cmd, ui

_ACTIONS = [
    {
        "label": "Development wheel",
        "hint": "every app at HEAD, version marked as a development one",
        "run": partial(bundle_cmd.run, dev=True),
    },
    {
        "label": "Release wheel",
        "hint": "only the apps workers.yaml marks as released",
        "run": bundle_cmd.run,
    },
    {
        "label": "Release gate",
        "hint": "what still blocks each app from being released",
        "run": check_cmd.run,
    },
    {
        "label": "Smoke test",
        "hint": "install the newest wheel in a fresh environment and run every command",
        "run": smoke_cmd.run,
    },
    {
        "label": "Documentation pages",
        "hint": "copy the guides and write each app's commands page into docs/",
        "run": docs_cmd.run,
    },
    {
        "label": "Check dependencies and apps",
        "hint": "what this repository needs and which apps it finds in workers/",
        "run": install.run,
    },
]


def _menu():
    while True:
        options = [(action["label"], action["hint"]) for action in _ACTIONS]
        chosen = ui.menu("pepa-workers", options)
        if chosen is None:
            return 0
        ui.run_action(_ACTIONS[chosen]["run"])


def _parser():
    parser = argparse.ArgumentParser(prog="manage.py", description="Build the pepa-workers package")
    sub = parser.add_subparsers(dest="command")
    bundle = sub.add_parser("bundle", help="Build the wheel from the apps workers.yaml releases")
    bundle.add_argument("--dev", action="store_true", help="include every app as it is in the working tree and mark the version")
    sub.add_parser("check", help="Hold every app against the release gate")
    sub.add_parser("test", help="Install the newest wheel in a fresh environment and run each command")
    sub.add_parser("docs", help="Copy the guides and write each app's commands page into docs/")
    sub.add_parser("install", help="Check dependencies and the apps in workers/")
    return parser


def main():
    args = _parser().parse_args()
    if args.command is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            return _menu()
        print("no TTY, run: python manage.py --help", file=sys.stderr)
        return 0
    if args.command == "bundle":
        return bundle_cmd.run(dev=args.dev)
    if args.command == "check":
        return check_cmd.run()
    if args.command == "test":
        return smoke_cmd.run()
    if args.command == "docs":
        return docs_cmd.run()
    return install.run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(0)
    except SystemExit as error:
        if isinstance(error.code, str):
            ui.error(error.code)
            sys.exit(1)
        raise
