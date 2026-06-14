import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CORPUS_DIR_DEFAULT = ROOT.parent / "pepa-sum" / "output"
DATA_DIR = ROOT / "data"
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
SECRETS_FILE = ROOT / "secrets.yaml"
SECRETS_EXAMPLE = ROOT / "secrets.example.yaml"
SKELETONS_FILE = DATA_DIR / "skeletons.json"

GENERATION_MODEL_DEFAULT = "claude-haiku-4-5-20251001"
GENERATION_MODEL_QUALITY = "claude-sonnet-4-6"
CONCURRENCY_DEFAULT = 8

_ENV_OVERRIDE = {
    "corpus_dir":        "PEPAPLAN_CORPUS_DIR",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "anthropic_model":   "PEPAPLAN_ANTHROPIC_MODEL",
    "review_model":      "PEPAPLAN_REVIEW_MODEL",
    "concurrency":       "PEPAPLAN_CONCURRENCY",
}

_PLACEHOLDERS = {"", "REPLACE_ME", "changeme"}


def _secrets():
    if SECRETS_FILE.exists():
        return yaml.safe_load(SECRETS_FILE.read_text(encoding="utf-8")) or {}
    return {}


def get(key, default=None):
    env_var = _ENV_OVERRIDE.get(key)
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    val = _secrets().get(key)
    return val if val not in (None, *_PLACEHOLDERS) else default


def corpus_dir():
    return Path(get("corpus_dir", CORPUS_DIR_DEFAULT))


def anthropic_api_key():
    return get("anthropic_api_key")


def anthropic_model():
    return get("anthropic_model", GENERATION_MODEL_DEFAULT)


def review_model():
    return get("review_model", GENERATION_MODEL_QUALITY)


def concurrency():
    return int(get("concurrency", CONCURRENCY_DEFAULT))


def set_values(updates):
    data = _secrets()
    data.update(updates)
    SECRETS_FILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
