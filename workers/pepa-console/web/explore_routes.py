"""Serve the Explore pages: search, maps, questions, find by document, reviews, citations, lists and papers.
Each paid step shows its cost, runs as a job, and is kept.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from web import (
    asking,
    citations,
    connections,
    documents,
    estimates,
    explore,
    folders,
    jobs,
    lists,
    maps,
    models,
    reviews,
)
from web.routes import item_count

bp = Blueprint("explore", __name__)
# Each Explore tab's name, by the part of its address after /explore/.
TAB_NAMES = {
    "map": "Map",
    "ask": "Ask",
    "document": "Find by document",
    "reviews": "Reviews",
    "citations": "Citations",
    "lists": "Lists",
}


# ---- Helpers ----

def missing_step(needs_embedding):
    """What a pepa-review step still lacks: "index", "models" or "keys", or "" when it can run.

    Args:
        needs_embedding: True for a step that embeds a question or an outline as it runs.
    """
    if not folders.index_built(folders.REVIEW_INDEX):
        return "index"
    if needs_embedding:
        missing = models.missing_choice("pepa-review", "embedding")
        if missing:
            return missing
    return models.missing_choice("pepa-review", "generation")


def shown_run(command_name):
    """The newest run of a pepa-review command its page still shows, with the address of its log, or None."""
    job = jobs.shown_job("pepa-review", command_name)
    if job is None:
        return None
    return {"run": job, "log_url": url_for("console.job_log", job_id=job["id"])}


def back_label(back):
    """The name of the Explore page a paper page was opened from, or "" when it was opened from elsewhere."""
    if not back.startswith("/explore"):
        return ""
    parts = back.split("?")[0].split("/")
    if len(parts) < 3:
        return "Search"
    return TAB_NAMES.get(parts[2], "Explore")


def wanted_list():
    """The literature list a page or form asks for, checked, or "" for the whole library."""
    name = request.values.get("list", "")
    if not name:
        return ""
    try:
        lists.list_path(name)
    except ValueError:
        abort(404)
    return name


# ---- Search ----

@bp.route("/explore")
def explore_page():
    wanted = explore.wanted_search(request.args)
    page = request.args.get("page", "1")
    asked = {name: text for name, text in wanted.items() if text}
    found = None
    if asked:
        found = explore.search(wanted, int(page) if page.isdigit() else 1)
    return render_template(
        "explore.html",
        wanted=wanted,
        asked=asked,
        advanced=any(name != "q" for name in asked),
        fields=explore.SEARCH_FIELDS,
        found=found,
        indexed=folders.index_built(folders.SEARCH_INDEX),
        lists=lists.all_lists(),
    )


# ---- Map ----

@bp.route("/explore/map")
def map_page():
    every_map = maps.all_maps()
    chosen = request.args.get("map") or (every_map[0]["file"] if every_map else "")
    field_map = maps.load_map(chosen) if chosen else None
    if chosen and field_map is None:
        abort(404)
    return render_template(
        "map.html",
        maps=every_map,
        field_map=field_map,
        cards=maps.theme_cards(field_map) if field_map else [],
        outliers=maps.named_papers(field_map.get("outliers", [])) if field_map else [],
        parent=maps.parent_map(field_map) if field_map else "",
        lists=lists.all_lists(),
        shown=shown_run("map"),
        missing=missing_step(False),
    )


@bp.route("/explore/map/new")
def map_new():
    list_name = wanted_list()
    flags = ["--list", str(lists.list_path(list_name))] if list_name else []
    return render_template("map_new.html", list_name=list_name, estimate=estimates.estimate("pepa-review", "map", flags))


@bp.route("/explore/map/new", methods=["POST"])
def map_make():
    list_name = wanted_list()
    values = {"--list": str(lists.list_path(list_name))} if list_name else {}
    try:
        jobs.start_job("pepa-review", "map", values)
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("explore.map_page"))


def theme_or_404():
    """The map and theme number a theme page's address names, or a 404 page."""
    field_map = maps.load_map(request.values.get("map", ""))
    theme_id = request.values.get("theme", "")
    if field_map is None or not theme_id.isdigit():
        abort(404)
    theme = maps.theme_view(field_map, int(theme_id))
    if theme is None:
        abort(404)
    return {"map": field_map, "theme": theme}


