"""Keep the run settings chosen on each app's page and hand them to its jobs as environment variables.
A blank setting is not sent; the app reads its own file.
"""
import json
import os

from web.settings import SETTINGS

OPTIONS_FILE_NAME = "options.json"

# Each app's settings: the environment variable it arrives in, its label, and either the
# values it takes or the lowest and highest number it accepts.
OPTIONS = {
    "pepa-prep": [
        {"variable": "PEPAPREP_WORKERS", "label": "PDFs read at once", "low": 1, "high": 16},
        {"variable": "PEPAPREP_OCR_DPI", "label": "Scan resolution (dpi)", "low": 72, "high": 600},
        {"variable": "PEPAPREP_BOOK_PAGES", "label": "Pages that make a book", "low": 20, "high": 2000},
        {"variable": "PEPAPREP_MAX_CHAPTERS", "label": "Most chapters per book", "low": 1, "high": 500},
    ],
    "pepa-sum": [
        {"variable": "PEPA_SPEED", "label": "Speed", "choices": ["eco", "balanced", "turbo"]},
        {"variable": "PEPA_MODE", "label": "Run mode", "choices": ["auto", "serial", "parallel", "batch"]},
        {"variable": "PEPA_PARA_METHOD", "label": "Paragraph rundown", "choices": ["llm", "extractive"]},
        {"variable": "PEPA_ON_EXISTING", "label": "Papers already done", "choices": ["ask", "skip", "overwrite"]},
        {"variable": "PEPA_OCR", "label": "Scanned pages", "choices": ["auto", "off", "force"]},
        {"variable": "PEPA_OCR_DPI", "label": "Scan resolution (dpi)", "low": 72, "high": 400},
        {"variable": "PEPA_CONTEXT_TOKENS", "label": "Model context (tokens)", "low": 16384, "high": 2000000},
    ],
    "pepa-review": [
        {"variable": "PEPAREVIEW_USE_BIBLIO", "label": "Use the bibliography database", "choices": ["yes", "no"]},
    ],
    "pepa-plan": [
        {"variable": "PEPAPLAN_MODE", "label": "Run mode", "choices": ["auto", "serial", "parallel", "batch"]},
        {"variable": "PEPAPLAN_CONCURRENCY", "label": "Requests at once", "low": 1, "high": 32},
    ],
}


# ---- The store ----

def store_file():
    """Where the run settings are kept: beside the key store, outside the workspace."""
    return SETTINGS["keys_file"].parent / OPTIONS_FILE_NAME


def load_store():
    """Every value chosen so far, as {app: {variable: value}}; a setting never chosen is absent."""
    if not store_file().exists():
        return {}
    return json.loads(store_file().read_text(encoding="utf-8"))


def save_store(store):
    """Write the store through a temporary file, so a crash never leaves half a file behind."""
    path = store_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(store, indent=2), encoding="utf-8")
    os.replace(temporary, path)


# ---- Saving one app's card ----

def checked_value(option, value):
    """The value as it is stored, after checking it is one the setting accepts.

    Raises:
        ValueError: a value outside the setting's choices or range.
    """
    if "choices" in option:
        if value not in option["choices"]:
            raise ValueError(f"{option['label']}: choose one of {', '.join(option['choices'])}.")
        return value
    if not value.isdigit() or not option["low"] <= int(value) <= option["high"]:
        raise ValueError(f"{option['label']}: give a whole number from {option['low']} to {option['high']}.")
    return value


def save_choices(app_name, form):
    """Check and store one app's settings card; a blank field leaves that setting to the app's own file.

    Raises:
        ValueError: the app has no settings, or a value the setting does not accept.
    """
    if app_name not in OPTIONS:
        raise ValueError(f"{app_name} has no settings here.")
    chosen = {}
    for option in OPTIONS[app_name]:
        value = form.get(option["variable"], "").strip()
        if value:
            chosen[option["variable"]] = checked_value(option, value)
    store = load_store()
    store[app_name] = chosen
    save_store(store)


# ---- What a job receives ----

def environment_for(app_name):
    """The settings a job of this app receives. A variable already set in the console's own environment wins."""
    environment = {}
    for variable, value in load_store().get(app_name, {}).items():
        if not os.environ.get(variable):
            environment[variable] = value
    return environment


def card_view(app_name):
    """The settings card on an app's page: each setting with the value chosen, or none for an app without settings."""
    chosen = load_store().get(app_name, {})
    fields = []
    for option in OPTIONS.get(app_name, []):
        field = dict(option)
        field["value"] = chosen.get(option["variable"], "")
        fields.append(field)
    return fields
