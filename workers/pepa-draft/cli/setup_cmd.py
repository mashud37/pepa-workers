"""Configure keys interactively and write the values to secrets.yaml.
"""
import config
from cli import ui

_KEYS = [
    ("anthropic_api_key", "Anthropic API key", True),
    ("gemini_api_key", "Gemini API key (embeddings; skip if using Ollama)", False),
    ("ollama_base_url", "Ollama base URL (embeddings; skip if using Gemini)", False),
    ("vllm_base_url", "vLLM Cloud Run URL (skip if using Anthropic only)", False),
    ("vllm_token", "vLLM auth token (skip if no vLLM URL)", False),
    ("review_index", "Path to pepa-review index.json (skip to use default)", False),
]


def _prompt_key(key: str, label: str, required: bool) -> str | None:
    current = config.get(key)
    if current and len(current) >= 8:
        masked = current[:4] + "..." + current[-4:]
    else:
        masked = "not set"
    if current:
        hint = f"current: {masked}"
    elif required:
        hint = "required"
    else:
        hint = "optional, skip to leave blank"
    value = ui.ask(f"{label} [{hint}]")
    if not value and current:
        return None
    if not value and required:
        ui.warn(f"{label} is required, leaving blank, set it manually in secrets.yaml")
        return None
    return value or None


def run() -> None:
    ui.header("pepa-draft: setup")
    ui.info("Configure API keys and paths. Existing values are not overwritten.")

    updates = {}
    for key, label, required in _KEYS:
        value = _prompt_key(key, label, required)
        if value:
            updates[key] = value

    if not updates:
        ui.info("no changes: all keys already set or skipped")
        return

    try:
        config.set_values(updates)
        ui.ok(f"saved {len(updates)} key(s) to secrets.yaml")
    except SystemExit as e:
        ui.error(str(e))