@bp.route("/explore/map/theme")
def theme_page():
    found = theme_or_404()
    return render_template(
        "theme.html",
        field_map=found["map"],
        theme=found["theme"],
        lists=lists.all_lists(),
        shown=shown_run("threadmap"),
    )


@bp.route("/explore/map/detail")
def theme_detail_new():
    found = theme_or_404()
    if not found["theme"]["can_detail"]:
        abort(404)
    flags = ["--map", found["map"]["file"], "--thread", str(found["theme"]["id"])]
    return render_template(
        "map_new.html",
        field_map=found["map"],
        theme=found["theme"],
        estimate=estimates.estimate("pepa-review", "threadmap", flags),
    )


@bp.route("/explore/map/detail", methods=["POST"])
def theme_detail_make():
    found = theme_or_404()
    values = {"--map": found["map"]["file"], "--thread": str(found["theme"]["id"])}
    try:
        jobs.start_job("pepa-review", "threadmap", values)
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("explore.theme_page", map=found["map"]["file"], theme=found["theme"]["id"]))


# ---- Ask ----

@bp.route("/explore/ask")
def ask_page():
    list_name = wanted_list()
    missing = missing_step(True)
    estimate = None
    if not missing:
        flags = ["--list", str(lists.list_path(list_name))] if list_name else []
        estimate = estimates.estimate("pepa-review", "ask", flags)
    return render_template(
        "ask.html",
        list_name=list_name,
        lists=lists.all_lists(),
        conversations=asking.conversations(),
        estimate=estimate,
        missing=missing,
    )


@bp.route("/explore/ask", methods=["POST"])
def ask_start():
    list_name = wanted_list()
    following_up = bool(request.form.get("conversation"))
    name = request.form.get("conversation") or asking.new_name()
    try:
        asking.start_question(request.form.get("question", ""), name, list_name)
    except ValueError as error:
        flash(str(error))
        if not following_up:
            return redirect(url_for("explore.ask_page", list=list_name))
    return redirect(url_for("explore.conversation_page", file=name))


@bp.route("/explore/ask/conversation")
def conversation_page():
    name = request.args.get("file", "")
    conversation = asking.conversation_view(name)
    running = asking.running_question(name)
    if conversation is None and running is None:
        abort(404)
    shown = None
    if running is not None:
        shown = {"run": running, "log_url": url_for("console.job_log", job_id=running["id"])}
    return render_template("conversation.html", name=name, conversation=conversation, shown=shown, lists=lists.all_lists())


# ---- Find by document ----

@bp.route("/explore/document")
def document_page():
    found = None
    if request.args.get("find"):
        found = explore.kept_find(request.args["find"])
        if found is None:
            abort(404)
    path = explore.saved_text(request.args.get("text", ""))
    return render_template(
        "document.html",
        found=found,
        text=path.name if path else "",
        estimate=explore.document_estimate(path) if path else None,
        earlier=explore.earlier_finds(),
        indexed=folders.index_built(folders.REVIEW_INDEX),
        missing=models.missing_choice("pepa-review", "embedding"),
        lists=lists.all_lists(),
    )


@bp.route("/explore/document", methods=["POST"])
def document_save():
    try:
        name = explore.save_text(request.files.get("file"), request.form.get("pasted", ""))
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("explore.document_page"))
    return redirect(url_for("explore.document_page", text=name))


@bp.route("/explore/document/find", methods=["POST"])
def document_find():
    path = explore.saved_text(request.form.get("text", ""))
    if path is None:
        abort(404)
    kept = explore.find_document(path)
    if kept is None:
        flash("pepa-review gave no answer. Run similar on its app page to see why.")
        return redirect(url_for("explore.document_page", text=path.name))
    return redirect(url_for("explore.document_page", find=kept))


# ---- Reviews ----

@bp.route("/explore/reviews")
def reviews_page():
    return render_template(
        "reviews.html",
        reviews=reviews.all_reviews(),
        list_name=wanted_list(),
        lists=lists.all_lists(),
        structures=reviews.STRUCTURES,
        shown=shown_run("review"),
        missing=missing_step(True),
    )


