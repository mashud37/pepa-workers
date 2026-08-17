import os
from functools import lru_cache
from pathlib import Path

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
SECRETS_FILE = ROOT / "secrets.yaml"
SECRETS_EXAMPLE = ROOT / "secrets.example.yaml"
SECTIONS_FILE = DATA_DIR / "sections.json"
STYLE_INDEX_FILE = DATA_DIR / "style_index.json"  # legacy; use style_index_file(profile)
STYLE_ACTIVE_FILE = DATA_DIR / "style_active.txt"
REVIEW_INDEX_DEFAULT = ROOT.parent / "pepa-review" / "data" / "index.json"

DRAFT_MODEL_DEFAULT = "claude-opus-4-8"
DRAFT_MODEL_BULK = "claude-sonnet-4-6"
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
}

DEFAULTS = {
    "anthropic_api_key": "",
    "gemini_api_key": "",
    "ollama_base_url": "http://localhost:11434",
    "vllm_base_url": "",
    "vllm_token": "",
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
    """Return the active embedding backend settings.

    Returns:
        Dict with keys provider and model, both None if unconfigured.
    """
    model_override = get("embed_model")
    if get("gemini_api_key"):
        return {"provider": "gemini", "model": model_override or EMBED_MODEL_GEMINI}
    base = get("ollama_base_url")
    if base:
        return {"provider": "ollama", "model": model_override or EMBED_MODEL_OLLAMA}
    return {"provider": None, "model": None}


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
