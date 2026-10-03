"""Serve the web console's pages and form actions. Each handler reads the registry, folders,
jobs, or key store, then renders a template, answers with JSON, or redirects.
"""
import socket
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
    url_for,
)

from registry import get_app
from web import documents, folders, jobs, keys, mascot, models, options, paths
from web.settings import SETTINGS

PIPELINE_STEPS = [
    {"app": "pepa-prep", "command": "extract", "label": "Prepare PDFs", "paid": False},
    {"app": "pepa-sum", "command": "summarize", "label": "Summarise", "paid": True},
    {"app": "pepa-read", "command": "index", "label": "Update search index", "paid": False},
    {"app": "pepa-review", "command": "index", "label": "Update review index", "paid": True},
]

PDF_APPS = [
    "pepa-prep",
    "pepa-sum",
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

# A page or drawing an app wrote may carry its own script; it runs walled off from the console.
WALLED_SUFFIXES = [
    ".html",
    ".svg",
]
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


def copy_message(result):
    """A short line saying how many files were copied, into which folder, and what was left out."""
    message = f"Copied {len(result['copied'])} file(s) into {result['folder']}."
    if result["left_out"]:
        message += f" Left out {len(result['left_out'])}: already there or not accepted."
    return message


def folder_message(app_name, slot):
    """What was saved, and how many papers sit in sub-folders the app is not reading."""
    if not paths.can_scan_subfolders(app_name, slot):
        return "Saved."
    count = folders.paper_counts(app_name, slot)
    here = folders.counted(count["here"], count["capped"])
    deeper = folders.counted(count["deeper"], count["capped"])
    if not count["deeper"]:
        return f"Saved. {here} paper(s) in that folder."
    if paths.scans_subfolders(app_name, slot):
        return f"Saved. {here} paper(s) there and {deeper} in sub-folders, all of them read."
    return f"Saved. {here} paper(s) there and {deeper} in sub-folders, which stay unread until you turn on Scan sub-folders."


def back_to(default):
    """The page a form asks to return to, or the given page when it asks for nothing sensible."""
    wanted = request.form.get("back", "")
    if wanted.startswith("/") and not wanted.startswith("//"):
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
def pipeline():
    chains = jobs.list_chains()
    latest = chains[0] if chains else None
    summary = folders.pipeline_summary()
    nothing_yet = summary["pdfs"] == 0 and summary["summarised"] == 0
    return render_template(
        "pipeline.html",
        summary=summary,
        steps=PIPELINE_STEPS,
        chain=latest,
        first_run=nothing_yet and not keys.load_store()["keys"],
    )


@bp.route("/pipeline/copy", methods=["POST"])
def pipeline_copy():
    files = folders.picked_files(request.files.getlist("pdfs"))
    lines = []
    for app_name in PDF_APPS:
        try:
            lines.append(copy_message(folders.copy_into(app_name, "sources", files, ".pdf")))
        except ValueError as error:
            lines.append(str(error))
    flash(" ".join(lines))
    return redirect(url_for("console.pipeline"))


@bp.route("/pipeline/run", methods=["POST"])
def pipeline_run():
    ticked = request.form.getlist("step")
    steps = [step for step in PIPELINE_STEPS if f"{step['app']} {step['command']}" in ticked]
    if not steps:
        return jsonify({"error": "Tick at least one step."}), 400
    chain_id = jobs.start_chain(steps)
    return run_panel(jobs.chain_summary(chain_id), url_for("console.chain_log", chain_id=chain_id))


# ---- Apps ----

@bp.route("/apps")
def apps_page():  # lint-style: ignore MD001
    return render_template("apps.html")


@bp.route("/apps/<name>")
def app_page(name):
    app = find_app(name)
    latest = {}
    for command in app.commands:
        latest[command.name] = jobs.latest_job(name, command.name)
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
        flash(copy_message(folders.copy_into(name, request.form.get("slot", ""), files, "")))
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.app_page", name=name))


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
    if path.suffix.lower() in WALLED_SUFFIXES:
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
    return render_template("jobs.html", jobs=rows, chains=jobs.list_chains(), refresh=bool(running))


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
