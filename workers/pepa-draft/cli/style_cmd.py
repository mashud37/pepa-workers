"""Manage author writing samples for style matching."""
import config
from cli import ui


def _add(file_path: str) -> None:
    from pathlib import Path

    from cli.progress import StepSpinner
    from index.style import build

    if not file_path:
        file_path = ui.ask("Path to writing sample file")
    if not file_path:
        return
    p = Path(file_path)
    if not p.exists():
        ui.abort(f"file not found: {p}")
    sp = StepSpinner("indexing sample")
    sp.start()
    try:
        total = build([p])
    finally:
        sp.done(f"{total} paragraphs indexed")
    ui.ok(f"indexed {p.name}")


def _list() -> None:
    from index.style import list_samples
    samples = list_samples()
    if not samples:
        ui.info("no style samples indexed — use 'add' to index a writing sample")
        return
    ui.info(f"{len(samples)} sample file(s):")
    for s in samples:
        ui.info(f"  {s}")


def _build_all() -> None:
    from cli.progress import StepSpinner
    from index.style import build

    candidates = list(config.INPUT_DIR.glob("*.txt")) + list(config.INPUT_DIR.glob("*.md"))
    if not candidates:
        ui.warn("no .txt or .md files in input/ to index as style samples")
        return
    ui.info(f"indexing {len(candidates)} file(s)...")
    sp = StepSpinner("building style index")
    sp.start()
    try:
        total = build(candidates, force=True)
    finally:
        sp.done(f"{total} paragraphs")
    ui.ok("style index rebuilt")


_ACTION_MAP = {
    "add": _add,
    "list": lambda _: _list(),
    "build": lambda _: _build_all(),
    "remove": lambda _: ui.warn("remove: delete the file from input/ and rebuild the index"),
}

_MENU_ACTIONS = [_add, lambda: _list(), lambda: _build_all()]


def run(action: str = None, file_path: str = None) -> None:
    ui.header("pepa-draft — author style")
    if action is None:
        choice = ui.menu("Style samples", [
            ("Add sample",  "Index a writing sample file"),
            ("List samples", "Show all indexed sample files"),
            ("Build index", "Rebuild style index from all samples"),
        ])
        if choice is not None:
            _MENU_ACTIONS[choice](file_path) if choice == 0 else _MENU_ACTIONS[choice]()
        return
    handler = _ACTION_MAP.get(action)
    if handler:
        handler(file_path)
