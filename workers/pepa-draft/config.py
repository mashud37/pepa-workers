import os
from functools import lru_cache
from pathlib import Path

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

ROOT = Path(__file__).resolve().parent
PROJECT = os.environ.get("PEPA_PROJECT")
DATA_ROOT = Path(PROJECT) / "pepa-draft" if PROJECT else ROOT
INSTALLED = ROOT.parent.name == "apps"
COMMAND = "pepa-draft" if INSTALLED else "python manage.py"
REVIEW_COMMAND = "pepa-review" if INSTALLED else "python manage.py"
DATA_DIR = DATA_ROOT / "data"
INPUT_DIR = Path(os.environ.get("PEPADRAFT_INPUT_DIR", str(DATA_ROOT / "input")))
OUTPUT_DIR = Path(os.environ.get("PEPADRAFT_OUTPUT_DIR", str(DATA_ROOT / "output")))
SECRETS_FILE = DATA_ROOT / "secrets.yaml"
SECRETS_EXAMPLE = ROOT / "secrets.example.yaml"
SECTIONS_FILE = DATA_DIR / "sections.json"
STYLE_INDEX_FILE = DATA_DIR / "style_index.json"  # legacy; use style_index_file(profile)
STYLE_ACTIVE_FILE = DATA_DIR / "style_active.txt"
REVIEW_INDEX_DEFAULT = DATA_ROOT.parent / "pepa-review" / "data" / "index.json"

DRAFT_MODEL_DEFAULT = "claude-opus-5-5"
DRAFT_MODEL_BULK = "claude-sonnet-5-5"
EMBED_MODEL_GEMINI = "gemini-embedding-001"
EMBED_MODEL_OLLAMA = "nomic-embed-text"
RETRIEVAL_K = 6
STYLE_K = 3
WORD_COUNT_TOLERANCE = 0.15

SECTION_TARGETS = {
    "introduction": 500,
    "literature_review": 1500,
    "methods": 750,
    "findings": 3000,
    "discussion": 1000,
    "conclusion": 500,
}

_ENV_OVERRIDE = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "anthropic_model": "PEPADRAFT_ANTHROPIC_MODEL",
    "draft_model": "PEPADRAFT_MODEL",
    "gemini_api_key": "GEMINI_API_KEY",
    "ollama_base_url": "PEPADRAFT_OLLAMA_URL",
    "embed_model": "PEPADRAFT_EMBED_MODEL",
    "vllm_base_url": "PEPADRAFT_VLLM_URL",
    "vllm_token": "PEPADRAFT_VLLM_TOKEN",
    "review_index": "PEPADRAFT_REVIEW_INDEX",
    "backend": "PEPADRAFT_BACKEND",
    "llm_base_url": "PEPADRAFT_LLM_BASE_URL",
    "llm_model": "PEPADRAFT_LLM_MODEL",
    "llm_api_key": "PEPA_LLM_API_KEY",
    "embed_provider": "PEPADRAFT_EMBED_PROVIDER",
    "embed_base_url": "PEPADRAFT_EMBED_BASE_URL",
    "embed_api_key": "PEPA_EMBED_API_KEY",
}

DEFAULTS = {
    "anthropic_api_key": "",
    "gemini_api_key": "",
    "ollama_base_url": "http://localhost:11434",
    "vllm_base_url": "",
    "vllm_token": "",
    "backend": "anthropic",
    "embed_provider": "gemini",
}

# `anthropic` calls Claude; `openai-compatible` calls any server that accepts OpenAI's
# chat format (DeepSeek, Kimi, Qwen, Ollama, vLLM) at llm_base_url; `vllm` calls the
# Cloud Run service.
BACKENDS = (
    "anthropic",
    "openai-compatible",
    "vllm",
)

# Each embedding provider's default model, and the setting it cannot run without.
EMBED_DEFAULT_MODELS = {
    "gemini": EMBED_MODEL_GEMINI,
    "ollama": EMBED_MODEL_OLLAMA,
    "openai-compatible": None,
}
EMBED_NEEDS = {
    "gemini": "gemini_api_key",
    "ollama": "ollama_base_url",
    "openai-compatible": "embed_base_url",
}

