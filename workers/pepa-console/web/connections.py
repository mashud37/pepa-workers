"""Find what a paper connects to: the papers most like it, its theme on the field map, and its name in parts.
The paper, search and map pages show these.
"""
import json
from pathlib import Path

from web import paths

RELATED_FILE = Path("pepa-review") / "data" / "related.json"
MAP_PATTERN = "corpus_map_*.json"
SHOWN_RELATED = 8

# Files read again only when they change, keyed by path: {"stamp", "data"}.
LOADED = {}


def load_json(path):
    """A JSON file's content, read again only when the file has changed since the last read."""
    stamp = path.stat().st_mtime
    known = LOADED.get(str(path))
    if known is None or known["stamp"] != stamp:
        known = {"stamp": stamp, "data": json.loads(path.read_text(encoding="utf-8"))}
        LOADED[str(path)] = known
    return known["data"]


def named(stem):
    """A paper's author part and title part, from a file name like `Smith et al_A study of things`."""
    authors, _, title = stem.partition("_")
    if not title:
        return {"stem": stem, "authors": "", "title": stem}
    return {"stem": stem, "authors": authors, "title": title}


def related_papers(stem):
    """The papers most like this one, closest first, or None when the review index has not been built."""
    path = paths.project_folder() / RELATED_FILE
    if not path.exists():
        return None
    papers = []
    for other, score in load_json(path).get(stem, [])[:SHOWN_RELATED]:
        paper = named(other)
        paper["score"] = score
        papers.append(paper)
    return papers


def latest_map():
    """The newest field map pepa-review wrote, or None when there is none yet."""
    folder = paths.chosen("pepa-review", "results")
    maps = sorted(folder.glob(MAP_PATTERN)) if folder.is_dir() else []
    if not maps:
        return None
    return load_json(maps[-1])


def themes_of(stem):
    """The map's themes this paper belongs to: its own theme first, then those it is also close to."""
    field_map = latest_map()
    if field_map is None:
        return []
    found = []
    for thread in field_map["threads"]:
        if stem in thread["bases"]:
            found.insert(0, {"id": thread["id"], "name": thread["name"], "main": True})
        elif stem in thread["also_bases"]:
            found.append({"id": thread["id"], "name": thread["name"], "main": False})
    return found
