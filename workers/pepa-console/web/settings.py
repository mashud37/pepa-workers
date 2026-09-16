"""Hold the web console's settings in one dictionary, read once at import from the defaults
and the environment. The web modules import SETTINGS.
"""
import os
from pathlib import Path

# ---- Defaults ----
# PEPA_CONSOLE_<KEY> in the environment overrides each of these.

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 5190,
    "read_port": 5151,
    "upload_limit_mb": 500,
    "poll_ms": 700,
}

ALLOWED = {
    "host": [
        "127.0.0.1",
        "localhost",
    ],
}

NUMERIC = [
    "port",
    "read_port",
    "upload_limit_mb",
    "poll_ms",
]

ENV_PREFIX = "PEPA_CONSOLE_"
KEYS_FOLDER = "pepa-workers"
KEYS_FILE_NAME = "keys.json"


# ---- Functions ----

def load():
    """Merge the defaults with the environment and check the result, so a bad value fails
    at start rather than on the first request."""
    settings = dict(DEFAULTS)
    for key in DEFAULTS:
        from_environment = os.environ.get(ENV_PREFIX + key.upper())
        if from_environment:
            settings[key] = from_environment

    for key in NUMERIC:
        settings[key] = int(settings[key])

    for key, options in ALLOWED.items():
        if settings[key] not in options:
            raise SystemExit(f"Setting '{key}' must be one of {options}, not '{settings[key]}'.")

    appdata = os.environ.get("APPDATA")
    if appdata:
        keys_folder = Path(appdata) / KEYS_FOLDER
    else:
        keys_folder = Path.home() / ".config" / KEYS_FOLDER
    settings["keys_file"] = Path(os.environ.get(ENV_PREFIX + "KEYS_FILE") or keys_folder / KEYS_FILE_NAME)
    return settings


# ---- Read the settings once, at import ----

SETTINGS = load()
