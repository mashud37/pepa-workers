"""Keep which model and server each app uses, and hand the choices to its jobs as environment variables.
Apps left on their own file keep reading their own settings.
"""
import json
import os

from web.settings import SETTINGS

MODELS_FILE_NAME = "models.json"
BLANK_GENERATION = {
    "backend": "",
    "base_url": "",
    "model": "",
    "quality_model": "",
}
BLANK_EMBEDDING = {
    "provider": "",
    "base_url": "",
    "model": "",
}

BACKEND_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai-compatible": "OpenAI-compatible server (experimental)",
}

# Each app's backends, and the environment variable each of its settings arrives in.
GENERATION = {
    "pepa-sum": {
        "backends": ["anthropic", "openai-compatible"],
        "backend": "PEPA_BACKEND",
        "base_url": "PEPA_LLM_BASE_URL",
        "model": "PEPA_LLM_MODEL",
        "quality_model": "",
    },
    "pepa-review": {
        "backends": ["anthropic", "openai-compatible"],
        "backend": "PEPAREVIEW_BACKEND",
        "base_url": "PEPAREVIEW_LLM_BASE_URL",
        "model": "PEPAREVIEW_LLM_MODEL",
        "quality_model": "PEPAREVIEW_LLM_QUALITY_MODEL",
    },
    "pepa-plan": {
        "backends": ["anthropic", "openai-compatible"],
        "backend": "PEPAPLAN_BACKEND",
        "base_url": "PEPAPLAN_LLM_BASE_URL",
        "model": "PEPAPLAN_LLM_MODEL",
        "quality_model": "PEPAPLAN_LLM_QUALITY_MODEL",
    },
    "pepa-draft": {
        "backends": ["anthropic", "openai-compatible"],
        "backend": "PEPADRAFT_BACKEND",
        "base_url": "PEPADRAFT_LLM_BASE_URL",
        "model": "PEPADRAFT_LLM_MODEL",
        "quality_model": "",
    },
}

# pepa-draft searches pepa-review's index, so both embed with the one choice made here.
EMBEDDING = {
    "pepa-review": {
        "provider": "PEPAREVIEW_EMBED_PROVIDER",
        "base_url": "PEPAREVIEW_EMBED_BASE_URL",
        "model": "PEPAREVIEW_EMBED_MODEL",
    },
    "pepa-draft": {
        "provider": "PEPADRAFT_EMBED_PROVIDER",
        "base_url": "PEPADRAFT_EMBED_BASE_URL",
        "model": "PEPADRAFT_EMBED_MODEL",
    },
}
EMBED_PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openai-compatible": "OpenAI-compatible server",
}

