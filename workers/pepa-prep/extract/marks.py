"""Read the chapter starts and left-out pages a user marked in a PDF, and record the starts detection found, as pages from 1.
The web console shows both.
"""
import json
import os

from .config import DATA_ROOT

MARKS_DIR = DATA_ROOT / "data" / "marks"
FOUND_DIR = DATA_ROOT / "data" / "found"
EXCLUDE_VARIABLE = "PEPA_EXCLUDE_FILE"
ONLY_VARIABLE = "PEPA_ONLY_FILE"


def marked_starts(stem):
    """The PDF pages the user marked as chapter starts, sorted, or an empty list when there are none."""
    path = MARKS_DIR / f"{stem}.json"
    if not path.exists():
        return []
    return sorted(set(json.loads(path.read_text(encoding="utf-8")).get("starts", [])))


def left_out_pages(stem):
    """The PDF pages the user left out, counted from 1, or an empty set when there are none."""
    path = MARKS_DIR / f"{stem}.json"
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("skip", []))


def blank_left_out(stem, pages, empty):
    """The pages with each left-out one replaced by an empty page, so every later page keeps its number."""
    left_out = left_out_pages(stem)
    blanked = []
    for number, page in enumerate(pages, start=1):
        blanked.append(empty if number in left_out else page)
    return blanked


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


def only_names():
    """The only PDF file names to prepare, read from the list the console names in PEPA_ONLY_FILE, or None for all."""
    listed = os.environ.get(ONLY_VARIABLE, "")
    if not listed or not os.path.exists(listed):
        return None
    with open(listed, encoding="utf-8") as handle:
        return set(json.load(handle))
