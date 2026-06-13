"""Work-list derived from base filenames — the source for all selection menus."""
from corpus.load import load_corpus


def _authors(base):
    return base.split("_")[0].strip() if "_" in base else base


def _title(base):
    return base.split("_", 1)[1].strip() if "_" in base else base


def work_list():
    """Return [{base, authors, title, sum_path, para_path, quote_path}, ...] sorted by authors."""
    works = []
    for entry in load_corpus():
        base = entry["base"]
        works.append({
            "base": base,
            "authors": _authors(base),
            "title": _title(base),
            "sum_path": entry["sum_path"],
            "para_path": entry["para_path"],
            "quote_path": entry["quote_path"],
        })
    return sorted(works, key=lambda w: w["authors"].lower())


def display_label(work):
    title = work["title"]
    if len(title) > 60:
        title = title[:57] + "..."
    return f"{work['authors']} — {title}"
