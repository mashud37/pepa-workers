"""Manage author writing samples for style matching."""
import config
from cli import ui


def _add(file_path: str, profile: str = None) -> None:
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
    name = profile or config.active_style_profile()
    sp = StepSpinner(f"indexing sample into profile '{name}'")
    sp.start()
    total = 0
    try:
        total = build([p], profile=name)
    finally:
        sp.done(f"{total} paragraphs indexed")
    ui.ok(f"indexed {p.name} → profile '{name}'")


def _list(profile: str = None) -> None:
    from index.style import list_samples
    name = profile or config.active_style_profile()
    samples = list_samples(name)
    ui.info(f"profile '{name}':")
    if not samples:
        ui.info("  no style samples indexed, use 'add' to index a writing sample")
        return
    ui.info(f"  {len(samples)} sample file(s):")
    for s in samples:
        ui.info(f"    {s}")


def _build_all(profile: str = None) -> None:
    from cli.progress import StepSpinner
    from index.style import build

    name = profile or config.active_style_profile()
    candidates = list(config.INPUT_DIR.glob("*.txt")) + list(config.INPUT_DIR.glob("*.md"))
    if not candidates:
        ui.warn("no .txt or .md files in input/ to index as style samples")
        return
    ui.info(f"indexing {len(candidates)} file(s) into profile '{name}'...")
    sp = StepSpinner("building style index")
    sp.start()
    total = 0
    try:
        total = build(candidates, force=True, profile=name)
    finally:
        sp.done(f"{total} paragraphs")
    ui.ok(f"style index rebuilt for profile '{name}'")


def _switch(name: str = None) -> None:
    profiles = config.list_style_profiles()
    if not name:
        if not profiles:
            ui.warn("no profiles found, add samples first")
            return
        choices = [(p, f"Switch to profile '{p}'") for p in profiles]
        idx = ui.menu("Switch active profile", choices)
        if idx is None:
            return
        name = profiles[idx]
    config.set_active_style_profile(name)
    ui.ok(f"active style profile → '{name}'")


def _list_profiles() -> None:
    profiles = config.list_style_profiles()
    active = config.active_style_profile()
    if not profiles:
        ui.info("no profiles found, add samples to create one")
        return
    ui.info(f"{len(profiles)} profile(s)  (active: '{active}'):")
    for p in profiles:
        marker = " ◀ active" if p == active else ""
        ui.info(f"  {p}{marker}")


_ACTION_MAP = {
    "add":           lambda file_path, profile: _add(file_path, profile),
    "list":          lambda file_path, profile: _list(profile),
    "build":         lambda file_path, profile: _build_all(profile),
    "switch":        lambda file_path, profile: _switch(profile or file_path),
    "list-profiles": lambda file_path, profile: _list_profiles(),
    "remove":        lambda file_path, profile: ui.warn("remove: delete the file from input/ and rebuild the index"),
}


def run(action: str = None, file_path: str = None, profile: str = None) -> None:
    ui.header("pepa-draft: author style")
    active = config.active_style_profile()
    ui.info(f"active profile: '{active}'")
    if action is None:
        menu_actions = [
            lambda: _add(file_path, profile),
            lambda: _list(profile),
            lambda: _build_all(profile),
            lambda: _switch(profile),
            _list_profiles,
        ]
        while True:
            choice = ui.menu("Style samples", [
                ("Add sample",      "Index a writing sample file into the active profile"),
                ("List samples",    "Show indexed sample files for the active profile"),
                ("Build index",     "Rebuild style index for the active profile"),
                ("Switch profile",  "Change the active author style profile"),
                ("List profiles",   "Show all available author style profiles"),
            ])
            if choice is None:
                return
            ui.run_action(menu_actions[choice])
    handler = _ACTION_MAP.get(action)
    if handler:
        handler(file_path, profile)
