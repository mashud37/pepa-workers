#!/usr/bin/env python3
"""pepa-sum — summarise academic PDFs into structured, comparable Markdown.

No arguments launches the interactive menu; any subcommand runs directly.
"""
import sys
import argparse
from pathlib import Path

from cli import menu, summarize, install, show_config, deploy, ui


def main():
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Summarise PDFs in input/ into structured Markdown in output/.",
    )
    sub = parser.add_subparsers(dest="command")

    s = sub.add_parser("summarize", help="Summarise every PDF in the input folder")
    s.add_argument("-i", "--input", type=Path, help="Input folder of PDFs")
    s.add_argument("-o", "--output", type=Path, help="Output folder for summaries")
    s.add_argument("-f", "--force", action="store_true", help="Redo papers already summarised")

    sub.add_parser("config", help="Print effective config and cost note")
    sub.add_parser("deploy", help="Build and deploy the Cloud Run summariser service")
    sub.add_parser("install", help="Create env.yaml, generate token, check dependencies")

    args = parser.parse_args()
    if args.command is None:
        return menu.main()
    if args.command == "summarize":
        return summarize.run(input_dir=args.input, output_dir=args.output, force=args.force)
    if args.command == "config":
        return show_config.run()
    if args.command == "deploy":
        return deploy.run()
    if args.command == "install":
        return install.run()


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