@bp.route("/explore/reviews", methods=["POST"])
def reviews_save():
    list_name = wanted_list()
    structure = request.form.get("structure", "")
    try:
        name = explore.save_text(request.files.get("file"), request.form.get("pasted", ""))
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("explore.reviews_page", list=list_name))
    return redirect(url_for("explore.review_new", text=name, list=list_name, structure=structure))


@bp.route("/explore/reviews/new")
def review_new():
    path = explore.saved_text(request.args.get("text", ""))
    if path is None:
        abort(404)
    list_name = wanted_list()
    structure = request.args.get("structure", "")
    try:
        estimate = reviews.review_estimate(path, list_name, structure)
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("explore.reviews_page", list=list_name))
    return render_template(
        "review_new.html",
        text=path.name,
        list_name=list_name,
        structure=structure,
        structure_label=reviews.STRUCTURES[structure],
        estimate=estimate,
    )


@bp.route("/explore/reviews/new", methods=["POST"])
def review_make():
    path = explore.saved_text(request.form.get("text", ""))
    if path is None:
        abort(404)
    try:
        reviews.start_review(path, wanted_list(), request.form.get("structure", ""))
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("explore.reviews_page"))


@bp.route("/explore/reviews/read")
def review_page():
    review = reviews.review_view(request.args.get("file", ""))
    if review is None:
        abort(404)
    return render_template("review.html", review=review)


# ---- Citations ----

@bp.route("/explore/citations")
def citations_page():
    return render_template(
        "citations.html",
        overview=citations.overview(),
        zotero=citations.zotero_file(),
        shown=shown_run("biblio"),
    )


@bp.route("/explore/citations/zotero", methods=["POST"])
def citations_zotero():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        flash("Choose a Zotero export first.")
        return redirect(url_for("explore.citations_page"))
    try:
        citations.save_zotero(upload)
        flash("Saved. The next lookup matches DOIs from this export.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("explore.citations_page"))


@bp.route("/explore/citations/new")
def citations_new():
    return render_template("citations_new.html", estimate=citations.lookup_estimate(), zotero=citations.zotero_file())


@bp.route("/explore/citations/new", methods=["POST"])
def citations_run():
    try:
        citations.start_lookup()
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("explore.citations_page"))


# ---- Papers ----

@bp.route("/paper")
def paper_page():
    stem = request.args.get("stem", "")
    view = documents.paper_view(stem, request.args.get("tab", ""))
    if view is None:
        abort(404)
    return render_template(
        "paper.html",
        view=view,
        name=connections.named(stem),
        book_name=connections.named(view["book"]),
        related=connections.related_papers(stem),
        themes=connections.themes_of(stem),
        theme_map=maps.newest_corpus_map(),
        facts=citations.paper_facts(stem),
        back=request.args.get("back", ""),
        back_label=back_label(request.args.get("back", "")),
        lists=lists.all_lists(),
    )


# ---- Lists ----

@bp.route("/explore/lists")
def lists_page():
    chosen = request.args.get("list", "")
    papers_in_list = None
    if chosen:
        try:
            papers_in_list = lists.list_papers(chosen)
        except ValueError:
            abort(404)
    return render_template("lists.html", lists=lists.all_lists(), chosen=chosen, papers=papers_in_list)


@bp.route("/lists/add", methods=["POST"])
def lists_add():
    back = request.form.get("back") or url_for("explore.lists_page")
    stems = request.form.getlist("stem") + lists.stems_of_pdfs(request.form.getlist("name"))
    target = request.form.get("new_list", "").strip() or request.form.get("list", "")
    if not stems:
        flash("Tick at least one item.")
        return redirect(back)
    try:
        added = lists.add_to_list(target, stems)
    except ValueError as error:
        flash(str(error))
        return redirect(back)
    if added:
        flash(f"Added {item_count(added)} to {target}.")
    else:
        flash(f"Already in {target}.")
    return redirect(back)


@bp.route("/lists/remove", methods=["POST"])
def lists_remove():
    name = request.form.get("list", "")
    try:
        lists.remove_from_list(name, request.form.get("stem", ""))
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("explore.lists_page", list=name))


@bp.route("/lists/delete", methods=["POST"])
def lists_delete():
    name = request.form.get("list", "")
    try:
        lists.delete_list(name)
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("explore.lists_page"))
    flash(f"Deleted the list {name}.")
    return redirect(url_for("explore.lists_page"))
