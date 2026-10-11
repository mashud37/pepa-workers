"""Read the field maps pepa-review writes as theme cards and theme pages.
The Map tab under Explore shows them and starts new maps.
"""
from pathlib import Path

from web import connections, paths

MAP_KINDS = [
    {"prefix": "corpus_map_", "label": "Everything"},
    {"prefix": "list_map_", "label": "A list"},
    {"prefix": "thread_map_", "label": "A theme in detail"},
]
GIST_LENGTH = 260
# pepa-review maps a theme in detail only from this many papers (its MAP_SMALLEST).
DETAIL_SMALLEST = 6


def results_folder():
    """Where pepa-review writes its maps, reviews and conversations."""
    return paths.chosen("pepa-review", "results")


def kind_of(file_name):
    """What a map covers, from its file name, or None for a file that is no map."""
    for kind in MAP_KINDS:
        if file_name.startswith(kind["prefix"]) and file_name.endswith(".json"):
            return kind
    return None


def all_maps():
    """Every map pepa-review has written, newest first, with what it covers and how many themes it found."""
    folder = results_folder()
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*_map_*.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        kind = kind_of(path.name)
        if kind is None:
            continue
        field_map = connections.load_json(path)
        found.append({
            "file": path.name,
            "title": field_map["title"],
            "kind": kind["label"],
            "generated": field_map["generated"],
            "themes": len(field_map["threads"]),
            "papers": field_map["total_works"],
        })
    return found


def load_map(name):
    """One map by its file name, with "file" added, or None when there is no such map."""
    path = results_folder() / Path(name).name
    if kind_of(path.name) is None or not path.is_file():
        return None
    field_map = dict(connections.load_json(path))
    field_map["file"] = path.name
    return field_map


def gist(text):
    """The start of a theme's discussion, cut at a word near GIST_LENGTH characters."""
    if len(text) <= GIST_LENGTH:
        return text
    return text[:GIST_LENGTH].rsplit(" ", 1)[0] + "…"


def theme_cards(field_map):
    """Each theme of a map as a card: its name, the start of its discussion, and its paper counts."""
    cards = []
    for thread in field_map["threads"]:
        cards.append({
            "id": thread["id"],
            "name": thread["name"],
            "gist": gist(thread.get("discussion", "")),
            "papers": len(thread["bases"]),
            "shared": len(thread["also_bases"]),
        })
    return cards


def named_papers(bases):
    """Paper names as title and authors, sorted by authors."""
    papers = [connections.named(base) for base in bases]
    return sorted(papers, key=lambda paper: paper["authors"].lower())


def neighbours(field_map, thread):
    """The other themes this one shares papers with, most shared first."""
    own = set(thread["bases"] + thread["also_bases"])
    found = []
    for other in field_map["threads"]:
        if other["id"] == thread["id"]:
            continue
        shared = len(own & set(other["bases"] + other["also_bases"]))
        if shared:
            found.append({"id": other["id"], "name": other["name"], "shared": shared})
    return sorted(found, key=lambda other: -other["shared"])


def detail_maps(field_map, thread):
    """The maps that mapped this theme in detail, newest first."""
    wanted_title = "Thread map: " + thread["name"]
    found = []
    for each in all_maps():
        if each["title"] != wanted_title:
            continue
        detail = load_map(each["file"])
        if detail.get("source") == field_map["map_file"]:
            found.append(each)
    return found


def theme_view(field_map, theme_id):
    """Everything a theme page shows, or None when the map has no theme with this number."""
    for thread in field_map["threads"]:
        if thread["id"] != theme_id:
            continue
        return {
            "id": thread["id"],
            "name": thread["name"],
            "discussion": thread.get("discussion", ""),
            "arguments": thread.get("arguments", []),
            "concepts": thread.get("concepts", []),
            "methods": thread.get("methods", ""),
            "empirical": thread.get("empirical", ""),
            "papers": named_papers(thread["bases"]),
            "shared": named_papers(thread["also_bases"]),
            "neighbours": neighbours(field_map, thread),
            "detail_maps": detail_maps(field_map, thread),
            "can_detail": len(thread["bases"]) + len(thread["also_bases"]) >= DETAIL_SMALLEST,
            "detail_smallest": DETAIL_SMALLEST,
        }
    return None


def parent_map(field_map):
    """The map a detail map was drawn from, as its JSON file name, or "" for a map of its own."""
    source = field_map.get("source") or ""
    if not source:
        return ""
    return Path(source).with_suffix(".json").name


def newest_corpus_map():
    """The file name of the newest map of everything, or "" when there is none yet."""
    for each in all_maps():
        if each["kind"] == MAP_KINDS[0]["label"]:
            return each["file"]
    return ""
