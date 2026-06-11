"""Effective configuration: I/O paths and the Cloud Run summariser endpoint.

Precedence for every value: environment variable -> env.yaml -> built-in
default. env.yaml is the gitignored Cloud Run config; only env.yaml.example is
committed, so a real BASE_URL / JOB_TOKEN never reaches git.
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
    "BASE_URL": "PEPA_BASE_URL",
    "JOB_TOKEN": "PEPA_JOB_TOKEN",
    "MODEL": "PEPA_MODEL",
}

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


def base_url():
    return get("BASE_URL")


def job_token():
    return get("JOB_TOKEN")


def model():
    return get("MODEL", "qwen2.5-3b-instruct")
