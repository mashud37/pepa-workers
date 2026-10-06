"""Serve the web console's pages and form actions. Each handler reads the registry, folders,
jobs, or key store, then renders a template, answers with JSON, or redirects.
"""
import socket
import threading
import time
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from registry import get_app
from web import batches, documents, folders, jobs, keys, mascot, models, options, papers, paths
from web.settings import SETTINGS

MISSING_NOTE = {
    "keys": "Add a key in Settings first.",
    "models": "Choose an embedding model in Settings first.",
}
SET_ASIDE_ACTIONS = {
    "skip-prep": {"apps": ["pepa-prep"], "wanted": True, "message": "{items} will be skipped when preparing."},
    "skip-sum": {"apps": ["pepa-sum"], "wanted": True, "message": "{items} will be skipped when summarising."},
    "include": {"apps": ["pepa-prep", "pepa-sum"], "wanted": False, "message": "Back in every stage: {items}."},
}
# The Library's stages in the order a run takes them. An estimated stage shows its cost before it runs.
PIPELINE_STEPS = [
    {"app": "pepa-prep", "command": "extract", "label": "Prepare PDFs", "needs": "", "estimated": False},
    {"app": "pepa-sum", "command": "summarize", "label": "Summarise", "needs": "generation", "estimated": True},
    {"app": "pepa-read", "command": "index", "label": "Update search index", "needs": "", "estimated": False},
    {"app": "pepa-review", "command": "index", "label": "Update review index", "needs": "embedding", "estimated": False},
    {"app": "pepa-plan", "command": "abstract", "label": "Learn writing patterns", "needs": "generation", "estimated": True},
]

# A stage that brings a second command along in the same run.
FOLLOW_UPS = {
    "pepa-plan abstract": {"app": "pepa-plan", "command": "blueprint", "label": "Writing blueprints"},
}

# The Batches card's buttons and the pepa-sum flag each one sends.
BATCH_ACTIONS = {
    "cancel": "--cancel",
    "forget": "--forget",
}

# One check of the batches at a time, so the timer and a button never collect the same batch twice.
BATCH_CHECK = threading.Lock()

# The stages that can work on only the papers ticked in the Library.
ONLY_APPS = [
    "pepa-prep",
    "pepa-sum",
]

PDF_APPS = [
    "pepa-prep",
]

TEXT_SUFFIXES = [
    ".md",
    ".txt",
    ".jsonl",
    ".tsv",
    ".csv",
    ".log",
    ".yaml",
]

SHOWN_AS_IS = [
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
]

# Any other file, such as a saved web page, may carry its own script; it runs walled off from the console.
WALLED_POLICY = "sandbox allow-scripts"

PORT_CHECK_SECONDS = 0.3

bp = Blueprint("console", __name__)


# ---- Helpers ----

def find_app(name):
    """The registered app with this name, or a 404 page."""
    app = get_app(name)
    if app is None:
        abort(404)
    return app


def port_is_open(port):
    """True when something on this machine already answers on the port."""
    try:
        with socket.create_connection((SETTINGS["host"], port), timeout=PORT_CHECK_SECONDS):
            return True
    except OSError:
        return False


def copy_step(results, back_to):
    """Count one request's copies toward the browser's batch, sent one file per request;
    after the last file, flash one line per folder and send the browser back to the page.

    Args:
        results: a copy_into result per folder, or a string saying why nothing was copied there.
    """
    number = int(request.form.get("file_number", "1"))
    count = int(request.form.get("file_count", "1"))
    tally = {"folders": {}, "notes": []}
    if number > 1:
        tally = session.get("copy_tally", tally)
    for result in results:
        if isinstance(result, str):
            if result not in tally["notes"]:
                tally["notes"].append(result)
            continue
        counts = tally["folders"].get(result["folder"], {"copied": 0, "left_out": 0})
        counts["copied"] += len(result["copied"])
        counts["left_out"] += len(result["left_out"])
        tally["folders"][result["folder"]] = counts
    if number < count:
        session["copy_tally"] = tally
        return jsonify({"ok": True})
    session.pop("copy_tally", None)
    lines = []
    for folder, counts in tally["folders"].items():
        line = f"Copied {counts['copied']} file(s) into {folder}."
        if counts["left_out"]:
            line += f" Left out {counts['left_out']}: already there or not accepted."
        lines.append(line)
    flash(" ".join(lines + tally["notes"]))
    return redirect(back_to)