@lru_cache(maxsize=1)
def _load_secrets() -> dict:
    if not SECRETS_FILE.exists() or not _HAS_YAML:
        return {}
    try:
        with open(SECRETS_FILE, encoding="utf-8") as f:
            data = _yaml.safe_load(f) or {}
        return {k: v for k, v in data.items() if v and str(v) not in ("REPLACE_ME", "")}
    except Exception:
        return {}


def get(key: str, default=None):
    env_var = _ENV_OVERRIDE.get(key)
    if env_var:
        val = os.environ.get(env_var)
        if val:
            return val
    secrets = _load_secrets()
    if key in secrets:
        return secrets[key]
    if default is not None:
        return default
    return DEFAULTS.get(key, default)


def draft_model() -> str:
    return get("draft_model") or get("anthropic_model") or DRAFT_MODEL_DEFAULT


def bulk_model() -> str:
    return DRAFT_MODEL_BULK


def embed_config() -> dict:
    """Return the embedding provider and model the style index uses.

    Returns:
        Dict with keys provider and model, both None when the chosen provider's
        key, address or model is not set.
    """
    provider = get("embed_provider")
    if provider not in EMBED_DEFAULT_MODELS:
        raise SystemExit(f"Unknown embed_provider '{provider}'. Use one of: {', '.join(EMBED_DEFAULT_MODELS)}.")
    model = get("embed_model") or EMBED_DEFAULT_MODELS[provider]
    if not get(EMBED_NEEDS[provider]) or not model:
        return {"provider": None, "model": None}
    return {"provider": provider, "model": model}


def backend() -> str:
    """The generation backend, checked against BACKENDS."""
    chosen = get("backend")
    if chosen not in BACKENDS:
        raise SystemExit(f"Unknown backend '{chosen}'. Use one of: {', '.join(BACKENDS)}.")
    return chosen


def llm_connection() -> dict:
    """The server address, key and model the openai-compatible backend uses."""
    base_url = get("llm_base_url")
    model = get("llm_model")
    if not base_url or not model:
        raise SystemExit(
            "The openai-compatible backend needs llm_base_url and llm_model in secrets.yaml, "
            "or the PEPADRAFT_LLM_BASE_URL and PEPADRAFT_LLM_MODEL variables."
        )
    return {"base_url": base_url, "api_key": get("llm_api_key"), "model": model}


def active_style_profile() -> str:
    if STYLE_ACTIVE_FILE.exists():
        name = STYLE_ACTIVE_FILE.read_text(encoding="utf-8").strip()
        if name:
            return name
    return "default"


def style_index_file(profile: str = None) -> Path:
    name = profile or active_style_profile()
    return DATA_DIR / f"style_{name}.json"


def set_active_style_profile(name: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STYLE_ACTIVE_FILE.write_text(name.strip(), encoding="utf-8")


def list_style_profiles() -> list:
    profiles = []
    for p in sorted(DATA_DIR.glob("style_*.json")):
        if p == STYLE_INDEX_FILE:
            continue
        stem = p.stem  # e.g. style_default
        if stem.startswith("style_"):
            profiles.append(stem[len("style_"):])
    return profiles


def review_index_file() -> Path:
    override = get("review_index")
    if override:
        return Path(override)
    return REVIEW_INDEX_DEFAULT


def set_values(updates: dict) -> None:
    """Write key-value pairs into secrets.yaml without overwriting existing real values.

    Args:
        updates: Dict of key -> value to persist.
    """
    if not _HAS_YAML:
        raise SystemExit("pyyaml is required to write secrets. Run: pip install pyyaml")
    existing = {}
    if SECRETS_FILE.exists():
        with open(SECRETS_FILE, encoding="utf-8") as f:
            existing = _yaml.safe_load(f) or {}
    for k, v in updates.items():
        if not existing.get(k) or existing[k] in ("REPLACE_ME", ""):
            existing[k] = v
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SECRETS_FILE, "w", encoding="utf-8") as f:
        _yaml.safe_dump(existing, f, default_flow_style=False)
    _load_secrets.cache_clear()
