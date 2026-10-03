"""Announce each item a batch starts and finishes, as lines the web console turns into its progress list.
Silent in a terminal; the console switches it on through PEPA_ITEM_EVENTS.
"""
import os
import threading

ON = os.environ.get("PEPA_ITEM_EVENTS") == "on"
PREFIX = "pepa-item:"
LOCK = threading.Lock()


def announce(state, name="", detail=""):
    """One event: "total" with the count as name, then "start", "ok" or "failed" per item."""
    if not ON:
        return
    with LOCK:
        print(f"{PREFIX} {state} | {name} | {detail}", flush=True)