def folder_message(app_name, slot):
    """What was saved, and how many items sit in sub-folders the app is not reading."""
    if not paths.can_scan_subfolders(app_name, slot):
        return "Saved."
    count = folders.paper_counts(app_name, slot)
    here = folders.counted(count["here"], count["capped"])
    deeper = folders.counted(count["deeper"], count["capped"])
    items = f"{here} items"
    if count["here"] == 1:
        items = "1 item"
    if not count["deeper"]:
        return f"Saved. {items} in that folder."
    if paths.scans_subfolders(app_name, slot):
        return f"Saved. {items} there and {deeper} in sub-folders, all of them read."
    return f"Saved. {items} there and {deeper} in sub-folders, which stay unread until you turn on Scan sub-folders."


def item_count(count):
    """A count of library items in words, such as "1 item" or "17 items"."""
    if count == 1:
        return "1 item"
    return f"{count:,} items"


def back_to(default):
    """The page a form asks to return to, or the given page when it asks for nothing sensible."""
    wanted = request.form.get("back", "")
    if wanted.startswith("/") and not wanted.startswith("//") and "\\" not in wanted:
        return wanted
    return default


def run_panel(record, log_url):
    """The live run panel for a job or pipeline run, as HTML the page puts in place."""
    return jsonify({"panel": render_template("_run.html", run=record, log_url=log_url)})


def log_position():
    """The `after` query value as a number, or a 400 page when it is not one."""
    after = request.args.get("after", "0")
    if not after.isdigit():
        abort(400)
    return int(after)


def live_log(log):
    """A log as JSON, with the addresses for answering and stopping the job it is waiting on."""
    if log is None:
        abort(404)
    extra = {
        "input_url": None,
        "cancel_url": None,
        "running": jobs.running_count(),
    }
    if log["job"] is not None:
        extra["input_url"] = url_for("console.job_input", job_id=log["job"])
        extra["cancel_url"] = url_for("console.job_cancel", job_id=log["job"])
    return jsonify(log | extra)


# ---- Icon ----

@bp.route("/favicon.svg")
def favicon():
    drawing = str(mascot.svg("pepa", 2)).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    return Response(drawing, mimetype="image/svg+xml")


# ---- Library ----

@bp.route("/")
def library():
    wanted = request.args.get("q", "")
    length = request.args.get("length", "")
    page = request.args.get("page", "1")
    sort = request.args.get("sort", "name")
    if sort.lstrip("-") not in papers.SORT_COLUMNS:
        sort = "name"
    if length not in papers.LENGTHS:
        length = ""
    summary = folders.pipeline_summary()
    nothing_yet = summary["pdfs"] == 0 and summary["summarised"] == 0
    return render_template(
        "library.html",
        summary=summary,
        steps=pipeline_steps(),
        chain=jobs.shown_chain(),
        first_run=nothing_yet and not keys.load_store()["keys"],
        listing=papers.paper_rows(wanted, length, int(page) if page.isdigit() else 1, sort),
        sort=sort,
        has_batches=batches.any_kept(),
        own_pdfs=paths.own_pdf_folder(),
        wanted=wanted,
        length=length,
        lengths=papers.LENGTHS,
        book_pages=papers.book_pages(),
    )


@bp.route("/library/names")
def library_names():
    length = request.args.get("length", "")
    if length not in papers.LENGTHS:
        length = ""
    found = papers.matching_papers(request.args.get("q", ""), length)
    names = [Path(row["relative"]).name for row in found["rows"]]
    return jsonify({"names": names})


def pipeline_steps():
    """The Library's stages, each with what it still lacks before it can run and its settings."""
    steps = []
    for step in PIPELINE_STEPS:
        missing = ""
        if step["needs"]:
            missing = models.missing_choice(step["app"], step["needs"])
        steps.append({**step, "missing": missing, "settings": options.card_view(step["app"])})
    return steps


