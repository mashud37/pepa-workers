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
    models = config.model_names()
    ui.info(f"backend:              {config.backend()}")
    if config.backend() == "openai-compatible":
        ui.info(f"server:               {config.setting('llm_base_url') or 'missing'}")
    ui.info(f"generation (fast):    {models['fast'] or 'missing'}")
    ui.info(f"generation (quality): {models['quality'] or 'missing'}")
    embed = config.embed_config()
    if embed["provider"]:
        ui.info(f"embeddings:           {embed['provider']}/{embed['model']}")
    else:
        ui.warn(f"embeddings:           {config.setting('embed_provider')}, not configured")


def _show_api_keys():
    ui.step("API keys and servers")
    ui.info(f"anthropic_api_key: {'set' if config.setting('anthropic_api_key') else 'unset'}")
    ui.info(f"llm_api_key:       {'set' if config.setting('llm_api_key') else 'unset'}")
    ui.info(f"gemini_api_key:    {'set' if config.setting('gemini_api_key') else 'unset'}")
    ui.info(f"embed_api_key:     {'set' if config.setting('embed_api_key') else 'unset'}")
    if config.setting("embed_provider") == "ollama":
        ui.info(f"ollama_base_url:   {config.setting('ollama_base_url')}")
    if config.setting("embed_provider") == "openai-compatible":
        ui.info(f"embed_base_url:    {config.setting('embed_base_url') or 'missing'}")


def _show_index():
    ui.step("Index")
    if config.INDEX_FILE.exists():
        idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
        ui.ok(
            f"index present: {len(idx.get('records', []))} records, "
            f"provider={idx.get('provider','?')}, model={idx.get('model','?')}"
        )
    else:
        ui.warn(f"no index yet, run: {config.COMMAND} index")


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
        ui.info(f"biblio.db absent, run: {config.COMMAND} biblio ingest")


def _show_paths():
    ui.step("Paths")
    ui.info(f"data/:   {config.DATA_DIR}")
    ui.info(f"input/:  {config.INPUT_DIR}")
    ui.info(f"output/: {config.OUTPUT_DIR}")
