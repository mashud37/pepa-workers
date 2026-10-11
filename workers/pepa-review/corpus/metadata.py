"""Derive the work list from base filenames, the source for every selection menu.
"""
from pathlib import Path

from corpus.load import load_corpus


def work_list():
    """Return [{base, authors, title, sum_path, para_path, quote_path}, ...] sorted by authors."""
    works = []
    for entry in load_corpus():
        base = entry["base"]
        authors = base.split("_")[0].strip() if "_" in base else base
        title = base.split("_", 1)[1].strip() if "_" in base else base
        works.append({
            "base": base,
            "authors": authors,
            "title": title,
            "sum_path": entry["sum_path"],
            "para_path": entry["para_path"],
            "quote_path": entry["quote_path"],
        })
    return sorted(works, key=lambda w: w["authors"].lower())


def display_label(work):
    title = work["title"]
    if len(title) > 60:
        title = title[:57] + "..."
    return f"{work['authors']}: {title}"


def list_bases(list_file):
    """The paper names in a literature list file: one per line, blank lines and # comments skipped."""
    path = Path(list_file)
    if not path.exists():
        raise SystemExit(f"File not found: {list_file}")
    bases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if name and not name.startswith("#"):
            bases.append(name)
    if not bases:
        raise SystemExit(f"No papers named in {list_file}")
    return bases
