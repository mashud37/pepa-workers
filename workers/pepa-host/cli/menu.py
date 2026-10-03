"""Show the interactive menu when manage.py runs with no arguments. Loops until closed, and every
action returns here when it finishes or fails.
"""
from cli import deploy, install, servers, ui

_ACTIONS = [
    ("Deploy", "put a model server on Google Cloud or Azure", deploy.run),
    ("Servers", "list the deployed servers", servers.list_servers),
    ("Remove", "delete a deployed server", servers.remove_server),
    ("Install", "check which hosts are ready", install.run),
]


def main():
    ui.header("pepa-host")
    while True:
        choice = ui.menu("Action", [(label, detail) for label, detail, _ in _ACTIONS])
        if choice is None:
            return 0
        ui.run_action(_ACTIONS[choice][2])
