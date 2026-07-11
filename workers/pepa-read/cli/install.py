"""Idempotent setup: ensure data/, check dependencies, verify source dirs exist."""
import importlib

import config
from cli import ui

_CORE_DEPS = ["flask"]
_OPTIONAL_DEPS = ["markdown"]


def run():
    ui.header("Install / setup")
    _ensure_dirs()
    _check_deps()
    _check_sources()
    ui.step("Next steps")
    ui.info("1) python manage.py index   — build the search index")
    ui.info("2) python manage.py         — open the web UI")
    return 0


def _ensure_dirs():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    (config.DB_PATH.parent / ".gitkeep").touch()
    ui.ok("data/ ready")


def _check_deps():
    missing = [m for m in _CORE_DEPS if not _importable(m)]
    if missing:
        ui.warn(f"missing packages: {', '.join(missing)} — run: pip install -r requirements.txt")
    else:
        ui.ok("core dependencies present")

    missing_optional = [m for m in _OPTIONAL_DEPS if not _importable(m)]
    if missing_optional:
        ui.info(f"optional: {', '.join(missing_optional)} not installed — "
                 "/view/<id> will fall back to plain text")
    else:
        ui.ok("optional dependencies present")


def _importable(mod):
    try:
        importlib.import_module(mod)
        return True
    except ImportError:
        return False


def _check_sources():
    for label, d in (("pepa-prep text", config.TEXT_DIR), ("pepa-sum output", config.SUM_DIR)):
        if d.exists():
            ui.ok(f"{label} dir found: {d}")
        else:
            ui.warn(f"{label} dir not found: {d}")
            ui.info("override with PEPA_READER_TEXT_DIR / PEPA_READER_SUM_DIR if it lives elsewhere")
