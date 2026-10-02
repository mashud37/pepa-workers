"""Run child commands as background subprocesses, keep each live log, and pass typed answers in.
The web pages read these records; a chain runs several jobs one after another.
"""
import codecs
import os
import subprocess
import threading
import time
from datetime import datetime

from registry import get_app, get_command
from runner import build_argv
from web import keys, paths

STATUS_LABEL = {
    "running": "Running",
    "ok": "Done",
    "failed": "Failed",
    "cancelled": "Stopped",
    "waiting": "Waiting",
    "skipped": "Skipped",
}

CHILD_ENVIRONMENT = {
    "PYTHONUNBUFFERED": "1",
    "PYTHONIOENCODING": "utf-8",
}

STOP_WAIT_SECONDS = 5
SECONDS_PER_MINUTE = 60
CLOCK_FORMAT = "%H:%M"
READ_BYTES = 4096

JOBS = {}
CHAINS = {}
PROCESSES = {}
WATCHERS = {}
LOCK = threading.Lock()


# ---- Starting a job ----

def form_flags(command, values):
    """Turn a submitted form into the arguments for one command.

    Raises:
        ValueError: a required value is missing, or a value has the wrong shape.
    """
    positionals = []
    flags = []
    for field in command.fields:
        name = field["name"]
        raw = values.get(name, "").strip()
        if field["type"] == "bool":
            if raw:
                flags.append(name)
            continue
        if not raw:
            if not name.startswith("-"):
                raise ValueError(f"{command.name} needs a value for {name}.")
            continue
        if field["type"] == "int" and not raw.isdigit():
            raise ValueError(f"{name} must be a whole number.")
        if field["type"] == "choice" and raw not in field["choices"]:
            raise ValueError(f"{name} must be one of {', '.join(field['choices'])}.")
        if name.startswith("-"):
            flags.extend([name, raw])
        else:
            positionals.append(raw)
    return positionals + flags


def start_job(app_name, command_name, values):
    """Start one child command in the background and return its job id.

    Args:
        values: submitted form fields, keyed by flag or positional name.

    Raises:
        ValueError: the command is unknown, runs only in a terminal, or the form is invalid.
    """
    app = get_app(app_name)
    command = get_command(app_name, command_name)
    if app is None or command is None:
        raise ValueError(f"Unknown command: {app_name} {command_name}.")
    if command.kind == "terminal":
        raise ValueError(f"{app_name} {command_name} runs only in a terminal.")

    argv = build_argv(command, form_flags(command, values))
    environment = dict(os.environ)
    environment.update(paths.environment_for(app_name))
    environment.update(keys.environment_for(app_name))
    environment.update(CHILD_ENVIRONMENT)
    try:
        process = subprocess.Popen(argv, cwd=str(app.path), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment)
    except OSError as error:
        raise ValueError(f"Could not start {app_name} {command_name}: {error}") from error

    with LOCK:
        job_id = str(len(JOBS) + 1)
        JOBS[job_id] = {
            "id": job_id,
            "app": app_name,
            "command": command_name,
            "kind": command.kind,
            "shown": " ".join(argv[2:]),
            "status": "running",
            "started_at": datetime.now().strftime(CLOCK_FORMAT),
            "started": time.monotonic(),
            "ended": None,
            "exit_code": None,
            "lines": [],
            "partial": "",
        }
        PROCESSES[job_id] = process
        watcher = threading.Thread(target=watch_job, args=(job_id,), daemon=True)
        WATCHERS[job_id] = watcher
    watcher.start()
    return job_id


def add_output(job_id, text):
    """Add printed text to a job's log; a line still waiting for its newline stays unfinished.

    A carriage return starts its line over, as it does in a terminal. A hint to run
    `python manage.py <command>` is shown as the app's own command, which is what works once installed.
    """
    with LOCK:
        job = JOBS[job_id]
        pieces = (job["partial"] + text).split("\n")
        job["partial"] = pieces.pop()
        for piece in pieces:
            line = piece.rstrip("\r").split("\r")[-1]
            job["lines"].append(line.replace("python manage.py ", job["app"] + " "))


