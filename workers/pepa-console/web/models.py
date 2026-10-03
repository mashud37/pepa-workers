"""Keep which model and server each app uses, and hand the choices to its jobs as environment variables.
Apps left on their own settings keep reading their own file.
"""
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from web import keys, paths
from web.settings import SETTINGS

MODELS_FILE_NAME = "models.json"
SERVERS_RECORD = Path("pepa-host") / "data" / "servers.json"
LIST_TIMEOUT_SECONDS = 8
CLOUD_RUN_HOST = ".run.app"
BLANK_GENERATION = {
    "route": "",
    "base_url": "",
    "model": "",
    "quality_model": "",
}
BLANK_EMBEDDING = {
    "provider": "",
    "base_url": "",
    "model": "",
}

# Where a model runs, as the page offers it; every route but Claude is an OpenAI-compatible server.
ROUTES = {
    "claude": {"label": "Claude", "backend": "anthropic", "detail": "Anthropic's models, with a key"},
    "service": {"label": "Another service", "backend": "openai-compatible", "detail": "DeepSeek, Kimi, Qwen and others, with a key"},
    "computer": {"label": "This computer", "backend": "openai-compatible", "detail": "Ollama, LM Studio, vLLM or llama.cpp"},
    "cloud": {"label": "Your own cloud", "backend": "openai-compatible", "detail": "A server you deployed with pepa-host"},
}

