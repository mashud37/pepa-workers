"""Announce a run's stages and items as lines the web console turns into its progress view.
A terminal sees only the stages; the console switches the rest on through PEPA_ITEM_EVENTS.
"""
import os
import sys
import threading

from cli import ui

ON = os.environ.get("PEPA_ITEM_EVENTS") == "on"
PREFIX = "pepa-item:"
STAGE_PREFIX = "── "
LOCK = threading.Lock()


def stage(label):
    """One stage heading, such as "Writing the sections": the console shows it as the current step, a terminal as a step line."""
    if not ON:
        ui.step(label)
        return
    with LOCK:
        print(f"{STAGE_PREFIX}{label}", file=sys.stderr, flush=True)


def announce(state, name="", detail=""):
    """One event: "total" with the count as name, then "start", "progress", "ok" or "failed" per item."""
    if not ON:
        return
    with LOCK:
        print(f"{PREFIX} {state} | {name} | {detail}", file=sys.stderr, flush=True)
