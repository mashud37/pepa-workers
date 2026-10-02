"""Show effective configuration."""
import json

import config
from cli import ui


def run():
    ui.header("Configuration")
    _show_corpus()
    _show_models()
    _show_api_keys()
    _show_index()
    _show_biblio()
    _show_paths()


def _show_corpus():
    ui.step("Corpus")
    d = config.corpus_dir()
    ui.info(f"corpus_dir:  {d}")
    try:
        from cli import progress
        from corpus.load import paper_count
        sp = progress.StepSpinner("scanning corpus")
        sp.start()
        count = paper_count()
        sp.done()
        ui.info(f"papers:      {count}")
    except Exception as e:
        ui.warn(f"could not count papers: {e}")


def _show_models():
    ui.step("Models")
    ui.info(f"generation (fast):    {config.setting('anthropic_model')}")
    ui.info(f"generation (quality): {config.setting('review_model')}")
    embed = config.embed_config()
    if embed["provider"]:
        ui.info(f"embeddings:           {embed['provider']}/{embed['model']}")
    else:
        ui.warn("embeddings:           not configured (add gemini_api_key or ollama_base_url)")


def _show_api_keys():
    ui.step("API keys")
    ui.info(f"anthropic_api_key: {'set' if config.setting('anthropic_api_key') else 'unset'}")
    ui.info(f"gemini_api_key:    {'set' if config.setting('gemini_api_key') else 'unset'}")
    ollama_url = config.setting("ollama_base_url")
    if ollama_url:
        ui.info(f"ollama_base_url:   {ollama_url}")


def _show_index():
    ui.step("Index")
    if config.INDEX_FILE.exists():
        idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
        ui.ok(
            f"index present: {len(idx.get('records', []))} records, "
            f"provider={idx.get('provider','?')}, model={idx.get('model','?')}"
        )
    else:
        ui.warn("no index yet, run: python manage.py index")


def _show_biblio():
    ui.step("Bibliographic enrichment")
    ui.info(f"use_biblio: {'on' if config.use_biblio() else 'off'}")
    if config.BIBLIO_DB.exists():
        from biblio.store import stats
        s = stats()
        if s:
            ui.ok(
                f"biblio.db: {s['works']} works, "
                f"{s['internal_edges']} internal citation edges"
            )
        else:
            ui.info("biblio.db present but empty")
    else:
        ui.info("biblio.db absent, run: python manage.py biblio ingest")


def _show_paths():
    ui.step("Paths")
    ui.info(f"data/:   {config.DATA_DIR}")
    ui.info(f"input/:  {config.INPUT_DIR}")
    ui.info(f"output/: {config.OUTPUT_DIR}")
