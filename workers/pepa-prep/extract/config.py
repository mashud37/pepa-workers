import os
import shutil
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
_PROJECT = os.environ.get("PEPA_PROJECT")
DATA_ROOT = Path(_PROJECT) / "pepa-prep" if _PROJECT else _ROOT
_CONFIG_PATH = DATA_ROOT / "config.yaml"
_SECRETS_PATH = DATA_ROOT / "secrets.yaml"

# The evaluation harness and its gold data live only in the source repository.
EVALUATION_SHIPPED = (_ROOT / "evaluate").is_dir()

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


# Where the Windows installer puts Tesseract, which it does not add to PATH.
_WINDOWS_TESSERACT = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR" / "tesseract.exe"

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

# Folder settings written as relative paths are read from the data root, not from
# wherever the command happens to be started.
_FOLDER_KEYS = [
    "input_folder",
    "output_folder",
    "biblio_corpus",
    "biblio_output",
]


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
    for key in _FOLDER_KEYS:
        folder = Path(cfg[key])
        if not folder.is_absolute():
            cfg[key] = str((DATA_ROOT / folder).resolve())
    return cfg


def save(cfg: dict) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
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


def tesseract_path(cfg: dict) -> str:
    """The Tesseract program to run: the configured one, then the one on PATH, then the Windows default."""
    if cfg.get("tesseract_cmd"):
        return cfg["tesseract_cmd"]
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    if _WINDOWS_TESSERACT.exists():
        return str(_WINDOWS_TESSERACT)
    return ""
