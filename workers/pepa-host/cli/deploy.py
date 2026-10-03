"""Deploy a model server to the chosen host with a fresh key, and record its address so any worker can use it.
The console runs this as pepa-host's deploy job.
"""
import secrets

from cli import servers, ui
from settings import COMMAND, HOSTS, SERVERS, SERVERS_FILE


def choose(what, options, given):
    """The option named on the command line, or the one picked from a menu."""
    if given:
        if given not in options:
            raise SystemExit(f"No {what} called {given}; choose one of {', '.join(options)}.")
        return given
    names = list(options)
    picked = ui.menu(what.capitalize(), [(options[name]["label"], options[name]["detail"]) for name in names])
    if picked is None:
        raise SystemExit(f"No {what} chosen.")
    return names[picked]


def run(host_name=None, server_name=None):
    """Ask for the host and the server, deploy it, and keep its address, model and key."""
    ui.header("Deploy a model server")
    host_name = choose("host", HOSTS, host_name)
    server_name = choose("server", SERVERS, server_name)
    host = servers.HOST_MODULES[host_name]
    host.check()

    for number, name in enumerate(host.STEPS, 1):
        ui.info(f"{number}/{len(host.STEPS)}  {name}")
    place = host.choose_place()
    if not ui.confirm(f"Deploy the {server_name} server to {place}? It is charged while it runs", default_yes=False):
        raise SystemExit("Nothing deployed.")

    key = secrets.token_hex(32)
    placed = host.deploy(server_name, place, key)
    record = {
        "name": f"{server_name}-{host_name}",
        "server": server_name,
        "host": host_name,
        "model": SERVERS[server_name]["model"],
        "context_tokens": SERVERS[server_name][host_name]["context_tokens"],
        "concurrency": SERVERS[server_name][host_name]["concurrency"],
        "key": key,
    }
    record.update(placed)
    servers.keep_record(record)

    ui.ok(f"{record['name']} runs at {record['address']}")
    ui.info(f"Model: {record['model']}  ·  its key is in {SERVERS_FILE}")
    ui.info("On the console's Models page, choose Your own cloud and pick this server.")
    ui.info(f"Remove it with: {COMMAND} remove {record['name']}")
    return 0