def watch_job(job_id):
    """Copy everything a job prints into its log while it runs, then record how it ended.

    Output is read in pieces rather than whole lines, so a question waiting for an answer shows at once.
    """
    process = PROCESSES[job_id]
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    chunk = process.stdout.read1(READ_BYTES)
    while chunk:
        add_output(job_id, decoder.decode(chunk))
        chunk = process.stdout.read1(READ_BYTES)
    exit_code = process.wait()
    try:
        process.stdin.close()
    except OSError:
        pass

    with LOCK:
        job = JOBS[job_id]
        if job["partial"]:
            job["lines"].append(job["partial"])
            job["partial"] = ""
        job["exit_code"] = exit_code
        job["ended"] = time.monotonic()
        if job["status"] == "running" and exit_code == 0:
            job["status"] = "ok"
        elif job["status"] == "running":
            job["status"] = "failed"


def send_input(job_id, text):
    """Type one line into a running job, as if answering its question in a terminal.

    Raises:
        ValueError: the job is not running, or it no longer reads what is typed.
    """
    with LOCK:
        job = JOBS.get(job_id)
        if job is None or job["status"] != "running":
            raise ValueError("That job is no longer running.")
        job["lines"].append(job["partial"].split("\r")[-1] + text)
        job["partial"] = ""
    process = PROCESSES[job_id]
    try:
        process.stdin.write(text.encode("utf-8") + b"\n")
        process.stdin.flush()
    except (OSError, ValueError) as error:
        raise ValueError("That job no longer reads answers.") from error


# ---- Stopping jobs ----

