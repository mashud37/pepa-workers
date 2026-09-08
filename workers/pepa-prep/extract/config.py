import os
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _ROOT / "config.yaml"
_SECRETS_PATH = _ROOT / "secrets.yaml"

_DEFAULT: dict = {
    "input_folder": "./input",
    "output_folder": "./output",
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


def load() -> dict:
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {**_DEFAULT, **data}
    return dict(_DEFAULT)


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