# Prices are list prices in US dollars per million tokens, input then output.
CLAUDE_MODELS = [
    {"value": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5", "detail": "Fastest and cheapest · $1 in, $5 out"},
    {"value": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "detail": "Better writing · $2 in, $10 out"},
    {"value": "claude-opus-5-5", "label": "Claude Opus 5.5", "detail": "Strongest · $4 in, $20 out"},
]

# Each app's one or two model slots: what the slot does, the app's own Claude default, and the
# variable the choice arrives in for Claude and for an OpenAI-compatible server.
GENERATION = {
    "pepa-sum": {
        "backend": "PEPA_BACKEND",
        "base_url": "PEPA_LLM_BASE_URL",
        "slots": [
            {"setting": "model", "label": "Model", "help": "Writes every brief and rundown.", "default": "claude-haiku-4-5-20251001", "anthropic": "PEPA_ANTHROPIC_MODEL", "openai-compatible": "PEPA_LLM_MODEL"},
        ],
    },
    "pepa-review": {
        "backend": "PEPAREVIEW_BACKEND",
        "base_url": "PEPAREVIEW_LLM_BASE_URL",
        "slots": [
            {"setting": "model", "label": "Model for the many short steps", "help": "Sorts and labels papers, one small call each.", "default": "claude-haiku-4-5-20251001", "anthropic": "PEPAREVIEW_ANTHROPIC_MODEL", "openai-compatible": "PEPAREVIEW_LLM_MODEL"},
            {"setting": "quality_model", "label": "Model for the writing", "help": "Writes the review, the gap map and the synthesis.", "default": "claude-sonnet-5-5", "anthropic": "PEPAREVIEW_REVIEW_MODEL", "openai-compatible": "PEPAREVIEW_LLM_QUALITY_MODEL"},
        ],
    },
    "pepa-plan": {
        "backend": "PEPAPLAN_BACKEND",
        "base_url": "PEPAPLAN_LLM_BASE_URL",
        "slots": [
            {"setting": "model", "label": "Model for the many short steps", "help": "Labels the moves in every paragraph.", "default": "claude-haiku-4-5-20251001", "anthropic": "PEPAPLAN_ANTHROPIC_MODEL", "openai-compatible": "PEPAPLAN_LLM_MODEL"},
            {"setting": "quality_model", "label": "Model for the writing", "help": "Writes the skeletons and the outline.", "default": "claude-sonnet-5-5", "anthropic": "PEPAPLAN_REVIEW_MODEL", "openai-compatible": "PEPAPLAN_LLM_QUALITY_MODEL"},
        ],
    },
    "pepa-draft": {
        "backend": "PEPADRAFT_BACKEND",
        "base_url": "PEPADRAFT_LLM_BASE_URL",
        "slots": [
            {"setting": "model", "label": "Model", "help": "Writes each section of the draft.", "default": "claude-opus-5-5", "anthropic": "PEPADRAFT_MODEL", "openai-compatible": "PEPADRAFT_LLM_MODEL"},
        ],
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
EMBED_PROVIDERS = [
    {"value": "gemini", "label": "Gemini", "detail": "Google's embeddings, with a key"},
    {"value": "openai-compatible", "label": "OpenAI-compatible server", "detail": "Qwen, Ollama on this computer, and others"},
]

# Addresses offered for each route; any other address works the same way.
ADDRESSES = {
    "service": [
        {"value": "https://api.deepseek.com/v1", "label": "DeepSeek"},
        {"value": "https://api.moonshot.ai/v1", "label": "Kimi (Moonshot)"},
        {"value": "https://api.moonshot.cn/v1", "label": "Kimi (Moonshot, mainland China)"},
        {"value": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "label": "Qwen (Alibaba Model Studio)"},
        {"value": "https://dashscope.aliyuncs.com/compatible-mode/v1", "label": "Qwen (Alibaba Model Studio, mainland China)"},
        {"value": "https://open.bigmodel.cn/api/paas/v4", "label": "GLM (Zhipu)"},
        {"value": "https://api.mistral.ai/v1", "label": "Mistral"},
        {"value": "https://router.huggingface.co/v1", "label": "Hugging Face Inference Providers"},
        {"value": "https://openrouter.ai/api/v1", "label": "OpenRouter"},
        {"value": "https://api.openai.com/v1", "label": "OpenAI"},
        {"value": "https://generativelanguage.googleapis.com/v1beta/openai", "label": "Gemini"},
    ],
    "computer": [
        {"value": "http://localhost:11434/v1", "label": "Ollama"},
        {"value": "http://localhost:1234/v1", "label": "LM Studio"},
        {"value": "http://localhost:8000/v1", "label": "vLLM"},
        {"value": "http://localhost:8080/v1", "label": "llama.cpp server"},
    ],
}
LOCAL_HOSTS = [
    "localhost",
    "127.0.0.1",
]

# What a server deployed with pepa-host can take, handed to the apps that would otherwise send it
# more: its context window and the requests it answers at once.
SERVER_LIMITS = {
    "pepa-sum": {"context_tokens": "PEPA_CONTEXT_TOKENS", "concurrency": "PEPA_MAX_CONCURRENCY"},
    "pepa-plan": {"concurrency": "PEPAPLAN_CONCURRENCY"},
}


# ---- The store ----

def store_file():
    """Where the model choices are kept: beside the key store, outside the workspace."""
    return SETTINGS["keys_file"].parent / MODELS_FILE_NAME


def route_of(saved):
    """The route a saved choice belongs to; a choice saved before routes existed is read from its backend and address."""
    if saved.get("route"):
        return saved["route"]
    if saved.get("backend") == "anthropic":
        return "claude"
    if saved.get("backend") != "openai-compatible":
        return ""
    for host in LOCAL_HOSTS:
        if host in saved.get("base_url", ""):
            return "computer"
    return "service"


def load_store():
    """Every choice made on the Models page, with a blank entry for anything not chosen yet."""
    data = {"generation": {}, "embedding": {}}
    if store_file().exists():
        data = json.loads(store_file().read_text(encoding="utf-8"))
    generation = {}
    for app_name in GENERATION:
        saved = data.get("generation", {}).get(app_name, {})
        generation[app_name] = dict(BLANK_GENERATION)
        for setting in BLANK_GENERATION:
            generation[app_name][setting] = saved.get(setting, "")
        generation[app_name]["route"] = route_of(saved)
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


# ---- Servers deployed with pepa-host ----

def deployed_servers():
    """Every server pepa-host has deployed from the project folder, with its address, model and key."""
    record = paths.project_folder() / SERVERS_RECORD
    if not record.exists():
        return []
    return json.loads(record.read_text(encoding="utf-8")).get("servers", [])


def server_at(base_url):
    """The deployed server at this address, or None for any other server."""
    for server in deployed_servers():
        if server["address"].rstrip("/") == base_url.rstrip("/"):
            return server
    return None


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
        ValueError: an unknown route, or a server choice without address or model.
    """
    store = {"generation": {}, "embedding": {}}
    for app_name, app in GENERATION.items():
        route = form.get(f"{app_name}|route", "").strip()
        if route and route not in ROUTES:
            raise ValueError(f"{app_name} has no route called {route}.")
        field_kind = "claude" if route == "claude" else "server"
        chosen = dict(BLANK_GENERATION)
        chosen["route"] = route
        if route and route != "claude":
            chosen["base_url"] = form.get(f"{app_name}|base_url", "").strip()
        for slot in app["slots"]:
            chosen[slot["setting"]] = form.get(f"{app_name}|{slot['setting']}|{field_kind}", "").strip()
        server = server_at(chosen["base_url"]) if route == "cloud" else None
        if server and not chosen["model"]:
            chosen["model"] = server["model"]
        if route and route != "claude":
            check_server(chosen["base_url"], chosen["model"], app_name)
        if server:
            keys.use_server_key(app_name, f"pepa-host-{server['name']}", server["key"])
        store["generation"][app_name] = chosen

    for setting in BLANK_EMBEDDING:
        store["embedding"][setting] = form.get(f"embedding|{setting}", "").strip()
    provider = store["embedding"]["provider"]
    known = [choice["value"] for choice in EMBED_PROVIDERS]
    if provider and provider not in known:
        raise ValueError(f"There is no embedding provider called {provider}.")
    if provider == "openai-compatible":
        check_server(store["embedding"]["base_url"], store["embedding"]["model"], "Embeddings")
    save_store(store)


# ---- Listing a server's models ----

def server_key(app_name):
    """The key a server lookup sends for this app: the console's environment first, then the key store."""
    variable = "PEPA_EMBED_API_KEY" if app_name == "embedding" else "PEPA_LLM_API_KEY"
    if os.environ.get(variable):
        return os.environ[variable]
    store_app = "pepa-review" if app_name == "embedding" else app_name
    return keys.environment_for(store_app).get(variable, "")


def cloud_run_token():
    """Your Google sign-in from gcloud, which a model on Cloud Run asks for before anything else.

    Raises:
        ValueError: gcloud is missing or not signed in.
    """
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise ValueError("A model on Cloud Run needs the gcloud command, signed in with: gcloud auth login")
    made = subprocess.run([gcloud, "auth", "print-identity-token"], capture_output=True, text=True)
    if made.returncode != 0:
        raise ValueError("gcloud is not signed in. Run: gcloud auth login")
    return made.stdout.strip()


def list_models(app_name, base_url):
    """The model names an OpenAI-compatible server offers, asked from its /models address.

    Raises:
        ValueError: the address is not a web address, or the server refused or did not answer.
    """
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Enter the server address first; it starts with http:// or https://.")
    headers = {}
    key = server_key(app_name)
    server = server_at(base_url)
    if server:
        key = server["key"]
    if key:
        headers["Authorization"] = f"Bearer {key}"
    host = urllib.parse.urlparse(base_url).hostname or ""
    if host.endswith(CLOUD_RUN_HOST):
        headers["X-Serverless-Authorization"] = f"Bearer {cloud_run_token()}"
    request = urllib.request.Request(base_url.rstrip("/") + "/models", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=LIST_TIMEOUT_SECONDS) as reply:
            data = json.loads(reply.read())
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ValueError("The server refused the key. Add it on the Keys page as PEPA_LLM_API_KEY.")
        raise ValueError(f"The server answered with error {error.code}.")
    except (urllib.error.URLError, OSError, ValueError):
        raise ValueError("No answer from that address. Is the server running?")
    names = [entry.get("id", "") for entry in data.get("data", [])]
    return sorted(name for name in names if name)


# ---- What a job receives ----

def generation_variables(app_name, chosen):
    """The variables one app's generation choice sets: its backend, its address, and a model per slot."""
    app = GENERATION[app_name]
    backend = ROUTES[chosen["route"]]["backend"]
    wanted = {app["backend"]: backend}
    if backend == "openai-compatible":
        wanted[app["base_url"]] = chosen["base_url"]
    for slot in app["slots"]:
        if chosen[slot["setting"]]:
            wanted[slot[backend]] = chosen[slot["setting"]]
    server = server_at(chosen["base_url"]) if chosen["route"] == "cloud" else None
    if server:
        for limit, variable in SERVER_LIMITS.get(app_name, {}).items():
            wanted[variable] = str(server[limit])
    return wanted


def environment_for(app_name):
    """The model variables a job of this app receives. A variable already set in the console's
    own environment wins, and an app left on its own settings receives nothing."""
    store = load_store()
    wanted = {}
    if app_name in GENERATION and store["generation"][app_name]["route"]:
        wanted.update(generation_variables(app_name, store["generation"][app_name]))
    if app_name in EMBEDDING and store["embedding"]["provider"]:
        for setting, value in store["embedding"].items():
            if value:
                wanted[EMBEDDING[app_name][setting]] = value

    environment = {}
    for variable, value in wanted.items():
        if value and not os.environ.get(variable):
            environment[variable] = value
    return environment


def page_view():
    """Everything the Models page shows."""
    store = load_store()
    apps = []
    for app_name, app in GENERATION.items():
        apps.append({
            "name": app_name,
            "chosen": store["generation"][app_name],
            "slots": app["slots"],
        })
    addresses = dict(ADDRESSES)
    addresses["cloud"] = []
    for server in deployed_servers():
        addresses["cloud"].append({"value": server["address"], "label": f"{server['name']} · {server['model']}"})
    return {
        "apps": apps,
        "routes": ROUTES,
        "claude_models": CLAUDE_MODELS,
        "addresses": addresses,
        "embedding": store["embedding"],
        "embed_providers": EMBED_PROVIDERS,
        "file": str(store_file()),
    }
