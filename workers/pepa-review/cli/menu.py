"""Interactive menu — the bare `python manage.py` entry point."""
from cli import ui


def main():
    ui.header("pepa-review")

    while True:
        choice = ui.menu("Main menu", [
            ("Literature review",    "assemble a review from selected works"),
            ("Gap-check a draft",    "find missed/underused works in your draft"),
            ("Explore literature",   "interactive discovery over the corpus"),
            ("Corpus map",           "cluster works into thematic threads, write report"),
            ("Thread-level map",     "re-cluster one thread of a saved map in detail"),
            ("Build / refresh index","embed all sum_ briefs into the retrieval index"),
            ("Bibliographic data",   "ingest DOIs/refs, export document reference, citation graph"),
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
            from cli import thread_map
            thread_map.run()
        elif choice == 5:
            from cli import index_cmd
            index_cmd.run()
        elif choice == 6:
            _biblio_menu()
        elif choice == 7:
            from cli import show_config
            show_config.run()
        elif choice == 8:
            from cli import install
            install.run()


def _biblio_menu():
    from cli import biblio_cmd
    while True:
        sub = ui.menu("Bibliographic data", [
            ("Stats",           "summary counts for biblio.db"),
            ("Export CSVs",     "write works.csv + citations.csv to output/"),
            ("Citation graph",  "directed corpus→corpus citation network (HTML/GraphML)"),
            ("Coupling graph",  "bibliographic coupling network (shared references)"),
            ("Ingest data",     "load upstream works/citations file into biblio.db"),
        ])
        if sub is None:
            break
        elif sub == 0:
            biblio_cmd.run("stats")
        elif sub == 1:
            biblio_cmd.run("export")
        elif sub == 2:
            biblio_cmd.run("network", graph_type="citation", fmt="html")
        elif sub == 3:
            biblio_cmd.run("network", graph_type="coupling", fmt="html")
        elif sub == 4:
            biblio_cmd.run("ingest")
