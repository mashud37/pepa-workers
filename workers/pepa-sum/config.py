"""Resolve effective configuration (I/O paths, LLM backend, run settings)
with precedence: environment variable, then env.yaml, then a built-in
default.
"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
INPUT_DIR = Path(os.environ.get("PEPA_INPUT_DIR", str(ROOT / "input")))
OUTPUT_DIR = Path(os.environ.get("PEPA_OUTPUT_DIR", str(ROOT / "output")))
DATA_DIR = ROOT / "data"
ENV_FILE = ROOT / "env.yaml"
ENV_EXAMPLE = ROOT / "env.yaml.example"

# env.yaml key -> overriding environment variable
_ENV_OVERRIDE = {
    "BACKEND": "PEPA_BACKEND",
    "PARA_METHOD": "PEPA_PARA_METHOD",
    "ON_EXISTING": "PEPA_ON_EXISTING",
    "SUBFOLDERS": "PEPA_SUBFOLDERS",
    "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL": "PEPA_ANTHROPIC_MODEL",
    "BASE_URL": "PEPA_BASE_URL",
    "JOB_TOKEN": "PEPA_JOB_TOKEN",
    "MODEL": "PEPA_MODEL",
    "MAX_WORKERS": "PEPA_MAX_WORKERS",
    "PAPER_WORKERS": "PEPA_PAPER_WORKERS",
    "MAX_CONCURRENCY": "PEPA_MAX_CONCURRENCY",
    "MODE": "PEPA_MODE",
    "SPEED": "PEPA_SPEED",
    "LOCAL_WORKERS": "PEPA_LOCAL_WORKERS",
    "LOCAL_BATCH": "PEPA_LOCAL_BATCH",
    "BATCH_POLL": "PEPA_BATCH_POLL",
    "OCR": "PEPA_OCR",
    "OCR_DPI": "PEPA_OCR_DPI",
}

# env.yaml key -> built-in default for the plain settings, resolved by load().
DEFAULTS = {
    "BACKEND": "anthropic",
    "PARA_METHOD": "llm",
    "ON_EXISTING": "ask",
    "SUBFOLDERS": "off",
    "ANTHROPIC_API_KEY": None,
    "ANTHROPIC_MODEL": "claude-haiku-4-5-20251001",
    "BASE_URL": None,
    "JOB_TOKEN": None,
    "MODEL": "qwen2.5-3b-instruct",
    "MODE": "auto",
}

# Run-mode auto-selection. `auto` estimates wall-clock for each mode and picks
# the fastest; batch additionally bills at 50%, so it wins on large volumes.
# These are coarse planning constants (tune to your tier/machine); they only
# steer mode choice, never the actual work. Calibrated to observed runs:
# ~1h for 1000 papers in batch, ~1h20m in parallel at the `balanced` tier (the
# parallel rate scales with the speed tier: see SPEED_TIERS / est_parallel_pph).
EST_LOCAL_SECONDS = 4.0        # local read + spaCy signals + BM25, per paper (CPU)
EST_LLM_SECONDS = 50.0         # a paper's LLM calls, summed, run one after another
EST_BATCH_PPH = 6000           # papers/hour once a batch is running
EST_BATCH_FLOOR_MINUTES = 55   # batch latency floor (most batches finish within ~1h)

# USD per million tokens (input, output), for the post-run cost estimate only.
# Verify against current Anthropic pricing; these are not billing figures.
_PRICES_PER_MTOK = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}

BACKENDS = ("anthropic", "cloudrun")
PARA_METHODS = ("llm", "extractive")
# OCR policy for scanned pages. `auto` only OCRs a document that is mostly image
# (so a born-digital paper's odd figure page never triggers a slow tesseract
# pass); `off` never OCRs (scanned papers yield little text and are skipped, the
# fast path); `force` OCRs every sparse page as before.
OCR_MODES = ("auto", "off", "force")
# What to do with a paper whose three documents all already exist.
ON_EXISTING_MODES = ("ask", "skip", "overwrite")
# How the run is executed. `auto` picks serial/parallel/batch by estimated time;
# `batch` uses the Anthropic Message Batches API (anthropic backend only).
MODES = ("auto", "serial", "parallel", "batch")

# Speed tiers for the parallel path: one dial that moves the API throughput
# (papers in flight, total live LLM calls, per-paper rundown fan-out). Each tier
# only sets *defaults*: an explicit PAPER_WORKERS / MAX_CONCURRENCY / ... (env
# var or env.yaml) still overrides it. The local reading pool is sized to the
# machine's cores (see local_workers), independent of the tier. `pph` is the
# realistic sustained papers/hour used to estimate the parallel wall-clock for
# auto mode selection (calibrated to observed runs, ~750/h at balanced); turbo
# leans on rate-limit headroom, eco stays gentle on the tier.
SPEED_TIERS = ("eco", "balanced", "turbo")
_SPEED = {
    "eco":      {"paper": 3,  "conc": 8,  "rundown": 3, "pph": 380},
    "balanced": {"paper": 6,  "conc": 16, "rundown": 4, "pph": 750},
    "turbo":    {"paper": 12, "conc": 28, "rundown": 6, "pph": 1200},
}

# Characters of paper text sent to the LLM. Anthropic models have a 200k-token
# context; this caps only the body text, so it must stay well under the ceiling
# to leave room for the signals block, system prompt, and the output reservation
# (~200k tokens ≈ 800k chars, but dense academic text runs ~3.5 chars/token, so
# 600k keeps the full-text path safely under the limit). Past it we fall back to
# opening + retrieved passages. The cloudrun self-hosted model is limited to 16k
# tokens (~36k chars), so it falls back far sooner.
_TEXT_BUDGET_CLOUDRUN = 70_000
_TEXT_BUDGET_ANTHROPIC = 600_000


def text_budget():
    return _TEXT_BUDGET_CLOUDRUN if load("BACKEND") == "cloudrun" else _TEXT_BUDGET_ANTHROPIC


def _file_values():
    if ENV_FILE.exists():
        return yaml.safe_load(ENV_FILE.read_text(encoding="utf-8")) or {}
    return {}


def get(key, default=None):
    env = _ENV_OVERRIDE.get(key)
    if env and os.environ.get(env):
        return os.environ[env]
    val = _file_values().get(key)
    return val if val not in (None, "") else default


def load(key):
    """Effective value for a plain env.yaml setting: env var, then env.yaml,
    then the built-in default in DEFAULTS."""
    return get(key, DEFAULTS[key])


def ocr_mode():
    """How to handle scanned pages: auto | off | force. See OCR_MODES. `auto`
    keeps born-digital papers fast by only OCR-ing genuinely scanned documents.

    Tolerates YAML's boolean coercion: an unquoted `off`/`no`/`false` in env.yaml
    is parsed as Python False (and `on`/`yes`/`true` as True), so `OCR: off` would
    otherwise silently fall back to the default. Map those back to real modes."""
    raw = get("OCR", "auto")
    if raw is False:
        return "off"
    if raw is True:
        return "auto"
    val = str(raw).lower()
    return val if val in OCR_MODES else "auto"


def scan_subfolders():
    """Whether papers inside the input folder's own folders are summarised too.

    Tolerates YAML's boolean coercion the way ocr_mode does: an unquoted
    `on`/`off` in env.yaml arrives as Python True/False, not as a word."""
    raw = get("SUBFOLDERS", "off")
    if raw is True or raw is False:
        return raw
    return str(raw).lower() in ("1", "true", "yes", "on")


def ocr_dpi():
    """Rasterisation DPI for OCR. Lower is much faster and usually still legible
    for body text; raise it only if OCR output is poor."""
    return _clamped_int("OCR_DPI", 200, 72, 400)


def price_per_mtok(model=None):
    """(input, output) USD per million tokens for the model, or None if its
    price isn't known: the caller then reports tokens without a dollar figure."""
    model = model or load("ANTHROPIC_MODEL")
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


