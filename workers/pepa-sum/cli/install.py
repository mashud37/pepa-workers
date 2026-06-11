"""Idempotent setup: create env.yaml, generate the token, check dependencies.

Safe to re-run — only missing/blank/placeholder values are filled, and a real
BASE_URL or JOB_TOKEN is never overwritten.
"""
import secrets
import shutil

import yaml

import config
from cli import ui

_PLACEHOLDERS = {"", "changeme", "REPLACE_ME"}
_CORE_DEPS = ["pypdf", "spacy", "sklearn", "rank_bm25", "numpy", "yaml"]


def run():
    ui.header("Install / setup")
    _ensure_dirs()
    _ensure_env()
    _check_deps()
    _check_spacy_model()
    _check_gcloud()
    ui.step("Next")
    ui.info("Deploy the model service:  python manage.py deploy")
    ui.info("Then drop PDFs in input/ and run:  python manage.py summarize")
    return 0


def _ensure_dirs():
    for d in (config.INPUT_DIR, config.OUTPUT_DIR, config.DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    ui.ok("input/, output/, data/ ready")


def _ensure_env():
    if not config.ENV_FILE.exists():
        shutil.copyfile(config.ENV_EXAMPLE, config.ENV_FILE)
        ui.ok("created env.yaml from template")

    data = yaml.safe_load(config.ENV_FILE.read_text(encoding="utf-8")) or {}
    changed = False
    if str(data.get("JOB_TOKEN", "")).strip() in _PLACEHOLDERS:
        data["JOB_TOKEN"] = secrets.token_hex(32)
        changed = True
        ui.ok("generated JOB_TOKEN")
    if changed:
        config.ENV_FILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    else:
        ui.info("env.yaml already configured")


def _check_deps():
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
    try:
        import spacy
        spacy.load("en_core_web_sm")
        ui.ok("spaCy model en_core_web_sm present")
    except Exception:
        ui.warn("spaCy model missing — python -m spacy download en_core_web_sm")


def _check_gcloud():
    if shutil.which("gcloud"):
        ui.ok("gcloud CLI found")
    else:
        ui.warn("gcloud CLI not found — needed for deploy (https://cloud.google.com/sdk)")
