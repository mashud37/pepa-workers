import config
from cli import ui

_ACTIONS = [
    ("Build skeletons",      "learn paragraph structures from pepa-sum corpus", "abstract"),
    ("Build blueprints",     "within-section paragraph progression per skeleton move", "blueprint"),
    ("Outline a paper",      "idea → template/skeleton → paragraph-by-paragraph plan", "outline"),
    ("Plan templates",       "create/edit your own section/paragraph progressions", "templates"),
    ("Review argumentation", "argumentation-flow feedback on idea or draft", "review"),
    ("Show config",          "paths, models, skeleton library status", "show_config"),
    ("Install / setup",      "create secrets.yaml, check deps", "install"),
]


def _run(module_name: str) -> None:
    from importlib import import_module
    import_module(f"cli.{module_name}").run()


def main():
    ui.header("pepa-plan")
    _status()

    while True:
        choice = ui.menu("Main menu", [(label, desc) for label, desc, _ in _ACTIONS])
        if choice is None:
            return 0
        ui.run_action(_run, _ACTIONS[choice][2])


def _status():
    try:
        from corpus.load import paper_count
        count = paper_count()
        ui.info(f"corpus: {count} para files  |  {config.load()['corpus_dir'].name}/")
    except Exception:
        ui.warn("corpus not found, run Install / setup to check paths")

    if config.SKELETONS_FILE.exists():
        import json
        lib = json.loads(config.SKELETONS_FILE.read_text(encoding="utf-8"))
        n = len(lib.get("skeletons", []))
        ui.info(f"skeletons: {n} in library")
    else:
        ui.warn("no skeleton library yet, choose 'Build skeletons'")

    if config.BLUEPRINTS_FILE.exists():
        import json
        bp = json.loads(config.BLUEPRINTS_FILE.read_text(encoding="utf-8"))
        m = sum(len(moves) for moves in bp.get("blueprints", {}).values())
        ui.info(f"blueprints: {m} within-section move guides")