@bp.route("/papers")
def papers_page():  # lint-style: ignore MD001
    return redirect(url_for("console.library", **request.args) + "#papers")


@bp.route("/library/estimate", methods=["POST"])
def library_estimate():
    """What the ticked paid stages would cost, each counting the papers the stages before it add."""
    ticked = request.form.getlist("step")
    only = request.form.getlist("only")
    found = {}
    sum_more = 0
    if "pepa-sum summarize" in ticked:
        extra = {}
        only_file = None
        if only:
            only_file = paths.only_list_for("pepa-sum", only, f"estimate{time.monotonic_ns()}")
            extra["PEPA_ONLY_FILE"] = str(only_file)
        if "pepa-prep extract" in ticked:
            sum_more = folders.unprepared_count(only)
        found["pepa-sum"] = jobs.json_reply("pepa-sum", "summarize", ["--estimate", "--more", str(sum_more)], extra)
        if only_file is not None:
            only_file.unlink(missing_ok=True)
    if "pepa-plan abstract" in ticked:
        plan_more = 0
        if found.get("pepa-sum"):
            plan_more = found["pepa-sum"]["papers"]
        found["pepa-plan"] = jobs.json_reply("pepa-plan", "abstract", ["--estimate", "--more", str(plan_more)])
    for app_name, estimate in found.items():
        if estimate is None:
            return jsonify({"error": f"{app_name} could not estimate this run."}), 500
    if found.get("pepa-sum"):
        found["pepa-sum"]["more"] = sum_more
    return jsonify(found)


@bp.route("/library/batches", methods=["GET", "POST"])
def library_batches():
    """The Batches card, after asking Anthropic about every open batch; a post can also cancel or forget one."""
    flags = ["--json"]
    action = request.form.get("action", "")
    if request.method == "POST" and action in BATCH_ACTIONS:
        flags += [BATCH_ACTIONS[action], request.form.get("batch", "")]
    if not BATCH_CHECK.acquire(blocking=False):
        return jsonify({"error": "Already checking."}), 409
    try:
        found = jobs.json_reply("pepa-sum", "batches", flags)
    finally:
        BATCH_CHECK.release()
    if found is None:
        return jsonify({"error": "pepa-sum could not check its batches."}), 500
    tickets = [batches.card_row(ticket) for ticket in found["tickets"]]
    return render_template("_batches.html", tickets=tickets)


@bp.route("/library/copy", methods=["POST"])
def library_copy():
    files = folders.picked_files(request.files.getlist("pdfs"))
    results = []
    for app_name in PDF_APPS:
        try:
            results.append(folders.copy_into(app_name, "sources", files, ".pdf"))
        except ValueError as error:
            results.append(str(error))
    return copy_step(results, url_for("console.library"))


@bp.route("/library/run", methods=["POST"])
def library_run():
    ticked = request.form.getlist("step")
    only = request.form.getlist("only") or None
    chosen = [step for step in pipeline_steps() if f"{step['app']} {step['command']}" in ticked]
    if not chosen:
        return jsonify({"error": "Tick at least one step."}), 400
    steps = []
    for step in chosen:
        if step["missing"]:
            return jsonify({"error": f"{step['label']}: {MISSING_NOTE[step['missing']]}"}), 400
        if step["settings"]:
            try:
                options.save_choices(step["app"], request.form)
            except ValueError as error:
                return jsonify({"error": str(error)}), 400
        if step["app"] in ONLY_APPS:
            step["only"] = only
        if step["estimated"]:
            step["values"] = {"--approve-cost": request.form.get(f"limit {step['app']}", "")}
        steps.append(step)
        follow_up = FOLLOW_UPS.get(f"{step['app']} {step['command']}")
        if follow_up:
            steps.append(follow_up)
    chain_id = jobs.start_chain(steps)
    return run_panel(jobs.chain_summary(chain_id), url_for("console.chain_log", chain_id=chain_id))


