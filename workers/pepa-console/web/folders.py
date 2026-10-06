"""Read what sits in the folders each app uses: pipeline counts, recent files, and files copied in.
The pipeline and app pages show these.
"""
import os
import time
from datetime import datetime
from pathlib import Path

from web import paths

PDFS_WAITING = {"app": "pepa-prep", "slot": "sources", "inside": "", "prefix": "", "suffix": ".pdf"}
PREPARED = {"app": "pepa-prep", "slot": "results", "inside": "text", "prefix": "text_", "suffix": ".md"}
SUMMARISED = {"app": "pepa-sum", "slot": "results", "inside": "", "prefix": "sum_", "suffix": ".md"}
SEARCH_INDEX = {"app": "pepa-read", "path": "data/reader.db"}
REVIEW_INDEX = {"app": "pepa-review", "path": "data/index.json"}

IGNORED_NAMES = [
    ".gitkeep",
]

RECENT_LIMIT = 12
DAY_FORMAT = "%d %b"
TIME_FORMAT = "%d %b, %H:%M"

# A walk through sub-folders stops at whichever of these comes first, so a page
# never waits on a folder that turns out to be a whole network drive.
SCAN_LIMIT = 4000
SCAN_SECONDS = 2.0

# What counts as a paper in each folder that can be read with its sub-folders,
# so the number the page shows is the number the app will actually read.
PAPER_SUFFIXES = {
    "pepa-prep/sources": [".pdf"],
    "pepa-sum/sources": [".pdf", ".md", ".markdown", ".txt"],
}


# ---- Pipeline ----

def names_here(folder):
    """The names of the files sitting directly in a folder."""
    names = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.is_file() and entry.name not in IGNORED_NAMES:
                names.append(entry.name)
    return names


def files_below(folder):
    """Every file in a folder and its sub-folders, by the path that reaches it.

    Returns:
        dict with "names", each relative to the folder, and "capped", true when
        the walk stopped at SCAN_LIMIT files or SCAN_SECONDS rather than the end.
    """
    names = []
    capped = False
    deadline = time.monotonic() + SCAN_SECONDS
    for current, folders_inside, found in os.walk(folder):
        for name in found:
            if name not in IGNORED_NAMES:
                names.append(str(Path(current, name).relative_to(folder)))
        if len(names) >= SCAN_LIMIT or time.monotonic() > deadline:
            capped = True
            break
    return {"names": names, "capped": capped}


def leaf_name(name):
    """The file name at the end of a relative path; plain string work, as the library can hold many thousands."""
    return name.replace("\\", "/").rpartition("/")[2]


def matching_names(stage):
    """Names of the files in a stage's folder that carry the stage's prefix and suffix.

    Returns:
        dict with "names" and "capped", true when a sub-folder walk stopped early.
    """
    folder = paths.chosen(stage["app"], stage["slot"])
    if stage["inside"]:
        folder = folder / stage["inside"]
    if not folder.is_dir():
        return {"names": [], "capped": False}
    if paths.scans_subfolders(stage["app"], stage["slot"]):
        found = files_below(folder)
    else:
        found = {"names": names_here(folder), "capped": False}
    wanted = []
    for name in found["names"]:
        leaf = leaf_name(name)
        if leaf.startswith(stage["prefix"]) and leaf.endswith(stage["suffix"]):
            wanted.append(name)
    return {"names": wanted, "capped": found["capped"]}


def index_built(index):
    """The day an index file was last written, or an empty string when it does not exist."""
    path = paths.project_folder() / index["app"] / index["path"]
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime).strftime(DAY_FORMAT)


def papers_covered(stage):
    """The paper names a stage wrote files for, counting a book's chapter files once.

    A name ending in an underscore and digits may be a chapter of a longer name, so both are kept.
    """
    covered = set()
    for name in matching_names(stage)["names"]:
        core = leaf_name(name)[len(stage["prefix"]):-len(stage["suffix"])]
        covered.add(core)
        head, _, tail = core.rpartition("_")
        if head and tail.isdigit():
            covered.add(head)
    return covered


