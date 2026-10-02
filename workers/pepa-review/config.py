"""Resolve effective configuration (CORPUS_DIR, embeddings, LLM model
IDs, I/O paths) with precedence: environment variable, then secrets.yaml,
then a built-in default.
"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
PROJECT = os.environ.get("PEPA_PROJECT")
DATA_ROOT = Path(PROJECT) / "pepa-review" if PROJECT else ROOT
INSTALLED = ROOT.parent.name == "apps"
COMMAND = "pepa-review" if INSTALLED else "python manage.py"
CORPUS_DIR_DEFAULT = DATA_ROOT.parent / "pepa-sum" / "output"
DATA_DIR = DATA_ROOT / "data"
INPUT_DIR = Path(os.environ.get("PEPAREVIEW_INPUT_DIR", str(DATA_ROOT / "input")))
OUTPUT_DIR = Path(os.environ.get("PEPAREVIEW_OUTPUT_DIR", str(DATA_ROOT / "output")))
SECRETS_FILE = DATA_ROOT / "secrets.yaml"
SECRETS_EXAMPLE = ROOT / "secrets.example.yaml"
INDEX_FILE = DATA_DIR / "index.json"
BIBLIO_DB  = DATA_DIR / "biblio.db"

# Minimum match_confidence to include a works row in authority/coupling signals
BIBLIO_MIN_CONFIDENCE = 0.7
# Cosine threshold for coupling-graph edges (shared-reference adjacency)
BIBLIO_COUPLING_THRESHOLD = 2       # min shared references to form a coupling edge
# Weight of the citation feature channel when added to map.py (Phase 3)
MAP_WEIGHT_CITATION = 0.15
# Review biblio anchoring: anchors are top-tercile cited_by_count AND older-half year;
# each anchor pairs with its nearest newer-half works (by embedding) as interlocutors.
BIBLIO_ANCHOR_CITE_PCTL = 0.66      # citation percentile at/above which a work may anchor
BIBLIO_INTERLOCUTOR_TOPN = 2        # newer works paired to each anchor

# Gap-check (WS2): hybrid hits retrieved per draft paragraph
GAPS_PARA_K = 5

# Literature review (WS1)
REVIEW_CANDIDATE_K = 40             # broad candidate pool retrieved for the outline
REVIEW_SECTIONS_MIN = 3            # synthesised-structure section band
REVIEW_SECTIONS_MAX = 4

# Cap on concurrent LLM calls for per-section/per-thread fan-out
LLM_MAX_WORKERS = 4

GENERATION_MODEL_DEFAULT = "claude-haiku-4-5-20251001"
GENERATION_MODEL_QUALITY = "claude-sonnet-5-5"
EMBED_MODEL_GEMINI = "gemini-embedding-001"
EMBED_MODEL_OLLAMA = "nomic-embed-text"

# Corpus-map clustering (WS4): UMAP -> consensus -> c-TF-IDF
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

# Thread-level map (WS5): re-cluster the works of one thread at finer granularity
MAP_SUB_MIN_THREADS = 2        # band floor when re-clustering a single thread's works
MAP_SUB_MAX_THREADS = 12       # band ceiling for the sub-clustering sweep

_ENV_OVERRIDE = {
    "corpus_dir":       "PEPAREVIEW_CORPUS_DIR",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "anthropic_model":  "PEPAREVIEW_ANTHROPIC_MODEL",
    "review_model":     "PEPAREVIEW_REVIEW_MODEL",
    "gemini_api_key":   "GEMINI_API_KEY",
    "ollama_base_url":  "PEPAREVIEW_OLLAMA_URL",
    "embed_model":      "PEPAREVIEW_EMBED_MODEL",
    "use_biblio":       "PEPAREVIEW_USE_BIBLIO",
    "backend":          "PEPAREVIEW_BACKEND",
    "llm_base_url":     "PEPAREVIEW_LLM_BASE_URL",
    "llm_model":        "PEPAREVIEW_LLM_MODEL",
    "llm_quality_model": "PEPAREVIEW_LLM_QUALITY_MODEL",
    "llm_api_key":      "PEPA_LLM_API_KEY",
    "embed_provider":   "PEPAREVIEW_EMBED_PROVIDER",
    "embed_base_url":   "PEPAREVIEW_EMBED_BASE_URL",
    "embed_api_key":    "PEPA_EMBED_API_KEY",
}

_PLACEHOLDERS = {"", "REPLACE_ME", "changeme"}

DEFAULTS = {
    "corpus_dir": CORPUS_DIR_DEFAULT,
    "anthropic_api_key": None,
    "anthropic_model": GENERATION_MODEL_DEFAULT,
    "review_model": GENERATION_MODEL_QUALITY,
    "gemini_api_key": None,
    "ollama_base_url": "http://localhost:11434",
    "backend": "anthropic",
    "embed_provider": "gemini",
}

# `anthropic` calls Claude; `openai-compatible` calls any server that accepts OpenAI's
# chat format (DeepSeek, Kimi, Qwen, Ollama, vLLM) at llm_base_url.
BACKENDS = (
    "anthropic",
    "openai-compatible",
)

# Each embedding provider's default model, and the setting it cannot run without.
EMBED_DEFAULT_MODELS = {
    "gemini": EMBED_MODEL_GEMINI,
    "ollama": EMBED_MODEL_OLLAMA,
    "openai-compatible": None,
}
EMBED_MISSING = (
    "No embedding provider configured. Set embed_provider in secrets.yaml (gemini, ollama, "
    "or openai-compatible) and its key or address: gemini_api_key, ollama_base_url, or "
    "embed_base_url with embed_model."
)
EMBED_NEEDS = {
    "gemini": "gemini_api_key",
    "ollama": "ollama_base_url",
    "openai-compatible": "embed_base_url",
}


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


def setting(name):
    """Read one named config value: env var, then secrets.yaml, then DEFAULTS."""
    return get(name, DEFAULTS.get(name))


def corpus_dir():
    return Path(setting("corpus_dir"))


def embed_config():
    """Return the embedding provider and model to use.

    Returns:
        dict with keys "provider" and "model", both None when the chosen
        provider's key, address or model is not set.
    """
    provider = setting("embed_provider")
    if provider not in EMBED_DEFAULT_MODELS:
        raise SystemExit(f"Unknown embed_provider '{provider}'. Use one of: {', '.join(EMBED_DEFAULT_MODELS)}.")
    model = get("embed_model", EMBED_DEFAULT_MODELS[provider])
    if not setting(EMBED_NEEDS[provider]) or not model:
        return {"provider": None, "model": None}
    return {"provider": provider, "model": model}


def backend():
    """The generation backend, checked against BACKENDS."""
    chosen = setting("backend")
    if chosen not in BACKENDS:
        raise SystemExit(f"Unknown backend '{chosen}'. Use one of: {', '.join(BACKENDS)}.")
    return chosen


def llm_connection():
    """The server address, key and models the openai-compatible backend uses."""
    base_url = setting("llm_base_url")
    model = setting("llm_model")
    if not base_url or not model:
        raise SystemExit(
            "The openai-compatible backend needs llm_base_url and llm_model in secrets.yaml, "
            "or the PEPAREVIEW_LLM_BASE_URL and PEPAREVIEW_LLM_MODEL variables."
        )
    return {
        "base_url": base_url,
        "api_key": setting("llm_api_key"),
        "model": model,
        "quality_model": get("llm_quality_model", model),
    }


def model_names():
    """The fast and the quality model the configured backend generates with."""
    if backend() == "openai-compatible":
        model = setting("llm_model")
        return {"fast": model, "quality": get("llm_quality_model", model)}
    return {"fast": setting("anthropic_model"), "quality": setting("review_model")}


def use_biblio():
    """True when bibliographic enrichment is enabled and biblio.db exists."""
    raw = get("use_biblio", "false")
    return str(raw).lower() in ("1", "true", "yes") and BIBLIO_DB.exists()


def set_values(updates):
    """Persist values into secrets.yaml, preserving everything else."""
    data = _secrets()
    data.update(updates)
    SECRETS_FILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