# Addresses offered as suggestions; any other address works the same way.
ADDRESSES = [
    {"name": "DeepSeek", "url": "https://api.deepseek.com/v1"},
    {"name": "Kimi (Moonshot)", "url": "https://api.moonshot.ai/v1"},
    {"name": "Kimi (Moonshot, mainland China)", "url": "https://api.moonshot.cn/v1"},
    {"name": "Qwen (Alibaba Model Studio)", "url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"},
    {"name": "Qwen (Alibaba Model Studio, mainland China)", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    {"name": "GLM (Zhipu)", "url": "https://open.bigmodel.cn/api/paas/v4"},
    {"name": "Mistral", "url": "https://api.mistral.ai/v1"},
    {"name": "Hugging Face Inference Providers", "url": "https://router.huggingface.co/v1"},
    {"name": "OpenRouter", "url": "https://openrouter.ai/api/v1"},
    {"name": "OpenAI", "url": "https://api.openai.com/v1"},
    {"name": "Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    {"name": "Ollama on this computer", "url": "http://localhost:11434/v1"},
    {"name": "LM Studio on this computer", "url": "http://localhost:1234/v1"},
    {"name": "vLLM on this computer", "url": "http://localhost:8000/v1"},
    {"name": "llama.cpp server on this computer", "url": "http://localhost:8080/v1"},
]


# ---- The store ----

def store_file():
    """Where the model choices are kept: beside the key store, outside the workspace."""
    return SETTINGS["keys_file"].parent / MODELS_FILE_NAME


def load_store():
    """Every choice made on the Models page, with a blank entry for anything not chosen yet."""
    data = {"generation": {}, "embedding": {}}
    if store_file().exists():
        data = json.loads(store_file().read_text(encoding="utf-8"))
    generation = {}
    for app_name in GENERATION:
        generation[app_name] = dict(BLANK_GENERATION)
        generation[app_name].update(data.get("generation", {}).get(app_name, {}))
    embedding = dict(BLANK_EMBEDDING)
    embedding.update(data.get("embedding", {}))
    return {"generation": generation, "embedding": embedding}


def save_store(store):
    """Write the store through a temporary file, so a crash never leaves half a file behind."""
    path = store_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(store, indent=2), encoding="utf-8")
    os.replace(temporary, path)


# ---- Saving the page ----

def check_server(base_url, model, what):
    """Refuse an OpenAI-compatible choice without a web address and a model name.

    Raises:
        ValueError: the address is missing or not a web address, or the model is missing.
    """
    if not base_url.startswith(("http://", "https://")):
        raise ValueError(f"{what}: the server address must start with http:// or https://.")
    if not model:
        raise ValueError(f"{what}: name the model the server should use.")


def save_choices(form):
    """Check and store the Models page form, whose fields are named `app|setting` and `embedding|setting`.

    Raises:
        ValueError: a backend the app does not offer, or an OpenAI-compatible choice without address or model.
    """
    store = {"generation": {}, "embedding": {}}
    for app_name, app in GENERATION.items():
        chosen = {}
        for setting in BLANK_GENERATION:
            chosen[setting] = form.get(f"{app_name}|{setting}", "").strip()
        if chosen["backend"] and chosen["backend"] not in app["backends"]:
            raise ValueError(f"{app_name} has no backend called {chosen['backend']}.")
        if chosen["backend"] == "openai-compatible":
            check_server(chosen["base_url"], chosen["model"], app_name)
        store["generation"][app_name] = chosen

    for setting in BLANK_EMBEDDING:
        store["embedding"][setting] = form.get(f"embedding|{setting}", "").strip()
    provider = store["embedding"]["provider"]
    if provider and provider not in EMBED_PROVIDER_LABELS:
        raise ValueError(f"There is no embedding provider called {provider}.")
    if provider == "openai-compatible":
        check_server(store["embedding"]["base_url"], store["embedding"]["model"], "Embeddings")
    save_store(store)


# ---- What a job receives ----

def environment_for(app_name):
    """The model variables a job of this app receives. A variable already set in the console's
    own environment wins, and an app left on its own file receives nothing."""
    store = load_store()
    wanted = {}
    if app_name in GENERATION and store["generation"][app_name]["backend"]:
        chosen = store["generation"][app_name]
        for setting in BLANK_GENERATION:
            variable = GENERATION[app_name][setting]
            if variable and chosen[setting]:
                wanted[variable] = chosen[setting]
    if app_name in EMBEDDING and store["embedding"]["provider"]:
        for setting, value in store["embedding"].items():
            if value:
                wanted[EMBEDDING[app_name][setting]] = value

    environment = {}
    for variable, value in wanted.items():
        if not os.environ.get(variable):
            environment[variable] = value
    return environment


def page_view():
    """Everything the Models page shows."""
    store = load_store()
    apps = []
    for app_name, app in GENERATION.items():
        options = []
        for backend in app["backends"]:
            options.append({"value": backend, "label": BACKEND_LABELS[backend]})
        apps.append({
            "name": app_name,
            "options": options,
            "chosen": store["generation"][app_name],
            "has_quality": bool(app["quality_model"]),
        })
    return {
        "apps": apps,
        "embedding": store["embedding"],
        "embed_providers": EMBED_PROVIDER_LABELS,
        "addresses": ADDRESSES,
        "file": str(store_file()),
    }