def pipeline_summary():
    """What the pipeline holds now: waiting PDFs, how many are prepared and summarised, and both indexes."""
    waiting = matching_names(PDFS_WAITING)
    removed = [name for name in paths.load_removed() if name not in waiting["names"]]
    stems = [Path(name).stem for name in waiting["names"] + removed]
    prepared = papers_covered(PREPARED)
    summarised = papers_covered(SUMMARISED)
    return {
        "pdfs": len(waiting["names"]) + len(removed),
        "pdfs_capped": waiting["capped"],
        "prepared": sum(1 for stem in stems if stem in prepared),
        "summarised": sum(1 for stem in stems if stem in summarised),
        "search_index": index_built(SEARCH_INDEX),
        "review_index": index_built(REVIEW_INDEX),
    }


def remarked_stems():
    """The PDFs whose chapter marks were saved after their text was prepared, which pepa-prep prepares again."""
    marks_dir = paths.project_folder() / "pepa-prep" / "data" / "marks"
    if not marks_dir.is_dir():
        return set()
    text_dir = paths.chosen(PREPARED["app"], PREPARED["slot"]) / PREPARED["inside"]
    prepared = matching_names(PREPARED)["names"]
    stems = set()
    for marks in marks_dir.glob("*.json"):
        prefix = f"text_{marks.stem}_"
        newest = 0.0
        for name in prepared:
            leaf = leaf_name(name)
            chapter = leaf.startswith(prefix) and leaf[len(prefix):-len(".md")].isdigit()
            if leaf == f"text_{marks.stem}.md" or chapter:
                newest = max(newest, (text_dir / name).stat().st_mtime)
        if newest and marks.stat().st_mtime > newest:
            stems.add(marks.stem)
    return stems


def unprepared_count(only=None):
    """How many waiting PDFs a run would prepare and then summarise: not prepared yet or marked again since,
    skipped by neither stage, and among the only names given, when there are any."""
    waiting = matching_names(PDFS_WAITING)["names"]
    if only:
        waiting = [name for name in waiting if Path(name).name in only]
    prepared = papers_covered(PREPARED)
    remarked = remarked_stems()
    excluded = paths.load_excluded()
    skipped = set(excluded["pepa-prep"]) | set(excluded["pepa-sum"])
    count = 0
    for name in waiting:
        to_prepare = Path(name).stem not in prepared or Path(name).stem in remarked
        if to_prepare and Path(name).name not in skipped:
            count += 1
    return count


# ---- App folders ----

def one_row(name, modified, is_folder):
    """One line of a folder card: what it is called, whether it is a folder, when it changed."""
    return {
        "name": name,
        "is_folder": is_folder,
        "modified": modified,
        "when": datetime.fromtimestamp(modified).strftime(TIME_FORMAT),
    }


def entry_rows(folder):
    """A line for every file and folder sitting directly in one folder."""
    rows = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.name not in IGNORED_NAMES:
                rows.append(one_row(entry.name, entry.stat().st_mtime, entry.is_dir()))
    return rows


def deep_rows(folder, names):
    """A line for every file found below one folder, named by the path that reaches it."""
    rows = []
    for name in names:
        rows.append(one_row(name, (folder / name).stat().st_mtime, False))
    return rows


def recent_files(folder, deep):
    """The newest entries of one folder, and how many entries it holds in total."""
    if not folder.is_dir():
        return {"total": 0, "rows": [], "capped": False}
    capped = False
    if deep:
        found = files_below(folder)
        rows = deep_rows(folder, found["names"])
        capped = found["capped"]
    else:
        rows = entry_rows(folder)
    rows.sort(key=lambda row: row["modified"], reverse=True)
    return {"total": len(rows), "rows": rows[:RECENT_LIMIT], "capped": capped}


def app_folders(app_name):
    """Every folder this app uses, each with its newest files, as the app page's cards."""
    cards = []
    for place in paths.places_of(app_name):
        folder = paths.chosen(app_name, place["slot"])
        deep = paths.scans_subfolders(app_name, place["slot"])
        listing = recent_files(folder, deep)
        cards.append({
            "slot": place["slot"],
            "label": place["label"],
            "role": place["role"],
            "path": str(folder),
            "exists": folder.is_dir(),
            "takes_copies": paths.owned_by_app(place, folder),
            "deep": deep,
            "total": listing["total"],
            "capped": listing["capped"],
            "rows": listing["rows"],
        })
    return cards


# ---- The Folders page ----

