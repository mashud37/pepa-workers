"""Hold pepa-host's settings in one dictionary: where its files live, each server's model, and its size on each host.
The commands import SETTINGS, SERVERS and HOSTS.
"""
import os
from pathlib import Path

# ---- Where things live ----

ROOT = Path(__file__).resolve().parent
PROJECT = os.environ.get("PEPA_PROJECT")
DATA_ROOT = Path(PROJECT) / "pepa-host" if PROJECT else ROOT
INSTALLED = ROOT.parent.name == "apps"
COMMAND = "pepa-host" if INSTALLED else "python manage.py"
IMAGES_DIR = ROOT / "images"
SERVERS_FILE = DATA_ROOT / "data" / "servers.json"

# ---- Defaults ----
# PEPAHOST_<KEY> in the environment overrides each of these.

DEFAULTS = {
    "gcloud_region": "europe-west1",
    "azure_region": "swedencentral",
    "name_prefix": "pepa",
}

ENV_PREFIX = "PEPAHOST_"

# ---- The servers ----
# Each server is one image under images/, and its size on each host: concurrency is how many
# requests it answers at once. The variables reach the running server as environment variables.

SERVERS = {
    "small": {
        "label": "Small model on CPU",
        "detail": "Qwen2.5 3B, enough for pepa-sum's briefs",
        "model": "qwen2.5-3b-instruct",
        "gcloud": {
            "cpu": "8",
            "memory": "8Gi",
            "gpu": "",
            "concurrency": 1,
            "context_tokens": 32768,
            "variables": {"N_THREADS": "8"},
        },
        "azure": {
            "cpu": "4",
            "memory": "8Gi",
            "profile": "Consumption",
            "concurrency": 1,
            "context_tokens": 32768,
            "variables": {"N_THREADS": "4"},
        },
    },
    "large": {
        "label": "Large model on GPU",
        "detail": "Qwen3 32B, for reviews, outlines and drafts",
        "model": "Qwen/Qwen3-32B-AWQ",
        "gcloud": {
            "cpu": "8",
            "memory": "32Gi",
            "gpu": "nvidia-l4",
            "concurrency": 4,
            "context_tokens": 8192,
            "variables": {"MAX_MODEL_LEN": "8192"},
        },
        "azure": {
            "cpu": "8",
            "memory": "56Gi",
            "profile": "Consumption-GPU-NC24-A100",
            "concurrency": 4,
            "context_tokens": 32768,
            "variables": {"MAX_MODEL_LEN": "32768"},
        },
    },
}

HOSTS = {
    "gcloud": {"label": "Google Cloud", "detail": "Cloud Run, signed in with the gcloud command"},
    "azure": {"label": "Microsoft Azure", "detail": "Container Apps, signed in with the az command"},
}


# ---- Functions ----

def load():
    """Merge the defaults with the environment."""
    settings = dict(DEFAULTS)
    for key in DEFAULTS:
        from_environment = os.environ.get(ENV_PREFIX + key.upper())
        if from_environment:
            settings[key] = from_environment
    return settings


# ---- Read the settings once, at import ----

SETTINGS = load()