@bp.route("/papers/set-aside", methods=["POST"])
def papers_set_aside():
    names = request.form.getlist("name")
    action = SET_ASIDE_ACTIONS.get(request.form.get("action", ""))
    if not names or action is None:
        flash("Tick at least one item.")
    else:
        for app_name in action["apps"]:
            paths.set_excluded(names, app_name, action["wanted"])
        flash(action["message"].format(items=item_count(len(names))))
    return redirect(request.form.get("back") or url_for("console.library"))


@bp.route("/papers/remove-copies", methods=["POST"])
def papers_remove_copies():
    names = request.form.getlist("name")
    if not names:
        flash("Tick at least one item.")
        return redirect(request.form.get("back") or url_for("console.library"))
    try:
        outcome = papers.remove_copies(names)
    except ValueError as error:
        flash(str(error))
        return redirect(request.form.get("back") or url_for("console.library"))
    message = f"Removed {outcome['removed']} PDF cop{'y' if outcome['removed'] == 1 else 'ies'}."
    if outcome["kept"]:
        message += f" Kept {len(outcome['kept'])}: not prepared yet."
    flash(message)
    return redirect(request.form.get("back") or url_for("console.library"))


@bp.route("/papers/chapters")
def chapters_page():
    relative = request.args.get("file", "")
    if papers.source_path(relative) is None:
        abort(404)
    return render_template("chapters.html", book=papers.chapter_view(relative), kind_names=papers.LEAVE_OUT_KINDS)


@bp.route("/papers/chapters", methods=["POST"])
def chapters_save():
    relative = request.form.get("file", "")
    path = papers.source_path(relative)
    if path is None:
        abort(404)
    try:
        skips = request.form.getlist("skip")
        kinds = {}
        for page in skips:
            kinds[page] = request.form.get(f"kind_{page}", "")
        papers.save_marks(relative, request.form.getlist("start"), skips, kinds)
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("console.chapters_page", file=relative))
    job_id = jobs.start_job("pepa-prep", "extract", {"--file": path.name, "--force": "on"})
    return redirect(url_for("console.job_page", job_id=job_id))


@bp.route("/papers/page")
def paper_page_image():
    relative = request.args.get("file", "")
    number = request.args.get("n", "")
    size = request.args.get("size", "")
    if papers.source_path(relative) is None or not number.isdigit() or size not in papers.PAGE_WIDTHS:
        abort(404)
    image = papers.page_image(relative, int(number), papers.PAGE_WIDTHS[size])
    if image is None:
        abort(404)
    return Response(image, mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


# ---- Apps ----

@bp.route("/apps")
def apps_page():  # lint-style: ignore MD001
    return render_template("apps.html")


@bp.route("/apps/<name>")
def app_page(name):
    app = find_app(name)
    latest = {}
    for command in app.commands:
        latest[command.name] = jobs.shown_job(name, command.name)
    places = folders.app_folders(name)
    return render_template(
        "app.html",
        app=app,
        latest=latest,
        key_sources=keys.sources_for(name),
        paths=folders.path_choices(places),
        places=places,
        settings=options.card_view(name),
    )


@bp.route("/apps/<name>/settings", methods=["POST"])
def app_settings(name):
    find_app(name)
    try:
        options.save_choices(name, request.form)
        flash("Saved. The next run uses these settings.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.app_page", name=name))


@bp.route("/apps/<name>/run/<command_name>", methods=["POST"])
def app_run(name, command_name):
    find_app(name)
    try:
        job_id = jobs.start_job(name, command_name, request.form.to_dict())
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return run_panel(jobs.job_summary(job_id), url_for("console.job_log", job_id=job_id))


@bp.route("/apps/<name>/copy", methods=["POST"])
def app_copy(name):
    find_app(name)
    files = folders.picked_files(request.files.getlist("files"))
    try:
        result = folders.copy_into(name, request.form.get("slot", ""), files, "")
    except ValueError as error:
        result = str(error)
    return copy_step([result], url_for("console.app_page", name=name))


@bp.route("/apps/<name>/write", methods=["POST"])
def app_write(name):
    find_app(name)
    slot = request.form.get("slot", "")
    try:
        saved = folders.write_new_file(name, slot, request.form.get("name", ""), request.form.get("text", ""))
        flash(f"Saved {saved}.")
    except ValueError as error:
        flash(str(error))
    return redirect(back_to(url_for("console.app_page", name=name)))