def paper_counts(app_name, slot):
    """How many papers sit directly in a folder, and how many more sit in its sub-folders."""
    folder = paths.chosen(app_name, slot)
    if folder is None or not folder.is_dir():
        return {"here": 0, "deeper": 0, "capped": False}
    suffixes = PAPER_SUFFIXES.get(f"{app_name}/{slot}", [".pdf"])
    found = files_below(folder)
    here = 0
    deeper = 0
    for name in found["names"]:
        if Path(name).suffix.lower() not in suffixes:
            continue
        if len(Path(name).parts) == 1:
            here += 1
        else:
            deeper += 1
    return {"here": here, "deeper": deeper, "capped": found["capped"]}


def counted(number, capped):
    """A count as the pages show it, with a plus when the walk stopped before the end."""
    if capped:
        return f"{number:,}+"
    return f"{number:,}"


def folder_pages():
    """Every app's folders as the Folders page shows them, with the count that makes
    a nested library visible."""
    apps = paths.page_rows()
    for app in apps:
        for row in app["rows"]:
            row["deeper"] = 0
            row["capped"] = False
            if row["can_scan"]:
                count = paper_counts(app["name"], row["slot"])
                row["deeper"] = count["deeper"]
                row["capped"] = count["capped"]
    return apps


def path_choices(cards):
    """Paths suggested in file and folder fields: each folder the app uses, then its newest files."""
    choices = []
    for card in cards:
        choices.append(card["path"])
        for row in card["rows"]:
            choices.append(str(Path(card["path"]) / row["name"]))
    return choices


def picked_files(uploads):
    """The files the browser sent, as name and bytes pairs, so one copy can reach two folders."""
    files = []
    for upload in uploads:
        files.append({
            "name": Path(upload.filename or "").name,
            "data": upload.read(),
        })
    return files


def copy_into(app_name, slot, files, required_suffix):
    """Copy files into one app folder, never replacing a file already there.

    Args:
        required_suffix: only names ending in this are copied; empty accepts any name.

    Raises:
        ValueError: that folder is the user's own, so the console does not write into it.
    """
    place = paths.find_place(app_name, slot)
    folder = paths.chosen(app_name, slot)
    if place is None or not paths.owned_by_app(place, folder):
        raise ValueError(f"{app_name} reads that folder from elsewhere, so nothing was copied into it.")
    folder.mkdir(parents=True, exist_ok=True)
    copied = []
    left_out = []
    for file in files:
        target = folder / file["name"]
        wrong_type = not file["name"].lower().endswith(required_suffix)
        if not file["name"] or file["name"].startswith(".") or wrong_type or target.exists():
            left_out.append(file["name"] or "(unnamed)")
            continue
        target.write_bytes(file["data"])
        copied.append(file["name"])
    return {"copied": sorted(set(copied)), "left_out": sorted(set(left_out)), "folder": str(folder)}


def write_new_file(app_name, slot, name, text):
    """Save typed text as a new file in one of the app's own folders, never replacing a file already there.

    Returns:
        the file's name as saved.

    Raises:
        ValueError: the folder is the user's own, the name is not usable, or the file exists already.
    """
    place = paths.find_place(app_name, slot)
    folder = paths.chosen(app_name, slot)
    if place is None or not paths.owned_by_app(place, folder):
        raise ValueError(f"{app_name} reads that folder from elsewhere, so nothing was written into it.")
    name = name.strip()
    if not name or Path(name).name != name or name.startswith("."):
        raise ValueError("Give a plain file name, without folders.")
    if not Path(name).suffix:
        name += ".md"
    target = folder / name
    if target.exists():
        raise ValueError(f"{name} is there already. Choose another name.")
    folder.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return name


def resolve_folder(app_name, slot, inside):
    """The sub-folder a browse link points at, or None when it is missing or outside the app's folder."""
    folder = paths.chosen(app_name, slot)
    if folder is None:
        return None
    allowed = folder.resolve()
    target = (allowed / inside).resolve()
    if not target.is_relative_to(allowed) or not target.is_dir():
        return None
    return target


def resolve_file(app_name, slot, relative):
    """The file a link points at, or None when it is missing or outside the app's own folder."""
    folder = paths.chosen(app_name, slot)
    if folder is None:
        return None
    allowed = folder.resolve()
    target = (allowed / relative).resolve()
    if not target.is_relative_to(allowed) or not target.is_file():
        return None
    return target
