"""Manage plan templates: markdown files in templates/ describing the
sections and paragraphs an outline should follow, copied from
example.plan.md and edited by the user.
"""
import re
import shutil
import sys

import config
from cli import ui

_SUFFIX = ".plan.md"


def list_templates():
    if not config.TEMPLATES_DIR.exists():
        return []
    return sorted(config.TEMPLATES_DIR.glob(f"*{_SUFFIX}"))


def read(path):
    return path.read_text(encoding="utf-8").strip()


def create(name):
    """Copy the example template to templates/<slug>.plan.md and return the path.
    Refuses to overwrite an existing template."""
    config.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    if not config.EXAMPLE_TEMPLATE.exists():
        raise SystemExit(f"Example template missing: {config.EXAMPLE_TEMPLATE}")
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "plan"
    dest = config.TEMPLATES_DIR / f"{slug}{_SUFFIX}"
    if dest.exists():
        raise SystemExit(f"Template already exists: {dest.name}")
    shutil.copyfile(config.EXAMPLE_TEMPLATE, dest)
    return dest


def run(new=None, show=False):
    """CLI entry: --new NAME creates a copy; --list/no args open the manager."""
    ui.header("Plan templates")
    if new:
        dest = create(new)
        ui.ok(f"created {dest.name}")
        ui.info(f"edit it: {dest}")
        ui.info("then run: python manage.py outline --template " + str(dest))
        return 0

    existing = list_templates()
    if show or not sys.stdin.isatty():
        _show_list(existing)
        return 0

    while True:
        options = [(p.name, "") for p in existing] + [("Create new template", "copy the example")]
        choice = ui.menu("Templates", options)
        if choice is None:
            return 0
        if choice == len(existing):
            name = ui.ask("Template name")
            if not name:
                continue
            dest = create(name)
            ui.ok(f"created {dest.name}")
            ui.info(f"edit it: {dest}")
            existing = list_templates()
        else:
            path = existing[choice]
            ui.step(path.name)
            ui.info(str(path))
            for line in read(path).splitlines()[:12]:
                print(f"  {line}")


def _show_list(existing):
    if not existing:
        ui.warn("no templates yet, create one with: python manage.py template --new <name>")
        return
    ui.step("Templates")
    for p in existing:
        ui.info(p.name)
