import config
from cli import ui


def main():
    ui.header("pepa-plan")
    _status()

    while True:
        choice = ui.menu("Main menu", [
            ("Build skeletons",        "learn paragraph structures from pepa-sum corpus"),
            ("Outline a paper",        "idea → skeleton → paragraph-by-paragraph plan"),
            ("Review argumentation",   "argumentation-flow feedback on idea or draft"),
            ("Show config",            "paths, models, skeleton library status"),
            ("Install / setup",        "create secrets.yaml, check deps"),
        ])

        if choice is None:
            break
        elif choice == 0:
            from cli import abstract
            abstract.run()
        elif choice == 1:
            from cli import outline
            outline.run()
        elif choice == 2:
            from cli import review
            review.run()
        elif choice == 3:
            from cli import show_config
            show_config.run()
        elif choice == 4:
            from cli import install
            install.run()


def _status():
    try:
        from corpus.load import paper_count
        count = paper_count()
        ui.info(f"corpus: {count} para files  |  {config.corpus_dir().name}/")
    except Exception:
        ui.warn("corpus not found — run Install / setup to check paths")

    if config.SKELETONS_FILE.exists():
        import json
        lib = json.loads(config.SKELETONS_FILE.read_text(encoding="utf-8"))
        n = len(lib.get("skeletons", []))
        ui.info(f"skeletons: {n} in library")
    else:
        ui.warn("no skeleton library yet — choose 'Build skeletons'")
