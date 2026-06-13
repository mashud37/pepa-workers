"""Effective configuration: I/O paths, the LLM backend, and run settings.

Precedence for every value: environment variable -> env.yaml -> built-in
default. env.yaml is the gitignored config; only env.yaml.example is committed,
so a real ANTHROPIC_API_KEY / BASE_URL / JOB_TOKEN never reaches git.
"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
DATA_DIR = ROOT / "data"
ENV_FILE = ROOT / "env.yaml"
ENV_EXAMPLE = ROOT / "env.yaml.example"

# env.yaml key -> overriding environment variable
_ENV_OVERRIDE = {
    "BACKEND": "PEPA_BACKEND",
    "PARA_METHOD": "PEPA_PARA_METHOD",
    "ON_EXISTING": "PEPA_ON_EXISTING",
    "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL": "PEPA_ANTHROPIC_MODEL",
    "BASE_URL": "PEPA_BASE_URL",
    "JOB_TOKEN": "PEPA_JOB_TOKEN",
    "MODEL": "PEPA_MODEL",
}

BACKENDS = ("anthropic", "cloudrun")
PARA_METHODS = ("llm", "extractive")
# What to do with a paper whose three documents all already exist.
ON_EXISTING_MODES = ("ask", "skip", "overwrite")

# Max characters of paper text sent alongside the signals. ~36k chars is ~9k
# tokens; with the signals and output it stays well inside the 16k context
# window and keeps CPU generation fast. Longer papers fall back to opening +
# retrieved passages (see backends/prompt.py).
TEXT_BUDGET = 36000


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


def backend():
    return get("BACKEND", "anthropic")


def para_method():
    return get("PARA_METHOD", "llm")


def on_existing():
    return get("ON_EXISTING", "ask")


def anthropic_api_key():
    return get("ANTHROPIC_API_KEY")


def anthropic_model():
    return get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def base_url():
    return get("BASE_URL")


def job_token():
    return get("JOB_TOKEN")


def model():
    return get("MODEL", "qwen2.5-3b-instruct")


def set_values(updates):
    """Persist non-secret settings into env.yaml, preserving everything else."""
    data = _file_values()
    data.update(updates)
    ENV_FILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
