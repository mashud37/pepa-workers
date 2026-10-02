"""Read workers.yaml and say which apps ship and what each leaves out."""
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_FILE = ROOT / "workers.yaml"
# Built outside the repository, where a syncing folder cannot lock files mid-build.
BUILD_FOLDER = Path(tempfile.gettempdir()) / "pepa-workers-build"
DIST_FOLDER = ROOT / "dist"

REQUIRED_APP_KEYS = [
    "released",
    "leave_out",
]


def load():
    """Everything workers.yaml holds, with every app entry checked for the keys a build needs.

    Returns:
        dict with the package fields and "apps", keyed by app name.

    Raises:
        SystemExit: the manifest is missing or an app entry is incomplete.
    """
    if not MANIFEST_FILE.exists():
        raise SystemExit(f"No manifest at {MANIFEST_FILE}.")
    manifest = yaml.safe_load(MANIFEST_FILE.read_text(encoding="utf-8"))
    for name, entry in manifest["apps"].items():
        for key in REQUIRED_APP_KEYS:
            if key not in entry:
                raise SystemExit(f"{name} in workers.yaml has no {key}.")
    return manifest


def chosen_apps(manifest, include_unreleased):
    """The apps this build takes: the released ones, or every one for a development build."""
    names = []
    for name, entry in manifest["apps"].items():
        if entry["released"] or include_unreleased:
            names.append(name)
    return names


def app_folder(name):
    """Where one app sits in this repository."""
    return ROOT / "workers" / name
