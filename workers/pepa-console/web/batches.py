"""Word pepa-sum's batch tickets for the Library's Batches card: how far each has got and when it was sent.
The card's route asks pepa-sum for the tickets.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from web import paths

TICKETS_FOLDER = ["pepa-sum", "data", "batches"]
LONGEST_BATCH = timedelta(hours=24)
CLOCK_FORMAT = "%H:%M"


def any_kept():
    """True when pepa-sum holds a batch ticket, so the Library asks about batches as soon as it opens."""
    folder = paths.project_folder().joinpath(*TICKETS_FOLDER)
    return folder.is_dir() and any(folder.glob("*.json"))


def waiting_stems():
    """The papers waiting in a batch not yet collected, by the name their prepared text was written under."""
    folder = paths.project_folder().joinpath(*TICKETS_FOLDER)
    stems = set()
    if not folder.is_dir():
        return stems
    for path in folder.glob("*.json"):
        ticket = json.loads(path.read_text(encoding="utf-8"))
        if ticket["state"] != "open":
            continue
        for plan in ticket["plans"]:
            stems.add(Path(plan["pdf"]).stem.removeprefix("text_"))
    return stems


def time_ago(moment):
    """How long ago a moment was, in the largest whole unit that fits."""
    seconds = int((datetime.now(timezone.utc) - moment).total_seconds())
    if seconds < 90:
        return "just now"
    if seconds < 90 * 60:
        return f"{seconds // 60} min ago"
    return f"{seconds // 3600} h ago"


def card_row(ticket):
    """One ticket as the card shows it: papers, progress through its requests, when it was sent and its last moment."""
    sent = datetime.fromisoformat(ticket["created"])
    answered = ticket["requests"] - ticket["counts"]["processing"]
    latest = (sent + LONGEST_BATCH).astimezone()
    return {
        "id": ticket["id"],
        "state": ticket["state"],
        "papers": ticket["papers"],
        "requests": ticket["requests"],
        "answered": answered,
        "share": round(100 * answered / max(1, ticket["requests"])),
        "sent": time_ago(sent),
        "latest": latest.strftime(CLOCK_FORMAT) + (" tomorrow" if latest.date() > datetime.now().date() else ""),
        "result": ticket["result"],
    }
