"""Read the running Zotero app's references through its local API, keeping a copy that each run updates.
The lookup tries their DOIs before any search.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

import config
from biblio.references import csl_records
from cli import ui

PAGE_SIZE = 100
TIMEOUT_SECONDS = 60
COPY_FILE = config.DATA_DIR / "zotero.json"
# What to tell the user when Zotero cannot be read, by why.
NOT_READABLE = {
    "closed": "Zotero is not running. Open Zotero and try again.",
    "off": "Zotero does not let other applications read it yet. In Zotero, open Edit, Settings, Advanced, and tick \"Allow other applications on this computer to communicate with Zotero\".",
}


def items_url(parameters):
    """The local API address of the library's top-level items, those that are not notes or attachments."""
    return config.setting("zotero_url").rstrip("/") + "/users/0/items/top?" + urllib.parse.urlencode(parameters)


def zotero_status():
    """How Zotero answers: "connected" with its number of items and library version, "off" when its local API is not enabled, or "closed"."""
    try:
        with urllib.request.urlopen(items_url({"limit": 1, "format": "keys"}), timeout=TIMEOUT_SECONDS) as reply:
            return {
                "state": "connected",
                "count": int(reply.headers.get("Total-Results", "0")),
                "version": int(reply.headers.get("Last-Modified-Version", "0")),
            }
    except urllib.error.HTTPError:
        return {"state": "off", "count": 0, "version": 0}
    except (urllib.error.URLError, TimeoutError):
        return {"state": "closed", "count": 0, "version": 0}


def kept_copy():
    """The kept copy of the Zotero items, by Zotero's id, with the library version it was read at."""
    if not COPY_FILE.exists():
        return {"version": 0, "items": {}}
    return json.loads(COPY_FILE.read_text(encoding="utf-8"))


def changed_items(since, count):
    """Every item changed since a library version, read a page at a time; since 0 reads them all."""
    starts = list(range(0, count, PAGE_SIZE))
    entries = []
    for number, start in enumerate(starts, start=1):
        ui.info(f"[{number}/{len(starts)}] Zotero items {start + 1} to {min(start + PAGE_SIZE, count)}")
        parameters = {"format": "csljson", "limit": PAGE_SIZE, "start": start, "since": since}
        with urllib.request.urlopen(items_url(parameters), timeout=TIMEOUT_SECONDS) as reply:
            entries.extend(json.loads(reply.read()))
    return entries


def update_copy():
    """Bring the kept copy up to date with Zotero, reading only what changed since the last read.

    Raises:
        SystemExit: Zotero is not running, or its local API is not enabled.
    """
    status = zotero_status()
    if status["state"] != "connected":
        raise SystemExit(NOT_READABLE[status["state"]])
    copy = kept_copy()
    if copy["version"] == status["version"]:
        ui.info(f"Zotero: {len(copy['items']):,} items, unchanged since the last read")
        return
    with urllib.request.urlopen(items_url({"limit": 1, "format": "keys", "since": copy["version"]}), timeout=TIMEOUT_SECONDS) as reply:
        changed = int(reply.headers.get("Total-Results", "0"))
    ui.info(f"Zotero: reading {changed:,} new or changed items")
    for entry in changed_items(copy["version"], changed):
        copy["items"][entry["id"]] = entry
    copy["version"] = status["version"]
    COPY_FILE.parent.mkdir(parents=True, exist_ok=True)
    COPY_FILE.write_text(json.dumps(copy, ensure_ascii=False), encoding="utf-8")


def zotero_records():
    """Every item of the kept Zotero copy as a reference record."""
    return csl_records(list(kept_copy()["items"].values()))
