#!/usr/bin/env python3
"""Orchestrate the pepa-* child apps from one place. No arguments opens the web console;
subcommands are the scriptable twin of what the console does.
"""
import argparse
import sys
from pathlib import Path

from cli import ui
from registry import APPS, KIND_SYMBOL, get_command

INSTALLED = Path(__file__).resolve().parent.parent.name == "apps"
COMMAND = "pepa-console" if INSTALLED else "python manage.py"


def cmd_status() -> int:
    for app in APPS:
        print(f"{app.name}  :  {app.blurb}")
        for c in app.commands:
            mark = KIND_SYMBOL[c.kind]
            flags = " ".join(c.default_flags)
            tail = f"  ({flags})" if flags else ""
            print(f"  {mark} {c.name:<14} {c.kind:<11} {c.help}{tail}")
        print()
    return 0


def cmd_config() -> int:
    from registry import ROOT
    interactive = 0
    for app in APPS:
        for command in app.commands:
            if command.kind in ("interactive", "terminal"):
                interactive += 1
    print(f"root         {ROOT}")
    print(f"apps         {len(APPS)}")
    print(f"commands     {sum(len(a.commands) for a in APPS)}")
    print(f"interactive  {interactive} (run in a terminal)")
    return 0


def cmd_install() -> int:
    ui.step("Checking pepa-console")
    missing = []
    for module in ("flask",):
        try:
            __import__(module)
            ui.ok(f"{module} is installed")
        except ImportError:
            missing.append(module)
    if missing:
        ui.error(f"{', '.join(missing)} missing, run: pip install -r requirements.txt")
        return 1
    for a in APPS:
        found = a.path.exists()
        (ui.ok if found else ui.warn)(f"{a.name} {'found' if found else 'not found'}")
    return 0


def cmd_tui() -> int:
    try:
        import textual  # noqa: F401
    except ImportError:
        raise SystemExit("The terminal console needs Textual: pip install textual") from None
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise SystemExit("The terminal console needs a terminal.")
    from console.app import run
    run()
    return 0


def cmd_run(app: str, command: str, extra: list[str]) -> int:
    if get_command(app, command) is None:
        raise SystemExit(f"unknown command: {app} {command}, see: {COMMAND} status")
    from runner import run_blocking
    return run_blocking(app, command, extra)


def main() -> int:
    parser = argparse.ArgumentParser(prog=COMMAND, description="Orchestrate the pepa-* child apps.")
    sub = parser.add_subparsers(dest="command")

    r = sub.add_parser("run", help="Run a child command headlessly and stream its output")
    r.add_argument("app", help="Child app, e.g. pepa-sum")
    r.add_argument("cmd", help="Subcommand, e.g. config")
    r.add_argument("extra", nargs=argparse.REMAINDER, help="Extra flags passed to the child")

    w = sub.add_parser("web", help="Open the web console in the browser (the default)")
    w.add_argument("--port", type=int, default=None, metavar="N", help="Port (default: 5190)")
    w.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")

    sub.add_parser("tui", help="Open the older terminal console (needs: pip install textual)")
    sub.add_parser("status", help="List apps and their commands")
    sub.add_parser("config", help="Show effective configuration")
    sub.add_parser("install", help="Check dependencies and discover apps")

    args = parser.parse_args()

    if args.command is None:
        from web.app import run as run_web
        run_web(None, open_browser=True)
        return 0
    if args.command == "web":
        from web.app import run as run_web
        run_web(args.port, open_browser=not args.no_browser)
        return 0
    if args.command == "tui":
        return cmd_tui()
    if args.command == "status":
        return cmd_status()
    if args.command == "config":
        return cmd_config()
    if args.command == "install":
        return cmd_install()
    if args.command == "run":
        return cmd_run(args.app, args.cmd, args.extra)
    return 0


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
