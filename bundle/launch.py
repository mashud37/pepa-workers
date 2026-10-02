"""Run one bundled app's manage.py with only that app's folder on the import path.
Installed as each app's command, so every app runs in its own process.
"""
import os
import runpy
import sys
from pathlib import Path

APPS_FOLDER = Path(__file__).resolve().parent / "apps"
DEFAULT_PROJECT = Path.home() / "pepa-workers"


def main():
    app_name = Path(sys.argv[0]).stem
    app_folder = APPS_FOLDER / app_name
    if not (app_folder / "manage.py").exists():
        raise SystemExit(f"This package does not hold {app_name}.")
    if not os.environ.get("PEPA_PROJECT"):
        os.environ["PEPA_PROJECT"] = str(DEFAULT_PROJECT)
    sys.path.insert(0, str(app_folder))
    runpy.run_path(str(app_folder / "manage.py"), run_name="__main__")


if __name__ == "__main__":
    main()