def cancel_job(job_id):
    """Stop a running job; the child skips its finished work when it runs again."""
    with LOCK:
        job = JOBS.get(job_id)
        if job is None or job["status"] != "running":
            return
        job["status"] = "cancelled"
    process = PROCESSES[job_id]
    process.terminate()
    try:
        process.wait(timeout=STOP_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()


def stop_all():
    """Cancel every job still running, so quitting the console leaves no child behind."""
    with LOCK:
        running = [job_id for job_id, job in JOBS.items() if job["status"] == "running"]
    for job_id in running:
        cancel_job(job_id)


# ---- Reading jobs ----

def elapsed_text(record):
    """How long a job or chain has run, or ran: seconds under a minute, otherwise minutes and seconds."""
    end = record["ended"] or time.monotonic()
    seconds = int(end - record["started"])
    if seconds < SECONDS_PER_MINUTE:
        return f"{seconds}s"
    return f"{seconds // SECONDS_PER_MINUTE}m {seconds % SECONDS_PER_MINUTE:02d}s"


def summary_row(job):
    """The fields a jobs list shows for one job, with the last line's status symbols removed."""
    last_line = ""
    for line in reversed(job["lines"]):
        text = line.strip().lstrip("▶✓⚠·✗─ ")
        if text:
            last_line = text
            break
    return {
        "id": job["id"],
        "app": job["app"],
        "command": job["command"],
        "shown": job["shown"],
        "status": job["status"],
        "label": STATUS_LABEL[job["status"]],
        "started_at": job["started_at"],
        "elapsed": elapsed_text(job),
        "exit_code": job["exit_code"],
        "last_line": last_line,
    }


def job_summary(job_id):
    """One job's summary, or None when there is no such job."""
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return summary_row(job)


def job_log(job_id, after):
    """The log lines after a position, the unfinished line, and the job's state, for a live log."""
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        lines = job["lines"][after:]
        waiting_job = job_id if job["status"] == "running" else None
        return {
            "lines": lines,
            "next": after + len(lines),
            "partial": job["partial"].split("\r")[-1],
            "job": waiting_job,
            "status": job["status"],
            "label": STATUS_LABEL[job["status"]],
            "exit_code": job["exit_code"],
            "elapsed": elapsed_text(job),
            "steps": [],
        }


def list_jobs():
    """Every job, newest first."""
    with LOCK:
        rows = [summary_row(job) for job in JOBS.values()]
    rows.reverse()
    return rows


def running_count():
    """How many jobs are working right now, leaving out services that run until stopped."""
    with LOCK:
        working = [job for job in JOBS.values() if job["status"] == "running" and job["kind"] != "service"]
    return len(working)


def latest_job(app_name, command_name):
    """The newest job for one command, running or not, or None."""
    for row in list_jobs():
        if row["app"] == app_name and row["command"] == command_name:
            return row
    return None


def running_service(app_name, command_name):
    """The id of the running job for this command, or None."""
    row = latest_job(app_name, command_name)
    if row is None or row["status"] != "running":
        return None
    return row["id"]


# ---- Chains ----

def start_chain(steps):
    """Run several commands one after another in the background and return the chain id."""
    planned = []
    for step in steps:
        planned.append({
            "app": step["app"],
            "command": step["command"],
            "label": step["label"],
            "job_id": None,
            "status": "waiting",
            "error": "",
        })
    with LOCK:
        chain_id = str(len(CHAINS) + 1)
        CHAINS[chain_id] = {
            "id": chain_id,
            "status": "running",
            "started_at": datetime.now().strftime(CLOCK_FORMAT),
            "started": time.monotonic(),
            "ended": None,
            "steps": planned,
        }
    threading.Thread(target=run_chain, args=(chain_id,), daemon=True).start()
    return chain_id


def run_chain(chain_id):
    """Start each step once the one before it has succeeded; any other ending skips the rest."""
    outcome = "ok"
    for step in CHAINS[chain_id]["steps"]:
        if outcome != "ok":
            with LOCK:
                step["status"] = "skipped"
            continue
        try:
            job_id = start_job(step["app"], step["command"], {})
        except ValueError as error:
            with LOCK:
                step["status"] = "failed"
                step["error"] = str(error)
            outcome = "failed"
            continue
        with LOCK:
            step["job_id"] = job_id
            step["status"] = "running"
        WATCHERS[job_id].join()
        with LOCK:
            step["status"] = JOBS[job_id]["status"]
            outcome = step["status"]
    with LOCK:
        CHAINS[chain_id]["status"] = outcome
        CHAINS[chain_id]["ended"] = time.monotonic()


def chain_row(chain):
    """The fields a page shows for one pipeline run, with a copy of its steps."""
    return {
        "id": chain["id"],
        "status": chain["status"],
        "label": STATUS_LABEL[chain["status"]],
        "started_at": chain["started_at"],
        "elapsed": elapsed_text(chain),
        "steps": [dict(step) for step in chain["steps"]],
    }


def list_chains():
    """Every pipeline run, newest first."""
    with LOCK:
        rows = [chain_row(chain) for chain in CHAINS.values()]
    rows.reverse()
    return rows


def chain_summary(chain_id):
    """One pipeline run's summary, or None when there is no such run."""
    with LOCK:
        chain = CHAINS.get(chain_id)
        if chain is None:
            return None
        return chain_row(chain)


def chain_log(chain_id, after):
    """A pipeline run's log after a position: each started step's heading, then its job's lines.

    Only the running step still grows, and it is always the last one, so a position stays valid.
    """
    with LOCK:
        chain = CHAINS.get(chain_id)
        if chain is None:
            return None
        lines = []
        running_job = None
        for step in chain["steps"]:
            if step["status"] in ("waiting", "skipped"):
                continue
            if lines:
                lines.append("")
            lines.append(f"── {step['label']}")
            if step["job_id"] is None:
                lines.append(step["error"])
                continue
            job = JOBS[step["job_id"]]
            lines.extend(job["lines"])
            if job["status"] == "running":
                running_job = job

        new_lines = lines[after:]
        row = chain_row(chain)
        return {
            "lines": new_lines,
            "next": after + len(new_lines),
            "partial": running_job["partial"].split("\r")[-1] if running_job else "",
            "job": running_job["id"] if running_job else None,
            "status": row["status"],
            "label": row["label"],
            "exit_code": None,
            "elapsed": row["elapsed"],
            "steps": row["steps"],
        }
