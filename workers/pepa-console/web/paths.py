"""Decide which folder each child app reads from and writes to, and remember the user's choice.
Jobs receive these folders as environment variables, so no child's config file is edited.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from registry import ROOT
from web.settings import SETTINGS

# Every folder a child app can be pointed at. A `reads` folder is only ever read,
# which is the promise the Folders page makes about a linked library.
PLACES = [
    {"app": "pepa-prep", "slot": "sources", "role": "reads", "label": "PDFs to prepare", "variable": "PEPAPREP_INPUT_DIR", "default": "pepa-prep/input"},
    {"app": "pepa-prep", "slot": "results", "role": "writes", "label": "Prepared text", "variable": "PEPAPREP_OUTPUT_DIR", "default": "pepa-prep/output"},
    {"app": "pepa-sum", "slot": "sources", "role": "reads", "label": "Papers to summarise", "variable": "PEPA_INPUT_DIR", "default": "pepa-sum/input"},
    {"app": "pepa-sum", "slot": "results", "role": "writes", "label": "Summaries", "variable": "PEPA_OUTPUT_DIR", "default": "pepa-sum/output"},
    {"app": "pepa-read", "slot": "texts", "role": "reads", "label": "Prepared text to index", "variable": "PEPA_READER_TEXT_DIR", "default": "pepa-prep/output/text"},
    {"app": "pepa-read", "slot": "summaries", "role": "reads", "label": "Summaries to index", "variable": "PEPA_READER_SUM_DIR", "default": "pepa-sum/output"},
    {"app": "pepa-review", "slot": "corpus", "role": "reads", "label": "Summary corpus", "variable": "PEPAREVIEW_CORPUS_DIR", "default": "pepa-sum/output"},
    {"app": "pepa-review", "slot": "drafts", "role": "reads", "label": "Outlines and drafts", "variable": "PEPAREVIEW_INPUT_DIR", "default": "pepa-review/input"},
    {"app": "pepa-review", "slot": "results", "role": "writes", "label": "Reviews, gaps and maps", "variable": "PEPAREVIEW_OUTPUT_DIR", "default": "pepa-review/output"},
    {"app": "pepa-plan", "slot": "corpus", "role": "reads", "label": "Summary corpus", "variable": "PEPAPLAN_CORPUS_DIR", "default": "pepa-sum/output"},
    {"app": "pepa-plan", "slot": "drafts", "role": "reads", "label": "Ideas and drafts", "variable": "PEPAPLAN_INPUT_DIR", "default": "pepa-plan/input"},
    {"app": "pepa-plan", "slot": "results", "role": "writes", "label": "Outlines", "variable": "PEPAPLAN_OUTPUT_DIR", "default": "pepa-plan/output"},
    {"app": "pepa-draft", "slot": "drafts", "role": "reads", "label": "Plans and reviews", "variable": "PEPADRAFT_INPUT_DIR", "default": "pepa-draft/input"},
    {"app": "pepa-draft", "slot": "results", "role": "writes", "label": "Manuscripts", "variable": "PEPADRAFT_OUTPUT_DIR", "default": "pepa-draft/output"},
]

# The only folders that can be read with their sub-folders: the two apps that read
# a library of papers. Each child takes the choice as this environment variable.
SUBFOLDER_VARIABLES = {
    "pepa-prep/sources": "PEPAPREP_SUBFOLDERS",
    "pepa-sum/sources": "PEPA_SUBFOLDERS",
}

OPEN_COMMAND = {
    "darwin": "open",
    "linux": "xdg-open",
}

FOLDERS_FILE_NAME = "folders.json"
DRIVE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_ENTRIES = 500


# ---- The store ----

def store_file():
    """Where the chosen folders are kept: beside the key store, outside the workspace."""
    return SETTINGS["keys_file"].parent / FOLDERS_FILE_NAME


def load_store():
    """Every choice the user has made: a folder per app and slot, and which are read deeply.

    Returns:
        dict with "project", the folder every app keeps its own files in,
        "folders", keyed `app/slot`, and "subfolders", the keys read with their sub-folders. A store written before deep reading existed holds
        the folders alone, so it is read as such.
    """
    path = store_file()
    if not path.exists():
        return {"project": "", "folders": {}, "subfolders": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if "folders" not in data:
        return {"project": "", "folders": data, "subfolders": []}
    return {
        "project": data.get("project", ""),
        "folders": data["folders"],
        "subfolders": data.get("subfolders", []),
    }


def save_store(store):
    """Write the store through a temporary file, so a crash never leaves half a file behind."""
    path = store_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(store, indent=2), encoding="utf-8")
    os.replace(temporary, path)


# ---- Which folder an app uses ----

def project_folder():
    """The folder every app keeps its own files in: the user's choice, then PEPA_PROJECT,
    then the folder that holds the apps themselves."""
    picked = load_store()["project"]
    if picked:
        return Path(picked)
    if os.environ.get("PEPA_PROJECT"):
        return Path(os.environ["PEPA_PROJECT"])
    return ROOT


def set_project(path_text):
    """Move every app's own files to another project folder, or back to the default when blank.

    Raises:
        ValueError: the path is not absolute, or the folder cannot be created.
    """
    store = load_store()
    if not path_text.strip():
        store["project"] = ""
        save_store(store)
        return
    folder = Path(path_text.strip())
    if not folder.is_absolute():
        raise ValueError("Give the full path, starting at the drive or the root folder.")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"Could not create {folder}: {error}") from error
    store["project"] = str(folder)
    save_store(store)


def find_place(app_name, slot):
    """The one registered folder of an app, or None when there is no such slot."""
    for place in PLACES:
        if place["app"] == app_name and place["slot"] == slot:
            return place
    return None


def places_of(app_name):
    """Every folder this app can be pointed at, in the order the pages show them."""
    found = []
    for place in PLACES:
        if place["app"] == app_name:
            found.append(place)
    return found


def default_path(place):
    """The folder this slot uses when the user has chosen nothing: the app's own folder in the project."""
    return (project_folder() / place["default"]).resolve()


