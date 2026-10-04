"""Keep each submitted Message Batch as a ticket on disk, and write its papers once it ends.
The `batches` command and the console's Library check these tickets.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import config
from cli import ui

TICKETS_DIR = config.DATA_DIR / "batches"
COUNT_NAMES = [
    "processing",
    "succeeded",
    "errored",
    "canceled",
    "expired",
]


# ---- Tickets on disk ----

def ticket_path(ticket_id):
    return TICKETS_DIR / f"{ticket_id}.json"


def save_ticket(ticket):
    """Write a ticket through a temporary file, so a crash never leaves half a ticket behind."""
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    path = ticket_path(ticket["id"])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(ticket, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_tickets():
    """Every ticket kept, oldest first."""
    if not TICKETS_DIR.is_dir():
        return []
    tickets = []
    for path in sorted(TICKETS_DIR.glob("*.json")):
        tickets.append(json.loads(path.read_text(encoding="utf-8")))
    tickets.sort(key=lambda ticket: ticket["created"])
    return tickets


def new_ticket(batch_ids, plans, out_dir, request_count):
    """Record a batch just sent, with the plan that turns its answers back into each paper's documents."""
    stored_plans = []
    for plan in plans:
        stored_plans.append(dict(plan, pdf=str(plan["pdf"])))
    ticket = {
        "id": batch_ids[0],
        "batches": batch_ids,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": config.load('ANTHROPIC_MODEL'),
        "out_dir": str(out_dir),
        "papers": len(plans),
        "requests": request_count,
        "state": "open",
        "counts": {name: 0 for name in COUNT_NAMES} | {"processing": request_count},
        "result": None,
        "plans": stored_plans,
    }
    save_ticket(ticket)
    return ticket


def pending_names():
    """The source file names waiting in a batch that has not been collected, so a new run leaves them out."""
    names = set()
    for ticket in load_tickets():
        if ticket["state"] == "open":
            for plan in ticket["plans"]:
                names.add(Path(plan["pdf"]).name)
    return names


# ---- Checking and collecting ----

def refresh(ticket):
    """The ticket with its batches' latest counts from Anthropic, and its papers written once every batch has ended."""
    from backends import anthropic_client

    counts = {name: 0 for name in COUNT_NAMES}
    ended = True
    for batch_id in ticket["batches"]:
        status = anthropic_client.batch_status(batch_id)
        for name in COUNT_NAMES:
            counts[name] += status["counts"][name]
        if status["state"] != "ended":
            ended = False
    updated = dict(ticket, counts=counts)
    if ended:
        updated = updated | collect(ticket)
    save_ticket(updated)
    return updated


def collect(ticket):
    """Write every paper's documents from an ended ticket's answers.

    Returns:
        dict with the ticket's new "state", when it was "collected", and its "result", papers done and failed.
    """
    from backends import anthropic_client
    from cli import summarize

    answers = {"results": {}, "truncated": set()}
    for batch_id in ticket["batches"]:
        collected = anthropic_client.collect_batch(batch_id)
        answers["results"].update(collected["results"])
        answers["truncated"] |= collected["truncated"]
    plans = [dict(plan, pdf=Path(plan["pdf"])) for plan in ticket["plans"]]
    assembled = summarize.assemble_batch(plans, answers, Path(ticket["out_dir"]))
    return {
        "state": "collected",
        "collected": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "result": {"done": assembled["done"], "failed": assembled["errors"]},
    }


# ---- The command ----

def shown(ticket):
    """What a list of batches shows for one ticket, without the plans."""
    return {key: value for key, value in ticket.items() if key != "plans"}


def run(cancel=None, forget=None, as_json=False):
    """Check every open batch and collect those that ended; or cancel one, or forget a collected one."""
    if cancel:
        from backends import anthropic_client

        for batch_id in json.loads(ticket_path(cancel).read_text(encoding="utf-8"))["batches"]:
            anthropic_client.cancel_batch(batch_id)
    if forget:
        ticket_path(forget).unlink(missing_ok=True)
    tickets = []
    for ticket in load_tickets():
        if ticket["state"] == "open":
            ticket = refresh(ticket)
        tickets.append(ticket)
    if as_json:
        print(json.dumps({"tickets": [shown(ticket) for ticket in tickets]}))
        return 0
    if not tickets:
        ui.info("No batches.")
        return 0
    rows = []
    for ticket in tickets:
        counts = ticket["counts"]
        answered = ticket["requests"] - counts["processing"]
        outcome = f"{answered} of {ticket['requests']} answered"
        if ticket["state"] == "collected":
            outcome = f"{ticket['result']['done']} written, {ticket['result']['failed']} failed"
        rows.append({
            "Batch": ticket["id"],
            "Sent": ticket["created"],
            "Papers": ticket["papers"],
            "State": ticket["state"],
            "Progress": outcome,
        })
    ui.table(rows, ["Batch", "Sent", "Papers", "State", "Progress"])
    return 0
