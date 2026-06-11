"""Interactive menu shown when manage.py is run with no arguments.

Mirrors the subcommands one-to-one, ordered by frequency of use."""
from cli import ui, summarize, install, show_config, deploy

_ACTIONS = [
    ("Summarise papers", "read input/, write output/", summarize.run),
    ("Show config", "paths, endpoint, costs", show_config.run),
    ("Deploy service", "build + deploy to Cloud Run", deploy.run),
    ("Install / setup", "env.yaml, token, dependency checks", install.run),
]


def main():
    while True:
        choice = ui.menu("pepa-sum", [(label, desc) for label, desc, _ in _ACTIONS])
        if choice is None:
            return 0
        _ACTIONS[choice][2]()
