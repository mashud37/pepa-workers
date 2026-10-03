"""Keep the record of every deployed server, with its address and key, and list or remove them.
The console's Models page reads the same record.
"""
import json
import os

from cli import ui
from hosts import azure, gcloud
from settings import HOSTS, SERVERS_FILE

HOST_MODULES = {
    "gcloud": gcloud,
    "azure": azure,
}
OWNER_ONLY = 0o600


def load_records():
    """Every server deployed from this project folder, oldest first."""
    if not SERVERS_FILE.exists():
        return []
    return json.loads(SERVERS_FILE.read_text(encoding="utf-8")).get("servers", [])


def save_records(records):
    """Write the record through a temporary file that only this user may read, since it holds keys."""
    SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SERVERS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"servers": records}, indent=2), encoding="utf-8")
    temporary.chmod(OWNER_ONLY)
    os.replace(temporary, SERVERS_FILE)


def keep_record(record):
    """Store a deployed server, replacing an earlier record of the same name."""
    records = [old for old in load_records() if old["name"] != record["name"]]
    records.append(record)
    save_records(records)


def list_servers():
    """Print every deployed server; the keys stay in the record file."""
    ui.step("Servers")
    records = load_records()
    if not records:
        ui.info("No server deployed yet.")
        return 0
    rows = []
    for record in records:
        rows.append({
            "name": record["name"],
            "host": HOSTS[record["host"]]["label"],
            "model": record["model"],
            "address": record["address"],
        })
    ui.table(rows, ["name", "host", "model", "address"])
    ui.info(f"Keys are in {SERVERS_FILE}")
    return 0


def choose_record(records, name):
    """The record named on the command line, or the one picked from a list."""
    if name:
        for record in records:
            if record["name"] == name:
                return record
        raise SystemExit(f"No server called {name}.")
    options = [(record["name"], record["address"]) for record in records]
    picked = ui.menu("Server to remove", options)
    if picked is None:
        raise SystemExit("Nothing removed.")
    return records[picked]


def remove_server(name=None):
    """Delete one server from its host after its name is typed back, then drop it from the record.
    On Azure, the last server's removal offers to delete the registry too, since it is charged daily."""
    ui.step("Remove a server")
    records = load_records()
    if not records:
        raise SystemExit("No server deployed yet.")
    record = choose_record(records, name)
    typed = (ui.ask(f"Type {record['name']} to delete it") or "").strip()
    if typed != record["name"]:
        raise SystemExit("Nothing removed.")

    HOST_MODULES[record["host"]].remove(record)
    remaining = [other for other in records if other["name"] != record["name"]]
    save_records(remaining)
    ui.ok(f"Removed {record['name']}")

    if record["host"] != "azure":
        return 0
    for other in remaining:
        if other["host"] == "azure" and other["place"] == record["place"]:
            return 0
    if ui.confirm("No Azure server is left. Delete the registry and environment too (the registry costs about $0.17 a day)?", default_yes=False):
        azure.remove_everything(record)
        ui.ok(f"Deleted the resource group {record['group']}")
    return 0
