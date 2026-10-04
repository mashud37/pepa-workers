"""Show the interactive menu when manage.py runs with no arguments, looping
until closed; every action returns here when it finishes or fails.
"""
from cli import batches, cleanup, install, settings, show_config, summarize, ui

_ACTIONS = [
    ("Summarise papers", "read input/, write sum_/para_/quote_ to output/", summarize.run),
    ("Check batches", "batches sent to Anthropic; write the papers of those that ended", batches.run),
    ("Clean failed outputs", "delete sum_ files missing the template + their pairs", cleanup.run),
    ("Settings", "backend + paragraph-rundown method", settings.run),
    ("Show config", "backend, model, costs", show_config.run),
    ("Install / setup", "env.yaml, API key, dependency checks", install.run),
]


def main():
    while True:
        choice = ui.menu("pepa-sum", [(label, desc) for label, desc, _ in _ACTIONS])
        if choice is None:
            return 0
        ui.run_action(_ACTIONS[choice][2])
