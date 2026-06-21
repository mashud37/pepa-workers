from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _ROOT / "config.yaml"

_DEFAULT: dict = {
    "input_folder": "./input",
    "output_folder": "./output",
    "workers": 4,
    "book_page_threshold": 100,
    "max_chapters": 80,
    "ocr_dpi": 300,
    "tesseract_cmd": "",
    # Bibliography enrichment (python manage.py biblio)
    "biblio_corpus": "../pepa-sum/output",
    "biblio_output": "./output",
    "biblio_zotero": "",
    "crossref_email": "",
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
