"""Build or refresh the embedding index (backbone shared by all workstreams)."""
import config
from cli import ui, progress


def run(force=False):
    ui.header("Build / refresh index")

    provider, model = config.embed_config()
    if not provider:
        raise SystemExit(
            "No embedding provider configured.\n"
            "Add gemini_api_key to secrets.yaml or set the GEMINI_API_KEY env var.\n"
            "Run: python manage.py install"
        )

    from corpus.load import paper_count
    total = paper_count()
    ui.info(f"corpus: {total} papers")
    ui.info(f"embed:  {provider}/{model}")
    if force:
        ui.warn("--force: rebuilding index from scratch")
    elif config.INDEX_FILE.exists():
        import json
        existing = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
        done = len(existing.get("records", []))
        ui.info(f"already indexed: {done} papers; will embed {total - done} new ones")

    sp = progress.StepSpinner("indexing")
    sp.start()

    def on_progress(i, total_, label):
        sp._label = f"[{i}/{total_}] {label[:18]}"

    try:
        from index.store import build_index
        n, model_used = build_index(force=force, progress_cb=on_progress)
        sp.done(f"{n} records")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    ui.ok(f"index ready: {n} records, {model_used}")
