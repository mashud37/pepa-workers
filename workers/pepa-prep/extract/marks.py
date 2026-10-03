"""Read the chapter starts a user marked in a book and record the starts found by detection, as PDF pages from 1.
The web console shows both.
"""
import json
import os

from .config import DATA_ROOT

MARKS_DIR = DATA_ROOT / "data" / "marks"
FOUND_DIR = DATA_ROOT / "data" / "found"
EXCLUDE_VARIABLE = "PEPA_EXCLUDE_FILE"


def marked_starts(stem):
    """The PDF pages the user marked as chapter starts, sorted, or an empty list when there are none."""
    path = MARKS_DIR / f"{stem}.json"
    if not path.exists():
        return []
    return sorted(set(json.loads(path.read_text(encoding="utf-8"))["starts"]))


def save_found(stem, starts, strategy):
    """Record where chapters start in a book, so the console can show them before the user marks any."""
    FOUND_DIR.mkdir(parents=True, exist_ok=True)
    record = {"starts": starts, "strategy": strategy}
    (FOUND_DIR / f"{stem}.json").write_text(json.dumps(record), encoding="utf-8")


def excluded_names():
    """The PDF file names the user set aside, read from the list the console names in PEPA_EXCLUDE_FILE."""
    listed = os.environ.get(EXCLUDE_VARIABLE, "")
    if not listed or not os.path.exists(listed):
        return set()
    with open(listed, encoding="utf-8") as handle:
        return set(json.load(handle))