def speed():
    """Parallel-path speed tier: eco | balanced | turbo. One dial behind the
    throughput knobs (papers in flight, live LLM calls, rundown fan-out, local
    pool). Anything set explicitly still overrides the tier's default."""
    val = (get("SPEED", "balanced") or "balanced").lower()
    return val if val in SPEED_TIERS else "balanced"


def _tier():
    return _SPEED[speed()]


def est_parallel_pph():
    """Realistic sustained papers/hour in parallel for the current speed tier,
    used only to estimate the parallel wall-clock for auto mode selection."""
    return _tier()["pph"]


def max_workers():
    """Concurrent LLM requests for the paragraph rundown. The self-hosted
    cloudrun model is a single scale-to-zero instance, so it stays serial."""
    if load("BACKEND") == "cloudrun":
        return 1
    return _clamped_int("MAX_WORKERS", _tier()["rundown"], 1, 8)


def paper_workers():
    """Papers processed concurrently across the batch. cloudrun is a single
    scale-to-zero instance, so it stays serial regardless of this value."""
    if load("BACKEND") == "cloudrun":
        return 1
    return _clamped_int("PAPER_WORKERS", _tier()["paper"], 1, 16)


def max_concurrency():
    """Hard cap on total simultaneous Anthropic requests across all papers and
    their internal fan-out: the real throttle that bounds rate-limit exposure
    however the paper and rundown pools happen to nest."""
    return _clamped_int("MAX_CONCURRENCY", _tier()["conc"], 1, 32)


def local_workers():
    """Processes for the CPU-bound local stage (PDF read + spaCy + BM25). Run in
    separate processes so the work escapes the GIL and genuinely parallelises.

    Each worker loads its own spaCy model and holds a paper's text, so this is a
    memory-bound knob: too many processes exhausts RAM and crashes the run. It is
    therefore capped conservatively (<=8 by default), NOT raised to the core
    count. The speed win comes from pinning each worker to a single BLAS/OMP
    thread (see cli/summarize._pin_threads) so these few workers stop thrashing,
    not from spawning more of them. Raise LOCAL_WORKERS only if you have the RAM
    headroom; lower it if memory is tight."""
    import os
    default = min(os.cpu_count() or 4, 8)
    return _clamped_int("LOCAL_WORKERS", default, 1, 32)


def local_batch():
    """Look-ahead window for parallel mode: how many papers the local reading
    pool may run *ahead* of the LLM pool. Extraction for the next papers proceeds
    on the CPU while the current papers' LLM calls wait on the network, but at
    most this many extracted papers are held in memory at once, so peak memory
    stays bounded instead of holding every paper's text. Defaults to keeping the
    paper pool comfortably fed."""
    default = max(paper_workers() * 4, 24)
    return _clamped_int("LOCAL_BATCH", default, 4, 2000)


def batch_poll_seconds():
    """How often to poll a running Message Batch for completion."""
    return _clamped_int("BATCH_POLL", 30, 5, 300)


def set_values(updates):
    """Persist non-secret settings into env.yaml, preserving everything else. A
    value of None removes that key, so a setting can hand control back to a
    computed default (e.g. a speed tier reclaiming the throughput knobs)."""
    data = _file_values()
    for key, val in updates.items():
        if val is None:
            data.pop(key, None)
        else:
            data[key] = val
    ENV_FILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
