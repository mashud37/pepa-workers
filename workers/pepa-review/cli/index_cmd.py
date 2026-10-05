"""Build or refresh the embedding index (backbone shared by all workstreams)."""
from functools import partial

import config
from cli import progress, ui


def _report_embed_progress(sp, i, total, _label):
    sp._label = f"embedding [{i}/{total}]"


def _report_status(sp, msg):
    sp._label = msg


def run(force=False):
    ui.header("Build / refresh index")

    embed = config.embed_config()
    provider = embed["provider"]
    model = embed["model"]
    if not provider:
        raise SystemExit(config.EMBED_MISSING)

    scan = progress.StepSpinner("scanning corpus")
    scan.start()
    from corpus.load import paper_count
    total = paper_count()
    scan.done(f"{total} papers")
    ui.info(f"embed:  {provider}/{model}")
    if force:
        ui.warn("--force: rebuilding index from scratch")
    elif config.INDEX_FILE.exists():
        import json
        existing = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
        done = len(existing["records"])
        ui.info(f"already indexed: {done} papers; will embed {total - done} new ones")

    sp = progress.StepSpinner("indexing")
    sp.start()

    try:
        from index.store import build_index
        result = build_index(
            force=force,
            progress_cb=partial(_report_embed_progress, sp),
            status_cb=partial(_report_status, sp),
        )
        sp.done(f"{result['n_records']} records")
    except BaseException as e:
        sp.done("error")
        raise SystemExit(str(e)) from None

    ui.ok(f"index ready: {result['n_records']} records, {result['model_used']}")
