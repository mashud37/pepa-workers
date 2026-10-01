"""Show the interactive menu at the bare `python manage.py` entry point,
looping until closed; actions return here when they finish or fail.
"""
from cli import ui


def _run(module_name: str) -> None:
    from importlib import import_module
    import_module(f"cli.{module_name}").run()


_ACTIONS = [
    ("Literature review",     "assemble a review from selected works",
     lambda: _run("review")),
    ("Gap-check a draft",     "find missed/underused works in your draft",
     lambda: _run("gaps")),
    ("Explore literature",    "interactive discovery over the corpus",
     lambda: _run("explore")),
    ("Corpus map",            "cluster works into thematic threads, write report",
     lambda: _run("map")),
    ("Thread-level map",      "re-cluster one thread of a saved map in detail",
     lambda: _run("thread_map")),
    ("Build / refresh index", "embed all sum_ briefs into the retrieval index",
     lambda: _run("index_cmd")),
    ("Bibliographic data",    "ingest DOIs/refs, export document reference, citation graph",
     lambda: _biblio_menu()),
    ("Show config",           "paths, models, index status",
     lambda: _run("show_config")),
    ("Install / setup",       "create secrets.yaml, check deps",
     lambda: _run("install")),
]


def main():
    ui.header("pepa-review")
    while True:
        choice = ui.menu("Main menu", [(label, desc) for label, desc, _ in _ACTIONS])
        if choice is None:
            return 0
        ui.run_action(_ACTIONS[choice][2])


def _biblio_menu():
    from cli import biblio_cmd
    actions = [
        ("Stats",          "summary counts for biblio.db",
         lambda: biblio_cmd.run("stats")),
        ("Export CSVs",    "write works.csv + citations.csv to output/",
         lambda: biblio_cmd.run("export")),
        ("Citation graph", "directed corpus→corpus citation network (HTML/GraphML)",
         lambda: biblio_cmd.run("network", {"graph_type": "citation", "fmt": "html"})),
        ("Coupling graph", "bibliographic coupling network (shared references)",
         lambda: biblio_cmd.run("network", {"graph_type": "coupling", "fmt": "html"})),
        ("Ingest data",    "load upstream works/citations file into biblio.db",
         lambda: biblio_cmd.run("ingest")),
    ]
    while True:
        sub = ui.menu("Bibliographic data", [(label, desc) for label, desc, _ in actions])
        if sub is None:
            return
        ui.run_action(actions[sub][2])
