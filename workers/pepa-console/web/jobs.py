"""Run child commands as background subprocesses, keep each live log, and pass typed answers in.
The web pages read these records; a chain runs several jobs one after another.
"""
import codecs
import json
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timedelta

from registry import get_app, get_command
from runner import build_argv, job_environment
from web import paths
from web.settings import SETTINGS

STATUS_LABEL = {
    "running": "Running",
    "ok": "Done",
    "failed": "Failed",
    "cancelled": "Stopped",
    "waiting": "Waiting",
    "skipped": "Skipped",
}

STOP_WAIT_SECONDS = 5
ESTIMATE_SECONDS = 120
SECONDS_PER_MINUTE = 60
CLOCK_FORMAT = "%H:%M"
DAY_FORMAT = "%d %b, %H:%M"
HISTORY_FOLDER_NAME = "jobs"
HISTORY_SETTING_FILE_NAME = "job-history.json"
# How long finished jobs are kept, in days; 0 keeps them for good.
KEEP_CHOICES = {
    7: "A week",
    30: "30 days",
    90: "90 days",
    365: "A year",
    0: "Forever",
}
KEEP_DAYS = 30
READ_BYTES = 4096
# Asks a child to announce each item it starts and finishes, which the run panel lists.
ITEM_EVENTS = {"PEPA_ITEM_EVENTS": "on"}

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
        if field["type"] == "dollars" and not raw.replace(".", "", 1).isdigit():
            raise ValueError(f"{name} must be an amount in dollars, like 2.50.")
        if field["type"] == "choice" and raw not in field["choices"]:
            raise ValueError(f"{name} must be one of {', '.join(field['choices'])}.")
        if name.startswith("-"):
            flags.extend([name, raw])
        else:
            positionals.append(raw)
    return positionals + flags


def start_job(app_name, command_name, values, extra_environment=None):
    """Start one child command in the background and return its job id.

    Args:
        values: submitted form fields, keyed by flag or positional name.
        extra_environment: variables for this run only, such as the list of papers it works on.

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
    environment = job_environment(app_name)
    environment.update(ITEM_EVENTS)
    environment.update(extra_environment or {})
    try:
        process = subprocess.Popen(argv, cwd=str(app.path), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment, start_new_session=os.name != "nt")
    except OSError as error:
        raise ValueError(f"Could not start {app_name} {command_name}: {error}") from error

    with LOCK:
        job_id = next_id(JOBS)
        JOBS[job_id] = {
            "id": job_id,
            "app": app_name,
            "command": command_name,
            "kind": command.kind,
            "shown": " ".join(argv[2:]),
            "status": "running",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "started": time.monotonic(),
            "ended": None,
            "exit_code": None,
            "lines": [],
            "partial": "",
            "dismissed": False,
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
    save_record("job", job)


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
    end_process_tree(PROCESSES[job_id])


def end_process_tree(process):
    """End a child and every process it started; on Windows the child is often a launcher for the real Python."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    elif process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
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
        WATCHERS[job_id].join(timeout=STOP_WAIT_SECONDS)


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
        "started_at": started_text(job),
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


def json_reply(app_name, command_name, flags, extra_environment=None):
    """Run a command that prints one JSON line and stops soon after, and return what it printed, or None."""
    app = get_app(app_name)
    argv = build_argv(get_command(app_name, command_name), flags)
    environment = job_environment(app_name)
    environment.update(extra_environment or {})
    try:
        done = subprocess.run(argv, cwd=str(app.path), env=environment, capture_output=True, text=True, encoding="utf-8", timeout=ESTIMATE_SECONDS)
    except subprocess.TimeoutExpired:
        return None
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return None


def latest_job(app_name, command_name):
    """The newest job for one command, running or not, or None."""
    for row in list_jobs():
        if row["app"] == app_name and row["command"] == command_name:
            return row
    return None


def shown_job(app_name, command_name):
    """The newest job for one command that its page still shows: not stopped and not closed."""
    row = latest_job(app_name, command_name)
    if row is None or row["status"] == "cancelled" or JOBS[row["id"]]["dismissed"]:
        return None
    return row


def shown_chain():
    """The newest pipeline run the home page still shows: not stopped and not closed."""
    with LOCK:
        if not CHAINS:
            return None
        newest = max(CHAINS, key=int)
        chain = CHAINS[newest]
        if chain["status"] == "cancelled" or chain["dismissed"]:
            return None
        return chain_row(chain)