@bp.route("/apps/<name>/files/<slot>/<path:relative>")
def app_file(name, slot, relative):
    find_app(name)
    path = folders.resolve_file(name, slot, relative)
    if path is None:
        abort(404)
    if path.suffix.lower() in TEXT_SUFFIXES:
        return send_file(path, mimetype="text/plain")
    response = send_file(path)
    if path.suffix.lower() not in SHOWN_AS_IS:
        response.headers["Content-Security-Policy"] = WALLED_POLICY
    return response


@bp.route("/view/<name>/<slot>/<path:relative>")
def view_page(name, slot, relative):
    app = find_app(name)
    path = folders.resolve_file(name, slot, relative)
    if path is None:
        abort(404)
    place = paths.find_place(name, slot)
    return render_template(
        "view.html",
        app=app,
        slot=slot,
        place=place,
        relative=relative,
        folder=str(Path(relative).parent) if Path(relative).parent != Path(".") else "",
        document=documents.document_view(path),
        related=documents.related_documents(path.name),
    )


@bp.route("/browse/<name>/<slot>")
def browse_page(name, slot):
    app = find_app(name)
    place = paths.find_place(name, slot)
    inside = request.args.get("in", "")
    if place is None or folders.resolve_folder(name, slot, inside) is None:
        abort(404)
    page = request.args.get("page", "1")
    wanted = request.args.get("q", "")
    listing = documents.folder_listing(paths.chosen(name, slot), inside, wanted, int(page) if page.isdigit() else 1)
    return render_template(
        "files.html",
        app=app,
        place=place,
        slot=slot,
        inside=inside,
        wanted=wanted,
        listing=listing,
        folder=str(paths.chosen(name, slot)),
    )


# ---- Jobs ----

@bp.route("/jobs")
def jobs_page():
    rows = jobs.list_jobs()
    running = [row for row in rows if row["status"] == "running"]
    return render_template("jobs.html", jobs=rows, refresh=bool(running), keep_choices=jobs.KEEP_CHOICES, keep_days=jobs.keep_days())


@bp.route("/jobs/history", methods=["POST"])
def jobs_history():
    try:
        jobs.set_keep_days(int(request.form.get("keep_days", "")))
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.jobs_page"))


@bp.route("/jobs/<job_id>")
def job_page(job_id):
    job = jobs.job_summary(job_id)
    if job is None:
        abort(404)
    return render_template("job.html", job=job)


@bp.route("/jobs/<job_id>/log")
def job_log(job_id):
    return live_log(jobs.job_log(job_id, log_position()))


@bp.route("/jobs/<job_id>/input", methods=["POST"])
def job_input(job_id):
    try:
        jobs.send_input(job_id, request.form.get("text", ""))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"ok": True})


@bp.route("/jobs/<job_id>/cancel", methods=["POST"])
def job_cancel(job_id):
    jobs.cancel_job(job_id)
    return jsonify({"ok": True})


@bp.route("/jobs/<job_id>/dismiss", methods=["POST"])
def job_dismiss(job_id):
    jobs.dismiss("job", job_id)
    return jsonify({"ok": True})


@bp.route("/chains/<chain_id>/dismiss", methods=["POST"])
def chain_dismiss(chain_id):
    jobs.dismiss("chain", chain_id)
    return jsonify({"ok": True})


@bp.route("/chains/<chain_id>/continue", methods=["POST"])
def chain_continue(chain_id):
    try:
        jobs.continue_chain(chain_id, request.form.get("approve") == "yes")
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return run_panel(jobs.chain_summary(chain_id), url_for("console.chain_log", chain_id=chain_id))


@bp.route("/chains/<chain_id>/log")
def chain_log(chain_id):
    return live_log(jobs.chain_log(chain_id, log_position()))


# ---- Guide ----

@bp.route("/guide")
def guide_start():
    return redirect(url_for("console.guide_page", name="index"))


@bp.route("/guide/<name>")
def guide_page(name):
    page = documents.guide_page(name.removesuffix(".md"))
    if page is None:
        abort(404)
    return render_template("guide.html", page=page, guides=documents.guide_names())


