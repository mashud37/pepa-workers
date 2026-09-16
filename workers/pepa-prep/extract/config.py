import os
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _ROOT / "config.yaml"
_SECRETS_PATH = _ROOT / "secrets.yaml"

_DEFAULT: dict = {
    "input_folder": "./input",
    "output_folder": "./output",
    "scan_subfolders": False,
    "workers": 4,
    "book_page_threshold": 100,
    "max_chapters": 80,
    "toc_headings": ["contents", "table of contents", "inhalt", "inhaltsverzeichnis"],
    "ocr_dpi": 300,
    "tesseract_cmd": "",
    "refine_snap_lines": 0,
    "refine_unit_slack": 1,
    # Bibliography enrichment (python manage.py biblio)
    "biblio_corpus": "../pepa-sum/output",
    "biblio_output": "./output",
    "biblio_zotero": "",
    "openalex_email": "",
}


# Folder settings an environment variable may override, so a launcher can point
# this app at the user's own folders without editing config.yaml.
_FOLDER_ENV = {
    "input_folder": "PEPAPREP_INPUT_DIR",
    "output_folder": "PEPAPREP_OUTPUT_DIR",
}

# Whether the input folder's own sub-folders are searched too, as an environment
# variable, so a launcher can turn it on without editing config.yaml.
_SUBFOLDERS_ENV = "PEPAPREP_SUBFOLDERS"
_YES_WORDS = ("1", "true", "yes", "on")


def load() -> dict:
    cfg = dict(_DEFAULT)
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cfg.update(data)
    for key, env_var in _FOLDER_ENV.items():
        if os.environ.get(env_var):
            cfg[key] = os.environ[env_var]
    wanted = os.environ.get(_SUBFOLDERS_ENV, "")
    if wanted:
        cfg["scan_subfolders"] = wanted.lower() in _YES_WORDS
    return cfg


def save(cfg: dict) -> None:
    with _CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


def openalex_api_key() -> str:
    """Optional OpenAlex premium key: OPENALEX_API_KEY env var wins over secrets.yaml."""
    if os.environ.get("OPENALEX_API_KEY"):
        return os.environ["OPENALEX_API_KEY"]
    if not _SECRETS_PATH.exists():
        return ""
    secrets = yaml.safe_load(_SECRETS_PATH.read_text(encoding="utf-8")) or {}
    key = secrets.get("openalex_api_key", "")
    return key if key and not key.startswith("<") else ""
