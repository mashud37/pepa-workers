"""Keep API keys in one store outside the workspace and decide which key each app receives.
Jobs get their assigned keys as environment variables; unassigned apps read their own file.
"""
import json
import os

from registry import APPS, get_app
from web.settings import SETTINGS

NAME_SEPARATORS = [
    "-",
    "_",
]


def key_variables():
    """Every key variable at least one app reads, sorted."""
    variables = set()
    for app in APPS:
        variables.update(app.keys)
    return sorted(variables)


def load_store():
    """The key store, or an empty one when the file does not exist yet."""
    path = SETTINGS["keys_file"]
    if not path.exists():
        return {"keys": {}, "assign": {}}
    store = json.loads(path.read_text(encoding="utf-8"))
    store.setdefault("keys", {})
    store.setdefault("assign", {})
    return store


def save_store(store):
    """Write the store through a temporary file, so a crash never leaves half a file behind."""
    path = SETTINGS["keys_file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(store, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def add_key(name, variable, value, everywhere):
    """Store a key under a name, replacing any key already stored under it.

    Args:
        everywhere: also give the key to every app that reads this variable and has none yet.

    Raises:
        ValueError: the name, variable, or value is not usable.
    """
    name = name.strip()
    plain_name = name
    for separator in NAME_SEPARATORS:
        plain_name = plain_name.replace(separator, "")
    if not plain_name.isalnum():
        raise ValueError("A key name uses letters, digits, hyphens and underscores only.")
    if variable not in key_variables():
        raise ValueError(f"No app reads {variable}.")
    if not value.strip():
        raise ValueError("The key value is empty.")

    store = load_store()
    store["keys"][name] = {"variable": variable, "value": value.strip()}
    if everywhere:
        for app in APPS:
            if variable not in app.keys:
                continue
            chosen = store["assign"].setdefault(app.name, {})
            if variable not in chosen:
                chosen[variable] = name
    save_store(store)


def delete_key(name):
    """Remove a key and every assignment that pointed at it."""
    store = load_store()
    store["keys"].pop(name, None)
    for chosen in store["assign"].values():
        for variable in list(chosen):
            if chosen[variable] == name:
                del chosen[variable]
    save_store(store)


def save_assignments(choices):
    """Replace every assignment with the submitted choices; an empty key means the app's own file.

    Args:
        choices: one dictionary per app and variable, with "app", "variable", and "key".

    Raises:
        ValueError: a choice names an unknown app or variable, or a key stored for another variable.
    """
    store = load_store()
    assign = {}
    for choice in choices:
        app = get_app(choice["app"])
        if app is None or choice["variable"] not in app.keys:
            raise ValueError(f"{choice['app']} does not read {choice['variable']}.")
        if not choice["key"]:
            continue
        stored = store["keys"].get(choice["key"])
        if stored is None or stored["variable"] != choice["variable"]:
            raise ValueError(f"Key {choice['key']} is not stored for {choice['variable']}.")
        chosen = assign.setdefault(choice["app"], {})
        chosen[choice["variable"]] = choice["key"]
    store["assign"] = assign
    save_store(store)


def environment_for(app_name):
    """The environment variables a job of this app receives from the store."""
    store = load_store()
    environment = {}
    for variable, key_name in store["assign"].get(app_name, {}).items():
        stored = store["keys"].get(key_name)
        if stored is not None:
            environment[variable] = stored["value"]
    return environment


def sources_for(app_name):
    """Where each key an app reads comes from: a stored key's name, or empty for its own file."""
    chosen = load_store()["assign"].get(app_name, {})
    rows = []
    for variable in get_app(app_name).keys:
        rows.append({"variable": variable, "key": chosen.get(variable, "")})
    return rows


def page_view():
    """Everything the key manager page shows, with no key value anywhere in it."""
    store = load_store()
    stored_keys = []
    for name, stored in sorted(store["keys"].items()):
        users = [app_name for app_name, chosen in store["assign"].items() if name in chosen.values()]
        stored_keys.append({"name": name, "variable": stored["variable"], "used_by": users})

    apps = []
    for app in APPS:
        if not app.keys:
            continue
        chosen = store["assign"].get(app.name, {})
        rows = []
        for variable in app.keys:
            options = [row["name"] for row in stored_keys if row["variable"] == variable]
            rows.append({"variable": variable, "chosen": chosen.get(variable, ""), "options": options})
        apps.append({"name": app.name, "rows": rows})

    return {
        "file": str(SETTINGS["keys_file"]),
        "stored": stored_keys,
        "apps": apps,
        "variables": key_variables(),
    }
