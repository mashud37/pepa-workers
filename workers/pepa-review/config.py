"""Effective configuration: CORPUS_DIR, embeddings, LLM model IDs, I/O paths.

Precedence for every value: environment variable -> secrets.yaml -> built-in default.
secrets.yaml is gitignored; only secrets.example.yaml is committed.
"""
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
INDEX_FILE = DATA_DIR / "index.json"
GRAPH_FILE = DATA_DIR / "graph.json"

GENERATION_MODEL_DEFAULT = "claude-haiku-4-5-20251001"
GENERATION_MODEL_QUALITY = "claude-sonnet-4-6"
EMBED_MODEL_GEMINI = "gemini-embedding-001"
EMBED_MODEL_OLLAMA = "nomic-embed-text"

# Corpus-map clustering (WS4) — UMAP -> consensus -> c-TF-IDF
MAP_UMAP_DIM = 10
MAP_MIN_THREADS = 6            # thread-count band floor (silhouette is swept within the band)
MAP_MAX_THREADS = 40           # thread-count band ceiling
MAP_WEIGHT_DENSE = 0.6
MAP_WEIGHT_TITLE = 0.2
MAP_WEIGHT_LITERATURE = 0.2
MAP_OUTLIER_THRESHOLD = 0.15   # min co-association to best thread; below -> cross-cutting/outlier
MAP_MULTI_MARGIN = 0.8         # second thread listed if its profile >= margin * best
MAP_MERGE_SIM = 0.9            # centroid cosine above which two threads may merge
MAP_MERGE_TERM_J = 0.5         # plus top-term Jaccard above which two threads merge

_ENV_OVERRIDE = {
    "corpus_dir":       "PEPAREVIEW_CORPUS_DIR",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "anthropic_model":  "PEPAREVIEW_ANTHROPIC_MODEL",
    "review_model":     "PEPAREVIEW_REVIEW_MODEL",
    "gemini_api_key":   "GEMINI_API_KEY",
    "ollama_base_url":  "PEPAREVIEW_OLLAMA_URL",
    "embed_model":      "PEPAREVIEW_EMBED_MODEL",
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


def gemini_api_key():
    return get("gemini_api_key")


def ollama_base_url():
    return get("ollama_base_url")


def embed_config():
    """Return (provider, model) or (None, None) if no embeddings configured."""
    if ollama_base_url():
        return ("ollama", get("embed_model", EMBED_MODEL_OLLAMA))
    if gemini_api_key():
        return ("gemini", get("embed_model", EMBED_MODEL_GEMINI))
    return (None, None)


def set_values(updates):
    """Persist values into secrets.yaml, preserving everything else."""
    data = _secrets()
    data.update(updates)
    SECRETS_FILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
