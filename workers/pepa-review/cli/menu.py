"""Interactive menu — the bare `python manage.py` entry point."""
import config
from cli import ui


def main():
    ui.header("pepa-review")
    _corpus_status()

    while True:
        choice = ui.menu("Main menu", [
            ("Literature review",    "assemble a review from selected works"),
            ("Gap-check a draft",    "find missed/underused works in your draft"),
            ("Explore literature",   "interactive discovery over the corpus"),
            ("Corpus map",           "cluster works into thematic threads, write report"),
            ("Build / refresh index","embed all sum_ briefs into the retrieval index"),
            ("Show config",          "paths, models, index status"),
            ("Install / setup",      "create secrets.yaml, check deps"),
        ])

        if choice is None:
            break
        elif choice == 0:
            from cli import review
            review.run()
        elif choice == 1:
            from cli import gaps
            gaps.run()
        elif choice == 2:
            from cli import explore
            explore.run()
        elif choice == 3:
            from cli import map as map_cmd
            map_cmd.run()
        elif choice == 4:
            from cli import index_cmd
            index_cmd.run()
        elif choice == 5:
            from cli import show_config
            show_config.run()
        elif choice == 6:
            from cli import install
            install.run()


def _corpus_status():
    try:
        from corpus.load import paper_count
        count = paper_count()
        ui.info(f"corpus: {count} papers  |  {config.corpus_dir().name}/")
    except Exception:
        ui.warn("corpus not found — run Install / setup to check paths")
    if config.INDEX_FILE.exists():
        import json
        try:
            idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
            ui.info(f"index:  {len(idx.get('records', []))} records  ({idx.get('provider','?')})")
        except Exception:
            pass
    else:
        ui.warn("no index yet — choose 'Build / refresh index'")
