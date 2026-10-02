import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
PROJECT = os.environ.get("PEPA_PROJECT")
DATA_ROOT = Path(PROJECT) / "pepa-plan" if PROJECT else ROOT
INSTALLED = ROOT.parent.name == "apps"
COMMAND = "pepa-plan" if INSTALLED else "python manage.py"
CORPUS_DIR_DEFAULT = DATA_ROOT.parent / "pepa-sum" / "output"
DATA_DIR = DATA_ROOT / "data"
INPUT_DIR = Path(os.environ.get("PEPAPLAN_INPUT_DIR", str(DATA_ROOT / "input")))
OUTPUT_DIR = Path(os.environ.get("PEPAPLAN_OUTPUT_DIR", str(DATA_ROOT / "output")))
TEMPLATES_DIR = ROOT / "templates"
EXAMPLE_TEMPLATE = TEMPLATES_DIR / "example.plan.md"
SECRETS_FILE = DATA_ROOT / "secrets.yaml"
SECRETS_EXAMPLE = ROOT / "secrets.example.yaml"
SKELETONS_FILE = DATA_DIR / "skeletons.json"
SEQUENCES_FILE = DATA_DIR / "sequences.json"
BLUEPRINTS_FILE = DATA_DIR / "blueprints.json"

GENERATION_MODEL_DEFAULT = "claude-haiku-4-5-20251001"
GENERATION_MODEL_QUALITY = "claude-sonnet-4-6"
CONCURRENCY_DEFAULT = 8

# `anthropic` calls Claude; `openai-compatible` calls any server that accepts OpenAI's
# chat format (DeepSeek, Kimi, Qwen, Ollama, vLLM) at llm_base_url.
BACKENDS = (
    "anthropic",
    "openai-compatible",
)

# How move-labelling is executed. `auto` picks serial/parallel/batch by estimated
# wall-clock; `batch` uses the Anthropic Message Batches API (50% cheaper, async), so
# it needs the anthropic backend.
MODES = ("auto", "serial", "parallel", "batch")

# Coarse planning constants that only steer the auto mode choice, never the work.
# Labelling is one fast LLM call per paper; the local read+parse is negligible.
EST_LABEL_SECONDS = 3.0        # one paper's labelling call, run serially
EST_PARALLEL_PPH = 2500        # realistic sustained papers/hour in parallel: the
                               # account rate limit, not the worker count, bounds
                               # this, so raising concurrency won't beat it
EST_BATCH_PPH = 6000           # papers/hour once a batch is running
EST_BATCH_FLOOR_MINUTES = 55   # batch latency floor (most batches finish within ~1h)

# USD per million tokens (input, output), for the post-run cost estimate only.
# Verify against current Anthropic pricing; these are not billing figures.
_PRICES_PER_MTOK = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}

_ENV_OVERRIDE = {
    "corpus_dir":        "PEPAPLAN_CORPUS_DIR",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "anthropic_model":   "PEPAPLAN_ANTHROPIC_MODEL",
    "review_model":      "PEPAPLAN_REVIEW_MODEL",
    "backend":           "PEPAPLAN_BACKEND",
    "llm_base_url":      "PEPAPLAN_LLM_BASE_URL",
    "llm_model":         "PEPAPLAN_LLM_MODEL",
    "llm_quality_model": "PEPAPLAN_LLM_QUALITY_MODEL",
    "llm_api_key":       "PEPA_LLM_API_KEY",
    "concurrency":       "PEPAPLAN_CONCURRENCY",
    "mode":              "PEPAPLAN_MODE",
    "batch_poll":        "PEPAPLAN_BATCH_POLL",
}

_PLACEHOLDERS = {"", "REPLACE_ME", "changeme"}

# Parsed secrets are cached: get() runs on every API call (via the concurrency
# governor), so re-reading and re-parsing the file each time would mean thousands
# of disk reads during a large labelling run. Keyed by the file's mtime so an edit
# between runs is still picked up; set_values() clears it after writing.
_secrets_cache = {"mtime": None, "data": {}}


def _secrets():
    if not SECRETS_FILE.exists():
        return {}
    mtime = SECRETS_FILE.stat().st_mtime
    if _secrets_cache["mtime"] != mtime:
        _secrets_cache["data"] = yaml.safe_load(SECRETS_FILE.read_text(encoding="utf-8")) or {}
        _secrets_cache["mtime"] = mtime
    return _secrets_cache["data"]


def get(key, default=None):
    env_var = _ENV_OVERRIDE.get(key)
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    val = _secrets().get(key)
    return val if val not in (None, *_PLACEHOLDERS) else default


def load():
    """The current settings, re-read every call so an edited secrets.yaml or a
    changed env var takes effect on the next call without a restart.

    Returns a dict with keys: corpus_dir, backend, anthropic_api_key, anthropic_model,
    review_model, concurrency, mode, batch_poll_seconds.
    """
    backend = get("backend", "anthropic")
    if backend not in BACKENDS:
        raise SystemExit(f"Unknown backend '{backend}'. Use one of: {', '.join(BACKENDS)}.")
    return {
        "corpus_dir": Path(get("corpus_dir", CORPUS_DIR_DEFAULT)),
        "backend": backend,
        "anthropic_api_key": get("anthropic_api_key"),
        "anthropic_model": get("anthropic_model", GENERATION_MODEL_DEFAULT),
        "review_model": get("review_model", GENERATION_MODEL_QUALITY),
        "concurrency": _clamped_int("concurrency", CONCURRENCY_DEFAULT, 1, 32),
        "mode": get("mode", "auto"),
        "batch_poll_seconds": _clamped_int("batch_poll", 30, 5, 300),
    }


def llm_connection():
    """The server address, key and models the openai-compatible backend uses."""
    base_url = get("llm_base_url")
    model = get("llm_model")
    if not base_url or not model:
        raise SystemExit(
            "The openai-compatible backend needs llm_base_url and llm_model in secrets.yaml, "
            "or the PEPAPLAN_LLM_BASE_URL and PEPAPLAN_LLM_MODEL variables."
        )
    return {
        "base_url": base_url,
        "api_key": get("llm_api_key"),
        "model": model,
        "quality_model": get("llm_quality_model", model),
    }


def model_names():
    """The fast and the quality model the configured backend generates with."""
    if get("backend", "anthropic") == "openai-compatible":
        model = get("llm_model")
        return {"fast": model, "quality": get("llm_quality_model", model)}
    return {
        "fast": get("anthropic_model", GENERATION_MODEL_DEFAULT),
        "quality": get("review_model", GENERATION_MODEL_QUALITY),
    }


def price_per_mtok(model):
    """(input, output) USD per million tokens for the model, or None if its price
    isn't known: the caller then reports tokens without a dollar figure."""
    for key, price in _PRICES_PER_MTOK.items():
        if model.startswith(key):
            return price
    return None


def _clamped_int(key, default, lo, hi):
    try:
        n = int(get(key, default))
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def set_values(updates):
    data = dict(_secrets())
    data.update(updates)
    SECRETS_FILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    _secrets_cache["mtime"] = None
