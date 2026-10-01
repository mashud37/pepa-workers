"""Check the bundle's own dependencies and report which app repositories sit beside it."""
import subprocess
import sys

from bundle import manifest

from . import ui

NEEDED_MODULES = [
    "yaml",
    "build",
]


def module_missing(name):
    """True when a module the bundle needs cannot be imported."""
    asked = [sys.executable, "-c", f"import {name}"]
    return subprocess.run(asked, capture_output=True).returncode != 0


def app_row(name, entry):
    """What one app looks like from here: its folder, its repository, and the ref the manifest names."""
    folder = manifest.app_folder(name)
    if not folder.is_dir():
        return {"app": name, "folder": "missing", "ref": entry["ref"], "commit": ""}
    if not (folder / ".git").is_dir():
        return {"app": name, "folder": "no repository", "ref": entry["ref"], "commit": ""}
    asked = ["git", "-C", str(folder), "rev-parse", "--verify", f"{entry['ref']}^{{commit}}"]
    found = subprocess.run(asked, capture_output=True, text=True)
    if found.returncode != 0:
        return {"app": name, "folder": "here", "ref": entry["ref"], "commit": "no such ref"}
    return {"app": name, "folder": "here", "ref": entry["ref"], "commit": found.stdout.strip()[:8]}


def run():
    """Report the missing dependencies and every app the manifest expects to find."""
    ui.step("Checking pepa-workers")
    missing = [name for name in NEEDED_MODULES if module_missing(name)]
    if missing:
        ui.warn(f"missing: {', '.join(missing)}  (pip install -r requirements.txt)")
    else:
        ui.ok("dependencies present")

    settings = manifest.load()
    names = sorted(settings["apps"])
    ui.step(f"Apps  [{len(names)}]")
    rows = [app_row(name, settings["apps"][name]) for name in names]
    ui.table(rows, ["app", "folder", "ref", "commit"])
    return 0
