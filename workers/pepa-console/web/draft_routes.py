"""Serve the Draft pages: outline, first draft, feedback and gap checks, each output beside what it came from.
Each paid step shows its cost first.
"""
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from web import drafting, jobs, word_export

bp = Blueprint("draft", __name__)
WORD_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# The inputs an action's form and estimate page pass along, besides its main text.
INPUT_NAMES = [
    "source",
    "literature",
    "review",
    "structure",
    "papers",
    "revise",
    "feedback",
]


def wanted_action(action):
    """The action an address names, or a 404 for one there is not."""
    if action not in drafting.ACTIONS:
        abort(404)
    return action


def wanted_inputs(values):
    """The inputs of an action, as a form or an address gives them."""
    inputs = {}
    for name in INPUT_NAMES:
        inputs[name] = values.get(name, "")
    return inputs


@bp.route("/draft")
def draft_home():
    return redirect(url_for("draft.action_page", action="outline"))


@bp.route("/draft/<action>")
def action_page(action):
    wanted_action(action)
    return render_template(
        "draft_action.html",
        action=action,
        info=drafting.ACTIONS[action],
        sources=drafting.choices(drafting.ACTIONS[action]["reads"]),
        reviews=drafting.choices(["review"]),
        prefill=wanted_inputs(request.args),
        papers=drafting.paper_choices(),
        skeletons=drafting.skeletons(),
        outputs=drafting.all_outputs(action),
        missing=drafting.missing_for(action),
        patterns_run=jobs.shown_job("pepa-plan", "abstract"),
    )


@bp.route("/draft/<action>", methods=["POST"])
def action_save(action):
    wanted_action(action)
    inputs = wanted_inputs(request.form)
    if inputs["revise"]:
        return redirect(url_for("draft.action_new", action=action, **inputs))
    try:
        inputs["source"] = drafting.keep_input(request.files.get("file"), request.form.get("pasted", ""), inputs["source"])
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("draft.action_page", action=action))
    return redirect(url_for("draft.action_new", action=action, **inputs))


@bp.route("/draft/<action>/new")
def action_new(action):
    wanted_action(action)
    inputs = wanted_inputs(request.args)
    try:
        estimate = drafting.action_estimate(action, inputs)
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("draft.action_page", action=action))
    return render_template(
        "draft_new.html",
        action=action,
        info=drafting.ACTIONS[action],
        inputs=inputs,
        made_from=[drafting.title_of(key) for key in drafting.input_keys(action, inputs)],
        papers=drafting.papers_label(inputs["papers"]),
        estimate=estimate,
    )


@bp.route("/draft/<action>/new", methods=["POST"])
def action_run(action):
    wanted_action(action)
    try:
        name = drafting.start_action(action, wanted_inputs(request.form))
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("draft.action_page", action=action))
    return redirect(url_for("draft.read_page", key=f"{action}:{name}"))


@bp.route("/draft/read")
def read_page():
    key = request.args.get("key", "")
    kind, _, name = key.partition(":")
    view = drafting.output_view(key)
    running = None
    if kind in drafting.ACTIONS:
        running = drafting.running_output(kind, name)
    if view is None and running is None:
        abort(404)
    shown = None
    if running is not None and view is None:
        shown = {"run": running, "log_url": url_for("console.job_log", job_id=running["id"])}
    return render_template("draft_read.html", view=view, kind=kind, kind_label=drafting.KINDS.get(kind, {}).get("label", ""), shown=shown)


@bp.route("/draft/word")
def word_download():
    key = request.args.get("key", "")
    path = drafting.source_path(key)
    if path is None:
        abort(404)
    title = drafting.title_of(key)
    text = drafting.reading_text(key)
    data = word_export.word_bytes(title, text)
    file_name = secure_filename(title) or "text"
    return Response(data, mimetype=WORD_TYPE, headers={"Content-Disposition": f'attachment; filename="{file_name}.docx"'})


@bp.route("/draft/structures")
def structures_page():
    return render_template("draft_structures.html", library=drafting.structure_library())


@bp.route("/draft/patterns")
def patterns_new():
    return render_template("draft_patterns.html", estimate=drafting.patterns_estimate())


@bp.route("/draft/patterns", methods=["POST"])
def patterns_run():
    estimate = drafting.patterns_estimate()
    if estimate is None:
        flash("pepa-plan could not say what learning the structures costs.")
        return redirect(url_for("draft.action_page", action="outline"))
    try:
        drafting.start_patterns(estimate["dollars"])
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("draft.action_page", action="outline"))