def dismiss(records, record_id):
    """Close a finished job or pipeline run, so its page stops showing it."""
    with LOCK:
        record = records.get(record_id)
        if record is not None and record["status"] != "running":
            record["dismissed"] = True


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
            "values": step.get("values", {}),
            "only": step.get("only"),
            "job_id": None,
            "status": "waiting",
            "error": "",
        })
    with LOCK:
        chain_id = next_id(CHAINS)
        CHAINS[chain_id] = {
            "id": chain_id,
            "status": "running",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "started": time.monotonic(),
            "ended": None,
            "steps": planned,
            "dismissed": False,
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
        extra = {}
        if step["only"] is not None:
            extra["PEPA_ONLY_FILE"] = str(paths.only_list_for(step["app"], step["only"], f"chain{chain_id}"))
        try:
            job_id = start_job(step["app"], step["command"], step["values"], extra)
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
    save_record("chain", CHAINS[chain_id])


def chain_row(chain):
    """The fields a page shows for one pipeline run, with a copy of its steps."""
    return {
        "id": chain["id"],
        "status": chain["status"],
        "label": STATUS_LABEL[chain["status"]],
        "started_at": started_text(chain),
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
            job = JOBS.get(step["job_id"])
            if job is None:
                continue
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


# ---- History ----

def next_id(records):
    """The id after the highest one in use, so ids read back from disk are never reused."""
    numbers = [int(key) for key in records]
    return str(max(numbers, default=0) + 1)


def started_text(record):
    """When a job or Library run started: the time for today, the day and time before that."""
    started = datetime.fromisoformat(record["started_at"])
    if started.date() == datetime.now().date():
        return started.strftime(CLOCK_FORMAT)
    return started.strftime(DAY_FORMAT).lstrip("0")


def history_folder():
    """Where finished jobs are kept: beside the key store, outside the workspace."""
    return SETTINGS["keys_file"].parent / HISTORY_FOLDER_NAME


def save_record(kind, record):
    """Keep a finished job or Library run on disk, so the Jobs page still lists it after a restart."""
    with LOCK:
        kept = dict(record)
        kept["seconds"] = int(record["ended"] - record["started"])
        if kind == "chain":
            kept["steps"] = [dict(step) for step in record["steps"]]
    kept.pop("started")
    kept.pop("ended")
    try:
        paths.write_json(history_folder() / f"{kind}-{record['id']}.json", kept)
    except OSError:
        return


def keep_days():
    """How many days finished jobs are kept: the user's choice on the Jobs page, else 30."""
    path = SETTINGS["keys_file"].parent / HISTORY_SETTING_FILE_NAME
    try:
        days = json.loads(path.read_text(encoding="utf-8"))["keep_days"]
    except (OSError, ValueError, KeyError):
        return KEEP_DAYS
    if days not in KEEP_CHOICES:
        return KEEP_DAYS
    return days


def set_keep_days(days):
    """Remember how long finished jobs are kept, and forget the ones already older than that.

    Raises:
        ValueError: the number of days is not one of the choices.
    """
    if days not in KEEP_CHOICES:
        raise ValueError("Pick one of the choices for how long jobs are kept.")
    paths.write_json(SETTINGS["keys_file"].parent / HISTORY_SETTING_FILE_NAME, {"keep_days": days})
    forget_old_jobs()


def forget_old_jobs():
    """Drop finished jobs and Library runs that started before the kept days, from the page and from disk."""
    days = keep_days()
    if days == 0:
        return
    oldest = datetime.now() - timedelta(days=days)
    records = {"job": JOBS, "chain": CHAINS}
    for kind, kept in records.items():
        with LOCK:
            old_ids = [record_id for record_id, record in kept.items() if record["status"] != "running" and datetime.fromisoformat(record["started_at"]) < oldest]
            for record_id in old_ids:
                del kept[record_id]
        for record_id in old_ids:
            (history_folder() / f"{kind}-{record_id}.json").unlink(missing_ok=True)


def load_history():
    """Read back the finished jobs and Library runs kept on disk, oldest first.

    Read-back runs count as closed, so the Library does not show last week's run as the current one.
    """
    folder = history_folder()
    if not folder.is_dir():
        return
    records = {"job": JOBS, "chain": CHAINS}
    saved = sorted(folder.glob("*.json"), key=lambda path: int(path.stem.partition("-")[2]))
    for path in saved:
        kind = path.stem.partition("-")[0]
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        record["started"] = 0.0
        record["ended"] = float(record.pop("seconds"))
        record["dismissed"] = True
        records[kind][record["id"]] = record
    forget_old_jobs()
