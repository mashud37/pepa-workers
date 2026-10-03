"""Check which hosts this computer can deploy to: each needs its own command installed and signed in."""
from cli import servers, ui
from settings import HOSTS


def run():
    ui.step("Check the hosts")
    ready = 0
    for name, host in HOSTS.items():
        try:
            servers.HOST_MODULES[name].check()
        except SystemExit as problem:
            ui.warn(f"{host['label']}: {problem}")
            continue
        ui.ok(f"{host['label']}: ready")
        ready += 1
    if ready == 0:
        ui.info("Install and sign in to one host's command to deploy a server there.")
    return 0
