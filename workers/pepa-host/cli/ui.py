"""Terminal UI helpers: header rule, step markers, status lines, and prompts.
Colour and unicode degrade when stdout is not a TTY or NO_COLOR is set.
"""
import os
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"

WIDTH = 64


def _supports_color():
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        # Enable ANSI (Virtual Terminal) processing on the Windows console.
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            return False
    return True


# Try to render unicode symbols even on legacy Windows code pages.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_COLOR = _supports_color()
_UNICODE = True
try:
    "▶✓⚠✗·".encode(sys.stdout.encoding or "utf-8")
except Exception:
    _UNICODE = False

_SYM = {
    "step": "▶" if _UNICODE else ">",
    "ok": "✓" if _UNICODE else "+",
    "warn": "⚠" if _UNICODE else "!",
    "err": "✗" if _UNICODE else "x",
    "info": "·" if _UNICODE else "-",
    "rule": "─" if _UNICODE else "-",
}


def _c(code, text):
    return f"{code}{text}{RESET}" if _COLOR else text


def header(text):
    rule = _SYM["rule"] * WIDTH
    print()
    print(_c(BLUE, rule))
    print(_c(BOLD + BLUE, f"  {text}"))
    print(_c(BLUE, rule))


def rule():
    print(_c(DIM, _SYM["rule"] * WIDTH))


def step(text):
    print()
    print(_c(BOLD + BLUE, f"{_SYM['step']} {text}"))


def ok(text):
    print(f"  {_c(GREEN, _SYM['ok'])} {text}")


def warn(text):
    print(f"  {_c(YELLOW, _SYM['warn'])} {text}")


def info(text):
    print(f"  {_c(DIM, _SYM['info'])} {text}")


def error(text):
    print(f"  {_c(RED, _SYM['err'])} {text}")


def abort(text, code=1):
    error(text)
    sys.exit(code)


def table(rows, columns):
    """Print a list of dictionaries as an aligned table, one row per unit of work.

    Args:
        rows: Dictionaries sharing the same keys, one per item processed.
        columns: Keys to show, in the order they should appear.
    """
    widths = [len(name) for name in columns]
    for row in rows:
        for position, name in enumerate(columns):
            widths[position] = max(widths[position], len(str(row.get(name, ""))))

    heading = "  ".join(name.ljust(widths[position]) for position, name in enumerate(columns))
    print(f"  {_c(BOLD, heading)}")
    for row in rows:
        cells = []
        for position, name in enumerate(columns):
            cells.append(str(row.get(name, "")).ljust(widths[position]))
        print("  " + "  ".join(cells))


def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    try:
        raw = input(_c(BOLD, f"  {prompt}{suffix}: ")).lstrip("﻿").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return raw or default


def ask_choice(prompt, choices, default=None):
    low = [c.lower() for c in choices]
    while True:
        raw = ask(prompt, default)
        if raw is None:
            return default
        r = raw.strip().lower()
        if r in low:
            return choices[low.index(r)]
        warn(f"choose one of: {', '.join(choices)}")


def confirm(question, default_yes=True):
    hint = "Y/n" if default_yes else "y/N"
    raw = ask(f"{question} [{hint}]")
    if not raw:
        return default_yes
    return raw.strip().lower() in ("y", "yes")


def menu(title, options):
    """Print a numbered menu and return a 0-based index, or None to close it.

    None means the user chose [0], typed q/quit/exit, submitted an empty line, or
    pressed Ctrl-C; every caller treats it as "close this menu level".

    Args:
        title: Heading printed above the entries.
        options: (label, description) tuples or plain strings.

    Returns:
        0-based index of the chosen option, or None to close the menu.
    """
    print()
    rule()
    print(_c(BOLD, f"  {title}"))
    width = max((len(o[0]) if isinstance(o, tuple) else len(o)) for o in options)
    for i, o in enumerate(options, 1):
        if isinstance(o, tuple):
            label, desc = o
            print(f"  {_c(BLUE, f'[{i}]')} {label.ljust(width)}   {_c(DIM, desc)}")
        else:
            print(f"  {_c(BLUE, f'[{i}]')} {o}")
    print(f"  {_c(BLUE, '[0]')} Back")
    while True:
        raw = ask("Choose")
        if raw in (None, "0", "q", "quit", "exit"):
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        warn("invalid choice")


def run_action(action, *args, **kwargs):
    """Run a menu action so a failure returns to the menu instead of the shell.

    Args:
        action: Callable invoked with *args/**kwargs.

    Returns:
        Whatever `action` returns, or None if it failed or was interrupted.
    """
    try:
        return action(*args, **kwargs)
    except SystemExit as e:
        if isinstance(e.code, str):
            error(e.code)
    except KeyboardInterrupt:
        warn("interrupted")
    return None