# ---- Read ----

@bp.route("/read")
def read_page():
    port = SETTINGS["read_port"]
    return render_template(
        "read.html",
        job_id=jobs.running_service("pepa-read", "serve"),
        last=jobs.latest_job("pepa-read", "serve"),
        answering=port_is_open(port),
        url=f"http://{SETTINGS['host']}:{port}/",
    )


@bp.route("/read/start", methods=["POST"])
def read_start():
    already_running = jobs.running_service("pepa-read", "serve") is not None
    if not already_running and not port_is_open(SETTINGS["read_port"]):
        try:
            jobs.start_job("pepa-read", "serve", {"--port": str(SETTINGS["read_port"])})
        except ValueError as error:
            flash(str(error))
    return redirect(url_for("console.read_page"))


@bp.route("/read/stop", methods=["POST"])
def read_stop():
    job_id = jobs.running_service("pepa-read", "serve")
    if job_id is not None:
        jobs.cancel_job(job_id)
    return redirect(url_for("console.read_page"))


# ---- Folders ----

@bp.route("/folders")
def folders_page():
    return render_template(
        "folders.html",
        apps=folders.folder_pages(),
        project=str(paths.project_folder()),
        store=str(paths.store_file()),
    )


@bp.route("/folders/set", methods=["POST"])
def folders_set():
    app_name = request.form.get("app", "")
    slot = request.form.get("slot", "")
    try:
        if slot == "project":
            paths.set_project(request.form.get("path", ""))
            flash("Saved. Every app now keeps its own files in this folder.")
        else:
            paths.set_place(app_name, slot, request.form.get("path", ""))
            flash(folder_message(app_name, slot))
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.folders_page"))


@bp.route("/folders/subfolders", methods=["POST"])
def folders_subfolders():
    app_name = request.form.get("app", "")
    slot = request.form.get("slot", "")
    try:
        paths.set_subfolders(app_name, slot, request.form.get("wanted") == "on")
        flash(folder_message(app_name, slot))
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.folders_page"))


@bp.route("/folders/open", methods=["POST"])
def folders_open():
    try:
        paths.open_in_file_manager(request.form.get("path", ""))
    except ValueError as error:
        flash(str(error))
    return redirect(back_to(url_for("console.folders_page")))


@bp.route("/folders/browse")
def folders_browse():
    return jsonify(paths.browse(request.args.get("path", "")))


# ---- Models ----

@bp.route("/models")
def models_page():
    return render_template("models.html", page=models.page_view())


@bp.route("/models/save", methods=["POST"])
def models_save():
    try:
        models.save_choices(request.form)
        flash("Saved. The next run of each app uses these models.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.models_page"))


@bp.route("/models/list", methods=["POST"])
def models_list():
    try:
        names = models.list_models(request.form.get("app", ""), request.form.get("base_url", "").strip())
    except ValueError as error:
        return jsonify({"error": str(error)})
    if not names:
        return jsonify({"error": "The server lists no models. Download one first, for example with ollama pull."})
    return jsonify({"models": names})


# ---- Keys ----

@bp.route("/keys")
def keys_page():
    return render_template("keys.html", store=keys.page_view())


@bp.route("/keys/add", methods=["POST"])
def keys_add():
    form = request.form
    try:
        keys.add_key(form.get("name", ""), form.get("variable", ""), form.get("value", ""), form.get("everywhere") == "on")
        flash("Key saved.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.keys_page"))


@bp.route("/keys/delete", methods=["POST"])
def keys_delete():
    keys.delete_key(request.form.get("name", ""))
    flash("Key deleted.")
    return redirect(url_for("console.keys_page"))


@bp.route("/keys/assign", methods=["POST"])
def keys_assign():
    choices = []
    for field_name, value in request.form.items():
        parts = field_name.split("|")
        if len(parts) != 3 or parts[0] != "assign":
            continue
        choices.append({"app": parts[1], "variable": parts[2], "key": value})
    try:
        keys.save_assignments(choices)
        flash("Saved.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.keys_page"))