def owned_by_app(place, folder):
    """True when a folder belongs to the app itself, which is the only kind files are copied into."""
    if place["role"] != "reads" or folder != default_path(place):
        return False
    return place["default"].startswith(place["app"] + "/")


def chosen(app_name, slot):
    """The folder an app uses for one slot right now: the user's choice, or the default."""
    place = find_place(app_name, slot)
    if place is None:
        return None
    picked = load_store()["folders"].get(f"{app_name}/{slot}")
    if picked:
        return Path(picked)
    return default_path(place)


def source_folders():
    """Every folder that is only ever read, as chosen now."""
    folders = []
    for place in PLACES:
        if place["role"] == "reads":
            folders.append(chosen(place["app"], place["slot"]))
    return folders


def can_scan_subfolders(app_name, slot):
    """True when this folder is one of the two that can be read with its sub-folders."""
    return f"{app_name}/{slot}" in SUBFOLDER_VARIABLES


def scans_subfolders(app_name, slot):
    """True when the user asked for this folder to be read with its sub-folders."""
    return f"{app_name}/{slot}" in load_store()["subfolders"]


def set_subfolders(app_name, slot, wanted):
    """Read one folder with its sub-folders from now on, or stop doing so.

    Raises:
        ValueError: this folder is always read one level deep.
    """
    key = f"{app_name}/{slot}"
    if key not in SUBFOLDER_VARIABLES:
        raise ValueError("That folder is read one level deep only.")
    store = load_store()
    kept = [name for name in store["subfolders"] if name != key]
    if wanted:
        kept.append(key)
    store["subfolders"] = sorted(kept)
    save_store(store)


def environment_for(app_name):
    """The folder variables a job of this app receives, so the child writes where the user chose."""
    environment = {"PEPA_PROJECT": str(project_folder())}
    for place in PLACES:
        if place["app"] == app_name:
            environment[place["variable"]] = str(chosen(app_name, place["slot"]))
    for key, variable in SUBFOLDER_VARIABLES.items():
        owner, slot = key.split("/")
        if owner == app_name:
            environment[variable] = "on" if scans_subfolders(owner, slot) else "off"
    return environment


# ---- Changing a folder ----

