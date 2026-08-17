"""Show the interactive menu for pepa-draft, looping until closed; every
action returns here when it finishes or fails.
"""
from cli import ui


def _run_draft():
    from cli import draft_cmd
    draft_cmd.run()


def _run_sections():
    from cli import sections_cmd
    sections_cmd.run()


def _run_style():
    from cli import style_cmd
    style_cmd.run()


def _run_config():
    from cli import config_cmd
    config_cmd.run()


def _run_setup():
    from cli import setup_cmd
    setup_cmd.run()


def _run_install():
    from cli import install
    install.run()


_ACTIONS = [_run_draft, _run_sections, _run_style, _run_config, _run_setup, _run_install]


def main():
    while True:
        choice = ui.menu("pepa-draft", [
            ("Draft",    "Write a full manuscript draft"),
            ("Sections", "Assign plan paragraphs to sections"),
            ("Style",    "Manage author writing samples"),
            ("Config",   "Show effective configuration"),
            ("Setup",    "Configure API keys and paths"),
            ("Install",  "Set up files and check dependencies"),
        ])
        if choice is None:
            break
        ui.run_action(_ACTIONS[choice])
