"""Idempotent setup: create env.yaml, fill settings/keys, check dependencies.

Safe to re-run — only missing/blank/placeholder values are filled; a real
ANTHROPIC_API_KEY, JOB_TOKEN, or BASE_URL is never overwritten.
"""
import getpass
import secrets
import shutil
import sys

import yaml

import config
from cli import ui

_PLACEHOLDERS = {"", "changeme", "REPLACE_ME"}
_CORE_DEPS = ["anthropic", "pypdf", "spacy", "sklearn", "rank_bm25", "numpy", "yaml"]
_DEFAULTS = {"BACKEND": "anthropic", "PARA_METHOD": "llm", "ON_EXISTING": "ask"}


def run():
    ui.header("Install / setup")
    ui.info("  · 1/4  Directories")
    ui.info("  · 2/4  Environment / secrets")
    ui.info("  · 3/4  Python dependencies")
    ui.info("  · 4/4  spaCy model")
    _ensure_dirs()
    _ensure_env()
    _check_deps()
    _check_spacy_model()
    ui.step("Next")
    if config.backend() == "anthropic":
        ui.info("Drop PDFs in input/ and run:  python manage.py summarize")
    else:
        ui.info("Deploy the self-hosted service:  python manage.py deploy")
    return 0


def _ensure_dirs():
    ui.step("Directories")
    for d in (config.INPUT_DIR, config.OUTPUT_DIR, config.DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    ui.ok("input/, output/, data/ ready")


def _ensure_env():
    ui.step("Environment / secrets")
    if not config.ENV_FILE.exists():
        shutil.copyfile(config.ENV_EXAMPLE, config.ENV_FILE)
        ui.ok("created env.yaml from template")

    data = yaml.safe_load(config.ENV_FILE.read_text(encoding="utf-8")) or {}
    changed = False

    for key, default in _DEFAULTS.items():
        if str(data.get(key, "")).strip() in _PLACEHOLDERS:
            data[key] = default
            changed = True

    if str(data.get("JOB_TOKEN", "")).strip() in _PLACEHOLDERS:
        data["JOB_TOKEN"] = secrets.token_hex(32)
        changed = True
        ui.ok("generated JOB_TOKEN (self-hosted fallback)")

    if data.get("BACKEND") == "anthropic" and not config.anthropic_api_key():
        key = _prompt_api_key()
        if key:
            data["ANTHROPIC_API_KEY"] = key
            changed = True
            ui.ok("stored ANTHROPIC_API_KEY")

    if changed:
        config.ENV_FILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    else:
        ui.info("env.yaml already configured")


def _prompt_api_key():
    if not sys.stdin.isatty():
        ui.warn("ANTHROPIC_API_KEY not set — paste it during an interactive install "
                "or set the ANTHROPIC_API_KEY env var")
        return None
    return getpass.getpass("  Anthropic API key (blank to skip): ").strip()


def _check_deps():
    ui.step("Python dependencies")
    import importlib
    missing = [m for m in _CORE_DEPS if not _importable(importlib, m)]
    if missing:
        ui.warn(f"missing packages: {', '.join(missing)} — pip install -r requirements.txt")
    else:
        ui.ok("python dependencies present")


def _importable(importlib, name):
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def _check_spacy_model():
    from cli.progress import StepSpinner
    ui.step("spaCy model")
    sp = StepSpinner("loading en_core_web_sm")
    sp.start()
    try:
        import spacy
        spacy.load("en_core_web_sm")
        sp.done("present")
        ui.ok("spaCy model en_core_web_sm present")
    except Exception:
        sp.done("missing")
        ui.warn("spaCy model missing — python -m spacy download en_core_web_sm")
