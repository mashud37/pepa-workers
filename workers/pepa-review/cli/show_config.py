"""Show effective configuration."""
import json
import config
from cli import ui


def run():
    ui.header("Configuration")

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

    ui.step("Models")
    ui.info(f"generation (fast):    {config.anthropic_model()}")
    ui.info(f"generation (quality): {config.review_model()}")
    provider, model = config.embed_config()
    if provider:
        ui.info(f"embeddings:           {provider}/{model}")
    else:
        ui.warn("embeddings:           not configured (add gemini_api_key or ollama_base_url)")

    ui.step("API keys")
    ui.info(f"anthropic_api_key: {'set' if config.anthropic_api_key() else 'unset'}")
    ui.info(f"gemini_api_key:    {'set' if config.gemini_api_key() else 'unset'}")
    if config.ollama_base_url():
        ui.info(f"ollama_base_url:   {config.ollama_base_url()}")

    ui.step("Index")
    if config.INDEX_FILE.exists():
        idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
        ui.ok(
            f"index present: {len(idx.get('records', []))} records, "
            f"provider={idx.get('provider','?')}, model={idx.get('model','?')}"
        )
    else:
        ui.warn("no index yet — run: python manage.py index")

    ui.step("Graph")
    if config.GRAPH_FILE.exists():
        g = json.loads(config.GRAPH_FILE.read_text(encoding="utf-8"))
        n_clusters = len({nd.get("cluster", 0) for nd in g.get("nodes", [])})
        ui.ok(
            f"graph present: {len(g.get('nodes',[]))} nodes, "
            f"{len(g.get('edges',[]))} edges, {n_clusters} clusters"
        )
    else:
        ui.info("no graph yet — run: python manage.py graph")

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
        ui.info("biblio.db absent — run: python manage.py biblio ingest")

    ui.step("Paths")
    ui.info(f"data/:   {config.DATA_DIR}")
    ui.info(f"input/:  {config.INPUT_DIR}")
    ui.info(f"output/: {config.OUTPUT_DIR}")
