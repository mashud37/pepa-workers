"""Interactive menu shown when manage.py is run with no arguments.

Mirrors the subcommands one-to-one, ordered by frequency of use."""
from cli import ui, summarize, settings, install, show_config, deploy

_ACTIONS = [
    ("Summarise papers", "read input/, write sum_/para_/quote_ to output/", summarize.run),
    ("Settings", "backend + paragraph-rundown method", settings.run),
    ("Show config", "backend, model, costs", show_config.run),
    ("Install / setup", "env.yaml, API key, dependency checks", install.run),
    ("Deploy service", "build + deploy the self-hosted fallback", deploy.run),
]


def main():
    while True:
        choice = ui.menu("pepa-sum", [(label, desc) for label, desc, _ in _ACTIONS])
        if choice is None:
            return 0
        _ACTIONS[choice][2]()
