"""Check the bundle's own dependencies and report which apps sit in workers/."""
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
    """What one app looks like from here: its folder and whether workers.yaml releases it."""
    folder = manifest.app_folder(name)
    found = "here" if folder.is_dir() else "missing"
    released = "yes" if entry["released"] else "no"
    return {"app": name, "folder": found, "released": released}


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
    ui.table(rows, ["app", "folder", "released"])
    return 0