def check_folder(place, folder):
    """Refuse a folder an app cannot use, and create a results folder that is not there yet.

    Raises:
        ValueError: a source folder is missing, or results would land inside a source folder.
    """
    if place["role"] == "reads":
        if not folder.is_dir():
            raise ValueError(f"No such folder: {folder}")
        return
    for source in source_folders():
        if folder == source or folder.is_relative_to(source):
            raise ValueError(f"Results cannot go inside {source}, which is only ever read.")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"Could not create {folder}: {error}") from error


def set_place(app_name, slot, path_text):
    """Point one app's folder somewhere else, or hand it back to the default when blank.

    Raises:
        ValueError: there is no such slot, or the folder cannot be used for it.
    """
    place = find_place(app_name, slot)
    if place is None:
        raise ValueError(f"{app_name} has no {slot} folder.")
    store = load_store()
    key = f"{app_name}/{slot}"
    if not path_text.strip():
        store["folders"].pop(key, None)
        save_store(store)
        return
    folder = Path(path_text.strip())
    if not folder.is_absolute():
        raise ValueError("Give the full path, starting at the drive or the root folder.")
    check_folder(place, folder)
    store["folders"][key] = str(folder)
    save_store(store)


# ---- What the page shows ----

def page_rows():
    """Every app with its folders: where each points, whether it is the default, and if it is there."""
    apps = []
    for place in PLACES:
        folder = chosen(place["app"], place["slot"])
        is_default = str(folder) == str(default_path(place))
        row = {
            "slot": place["slot"],
            "label": place["label"],
            "role": place["role"],
            "variable": place["variable"],
            "path": str(folder),
            "is_default": is_default,
            "read_only": place["role"] == "reads" and not is_default,
            "exists": folder.is_dir(),
            "can_scan": can_scan_subfolders(place["app"], place["slot"]),
            "deep": scans_subfolders(place["app"], place["slot"]),
        }
        if apps and apps[-1]["name"] == place["app"]:
            apps[-1]["rows"].append(row)
        else:
            apps.append({"name": place["app"], "rows": [row]})
    return apps


# ---- Browsing for a folder ----

def starting_points():
    """Where the picker starts: this computer's drives on Windows, the home folder elsewhere."""
    if os.name == "nt":
        found = []
        for letter in DRIVE_LETTERS:
            drive = Path(f"{letter}:/")
            if drive.exists():
                found.append({"name": f"{letter}:", "path": str(drive)})
        return found
    return [
        {"name": "Home", "path": str(Path.home())},
        {"name": "/", "path": "/"},
    ]


def sub_folders(folder):
    """The folders directly inside this one, sorted by name, hidden and system ones left out."""
    names = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.name.startswith(".") or entry.name.startswith("$"):
                continue
            if entry.is_dir():
                names.append(entry.name)
    names.sort(key=str.lower)
    return names[:MAX_ENTRIES]


def browse(path_text):
    """One level of the filesystem for the folder picker: where we are, what is in it, and the way up.

    Returns:
        dict with "path", "parent", "folders" as name and path pairs, and "message" when
        the folder cannot be read.
    """
    if not path_text.strip():
        return {"path": "", "parent": None, "folders": starting_points(), "message": ""}
    folder = Path(path_text)
    parent = "" if folder.parent == folder else str(folder.parent)
    try:
        names = sub_folders(folder)
    except OSError:
        return {"path": str(folder), "parent": parent, "folders": [], "message": "This folder cannot be opened."}
    inside = []
    for name in names:
        inside.append({"name": name, "path": str(folder / name)})
    return {"path": str(folder), "parent": parent, "folders": inside, "message": ""}


def open_in_file_manager(path_text):
    """Show a folder in the desktop's own file manager.

    Raises:
        ValueError: the folder is missing, or the desktop refused to open it.
    """
    folder = Path(path_text)
    if not folder.is_dir():
        raise ValueError(f"No such folder: {folder}")
    if os.name == "nt":
        os.startfile(folder)
        return
    command = OPEN_COMMAND.get(sys.platform, "xdg-open")
    try:
        subprocess.Popen([command, str(folder)])
    except OSError as error:
        raise ValueError(f"Could not open {folder}: {error}") from error
