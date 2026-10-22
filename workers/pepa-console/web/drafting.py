"""Start and read the Draft page's outlines, first drafts, feedback and gap reports, each with what it was made from.
The Draft tab lists them as the next step's inputs.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from registry import get_command
from web import documents, estimates, explore, folders, jobs, lists, maps, models, paths

# Every kind of text the Draft page works on or writes: its name, the worker that writes it, and its files.
KINDS = {
    "text": {"label": "Your text", "app": "", "pattern": "*.md"},
    "outline": {"label": "Outline", "app": "pepa-plan", "pattern": "outline_*.md"},
    "draft": {"label": "First draft", "app": "pepa-draft", "pattern": "manuscript_*.md"},
    "feedback": {"label": "Feedback", "app": "pepa-plan", "pattern": "feedback_*.md"},
    "gaps": {"label": "Gap report", "app": "pepa-review", "pattern": "gaps_*.md"},
    "review": {"label": "Literature review", "app": "pepa-review", "pattern": "review_*.md"},
}
# The four actions, each a tab: the command that runs it, and the kinds of text its main input can be.
ACTIONS = {
    "outline": {"title": "Outline", "app": "pepa-plan", "command": "outline", "reads": ["text", "draft"], "slot": "Your idea"},
    "draft": {"title": "First draft", "app": "pepa-draft", "command": "draft", "reads": ["outline"], "slot": "Outline"},
    "feedback": {"title": "Feedback", "app": "pepa-plan", "command": "review", "reads": ["text", "outline", "draft"], "slot": "Text"},
    "gaps": {"title": "Check for gaps", "app": "pepa-review", "command": "gaps", "reads": ["text", "draft", "outline"], "slot": "Text"},
}
# What each kind of text can go on to, as the actions offered beside it.
NEXT_ACTIONS = {
    "text": ["outline", "feedback", "gaps"],
    "outline": ["draft", "feedback"],
    "draft": ["feedback", "gaps"],
    "review": ["outline", "draft"],
}
MADE_FROM_FILE = Path("pepa-console") / "made_from.json"
THEMES_FOLDER = Path("pepa-console") / "themes"
SKELETONS_FILE = Path("pepa-plan") / "data" / "skeletons.json"
BLUEPRINTS_FILE = Path("pepa-plan") / "data" / "blueprints.json"
# An outline line's move tag, "[GAP]:" or "[GAP] -", which pepa-draft reads and a reader sees in plain words.
MOVE_TAG = re.compile(r"\[([A-Z_]+)\]\s*[:\-]?")
# pepa-plan's move labels in plain words.
MOVE_NAMES = {
    "HOOK_PROBLEM": "Opening problem",
    "BACKGROUND": "Background",
    "GAP": "Gap",
    "THESIS_AIM": "Aim",
    "CONTRIBUTION_PREVIEW": "Contribution",
    "ROADMAP": "Roadmap",
    "LIT_POSITIONING": "Place in the literature",
    "THEORY_CONCEPT": "Theory and concepts",
    "METHOD": "Method",
    "DATA_SETTING": "Data and setting",
    "ANALYSIS_FINDING": "Findings",
    "INTERPRETATION": "Interpretation",
    "COUNTERPOINT_LIMITATION": "Counterpoints and limits",
    "IMPLICATION": "Implications",
    "FUTURE_WORK": "Future work",
    "CONCLUSION": "Conclusion",
    "OTHER": "Other",
}
TIME_FORMAT = "%d %b %Y, %H:%M"
NAME_TIME = "%Y%m%d_%H%M%S"
# Where a gap report starts the papers it names; the page shows them beside the report instead.
RANKED_HEADING = "## Raw ranked candidates"


# ---- Texts and outputs ----

def folder_of(kind):
    """The folder a kind of text is kept in."""
    if kind == "text":
        return explore.texts_folder()
    return paths.chosen(KINDS[kind]["app"], "results")


def source_path(key):
    """The file a source key like "outline:outline_20261012_101500.md" names, or None when there is no such file."""
    kind, _, name = key.partition(":")
    if kind not in KINDS or not name:
        return None
    path = folder_of(kind) / Path(name).name
    if not path.match(KINDS[kind]["pattern"]) or not path.is_file():
        return None
    return path


def load_made_from():
    """What every output was made from, by file name: {"kind", "inputs", "papers"}."""
    path = paths.project_folder() / MADE_FROM_FILE
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def record_made_from(name, kind, inputs, papers):
    """Remember what the output `name` is made from: its input source keys and the papers it was checked against."""
    records = load_made_from()
    records[name] = {"kind": kind, "inputs": inputs, "papers": papers}
    paths.write_json(paths.project_folder() / MADE_FROM_FILE, records)


def title_of(key):
    """A short name for a source: a text's file name, or an output's kind and what it was made from."""
    kind, _, name = key.partition(":")
    if kind == "text":
        return Path(name).stem
    if kind == "review":
        return "Review of " + name.removeprefix("review_").rsplit("_", 2)[0]
    record = load_made_from().get(name)
    if record and record["inputs"]:
        return f"{KINDS[kind]['label']} from {origin_title(record['inputs'][0])}"
    stamp = "_".join(Path(name).stem.split("_")[-2:])
    try:
        when = datetime.strptime(stamp, NAME_TIME).strftime(TIME_FORMAT)
    except ValueError:
        return f"{KINDS[kind]['label']} {name}"
    return f"{KINDS[kind]['label']} of {when}"


def origin_title(key):
    """The name of the text a chain of outputs started from, so a draft of an outline of an idea is named after the idea."""
    records = load_made_from()
    while True:
        kind, _, name = key.partition(":")
        record = records.get(name)
        if kind in ["text", "review"] or not record or not record["inputs"]:
            return title_of(key)
        key = record["inputs"][0]


def choices(kinds):
    """Every kept text of the given kinds, newest first, as {"key", "label", "when"} for a dropdown."""
    found = []
    for kind in kinds:
        folder = folder_of(kind)
        if not folder.is_dir():
            continue
        for path in folder.glob(KINDS[kind]["pattern"]):
            found.append({"key": f"{kind}:{path.name}", "stamp": path.stat().st_mtime})
    found.sort(key=lambda each: each["stamp"], reverse=True)
    for each in found:
        each["label"] = title_of(each["key"])
        each["when"] = datetime.fromtimestamp(each["stamp"]).strftime(TIME_FORMAT)
    return found


def all_outputs(kind):
    """Every output of one action, newest first, with what it was made from."""
    outputs = []
    for each in choices([kind]):
        name = each["key"].partition(":")[2]
        record = load_made_from().get(name, {"inputs": []})
        outputs.append({
            "file": name,
            "when": each["when"],
            "made_from": [title_of(key) for key in record["inputs"]],
        })
    return outputs


def keep_input(upload, pasted, chosen):
    """The source key of a step's main input: a new text kept from a file or paste, else the one chosen.

    Raises:
        ValueError: no text given or chosen, or a file of a kind that holds no plain text.
    """
    if (upload is not None and upload.filename) or pasted.strip():
        return "text:" + explore.save_text(upload, pasted)
    if source_path(chosen) is None:
        raise ValueError("Paste a text, choose a file, or pick one you have.")
    return chosen


# ---- Papers to check against ----

def paper_choices():
    """The papers a gap check can use besides everything: each list, and each theme of the newest map."""
    found = []
    for each in lists.all_lists():
        found.append({"value": f"list:{each['name']}", "label": each["name"], "detail": f"A list, {each['count']} papers"})
    newest = maps.newest_corpus_map()
    if newest:
        for thread in maps.load_map(newest)["threads"]:
            found.append({"value": f"theme:{thread['id']}", "label": thread["name"], "detail": f"A theme, {len(thread['bases'])} papers"})
    return found


def papers_file(papers):
    """The list file a gap check reads for `papers` ("list:name" or "theme:id"), or None for everything.

    A theme's papers are written to a list file of their own first.

    Raises:
        ValueError: a list name that is not allowed, or a theme the newest map does not have.
    """
    kind, _, name = papers.partition(":")
    if kind == "list":
        return lists.list_path(name)
    if kind != "theme":
        return None
    newest = maps.newest_corpus_map()
    threads = []
    if newest:
        threads = maps.load_map(newest)["threads"]
    for thread in threads:
        if str(thread["id"]) == name:
            path = paths.project_folder() / THEMES_FOLDER / f"{Path(newest).stem}_{name}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(f"{base}\n" for base in thread["bases"]), encoding="utf-8")
            return path
    raise ValueError("That theme is no longer on the newest map.")


def papers_label(papers):
    """What a gap check was checked against, in words."""
    for each in paper_choices():
        if each["value"] == papers:
            return each["label"]
    return "Everything"


# ---- Learned structures ----

def skeletons():
    """The paper structures pepa-plan has learned from the library, as {"id", "name", "kind"}, or [] before it has."""
    path = paths.project_folder() / SKELETONS_FILE
    if not path.is_file():
        return []
    library = json.loads(path.read_text(encoding="utf-8"))
    found = []
    for skeleton in library.get("skeletons", []):
        found.append({"id": skeleton["id"], "name": skeleton.get("name", skeleton["id"]), "kind": skeleton.get("paper_type", "")})
    return found


def move_name(move):
    """A move's name in plain words, such as "Findings" for ANALYSIS_FINDING."""
    if move in MOVE_NAMES:
        return MOVE_NAMES[move]
    return move.replace("_", " ").capitalize()


def structure_sections(blueprints):
    """How each major part of one structure usually runs, from its blueprints: {"name", "reads_like", "steps"}."""
    sections = []
    for move, blueprint in blueprints.items():
        steps = []
        for step in blueprint.get("progression", []):
            steps.append({"name": move_name(step.get("sub_move", "")), "intent": step.get("intent", "")})
        sections.append({"name": move_name(move), "reads_like": blueprint.get("reads_like", ""), "steps": steps})
    return sections


def structure_library():
    """Every learned structure in full for the Structures page: its moves and their shares, how its main parts run, and papers that follow it.

    Returns:
        dict with "papers", the count learned from, "when", and "structures", [] before any are learned.
    """
    path = paths.project_folder() / SKELETONS_FILE
    if not path.is_file():
        return {"papers": 0, "when": "", "structures": []}
    library = json.loads(path.read_text(encoding="utf-8"))
    blueprints = {}
    blueprints_path = paths.project_folder() / BLUEPRINTS_FILE
    if blueprints_path.is_file():
        blueprints = json.loads(blueprints_path.read_text(encoding="utf-8")).get("blueprints", {})
    when = ""
    if library.get("generated"):
        when = datetime.fromisoformat(library["generated"]).strftime(TIME_FORMAT)
    structures = []
    for skeleton in library.get("skeletons", []):
        stages = []
        for stage in skeleton.get("stages", []):
            share = round(100 * float(stage.get("typical_share", 0) or 0))
            stages.append({"name": move_name(stage.get("move", "")), "share": share, "intent": stage.get("intent", "")})
        structures.append({
            "id": skeleton["id"],
            "name": skeleton.get("name", skeleton["id"]),
            "kind": skeleton.get("paper_type", ""),
            "description": skeleton.get("description", ""),
            "stages": stages,
            "sections": structure_sections(blueprints.get(skeleton["id"], {})),
            "examples": maps.named_papers(skeleton.get("example_bases", [])),
        })
    return {"papers": library.get("n_papers", 0), "when": when, "structures": structures}


def patterns_estimate():
    """What learning the field's structures would cost, worded, or None when pepa-plan could not say."""
    reply = jobs.json_reply("pepa-plan", "abstract", ["--estimate"])
    if reply is None:
        return None
    mode = reply["auto"]
    labelling = reply["cost"][mode]
    if labelling is None or reply["blueprints"] is None:
        return {"papers": reply["papers"], "dollars": None, "words": f"{reply['papers']:,} papers to read with {reply['model']}, whose price is not known here."}
    dollars = labelling + reply["blueprints"]
    if reply["papers"] == 0:
        return {"papers": 0, "dollars": dollars, "words": "Every paper has been read for its structure already."}
    words = f"{reply['papers']:,} papers to read with {reply['model']}: {estimates.dollars_words(dollars).replace('about', 'at most')} at list price."
    return {"papers": reply["papers"], "dollars": dollars, "words": words}


def start_patterns(dollars):
    """Start pepa-plan learning the field's structures, spending no more than `dollars`, and return the job's id."""
    values = {"--with-blueprints": "on"}
    if dollars is not None:
        values["--approve-cost"] = f"{dollars + 0.01:.2f}"
    return jobs.start_job("pepa-plan", "abstract", values)


# ---- Running an action ----

def missing_for(action):
    """What an action still lacks before it can run: "index", "models", "keys", or ""."""
    app = ACTIONS[action]["app"]
    if action == "gaps":
        if not folders.index_built(folders.REVIEW_INDEX):
            return "index"
        missing = models.missing_choice(app, "embedding")
        if missing:
            return missing
    return models.missing_choice(app, "generation")


def job_values(action, inputs):
    """The form values an action's job runs with, from its inputs.

    Args:
        inputs: "source" (a source key), and as the action needs: "literature" or "review" (a review's
            source key), "structure" (a skeleton id, or "" for none), "papers", "revise" and "feedback".

    Raises:
        ValueError: a missing or unknown input.
    """
    main = source_path(inputs.get("source", ""))
    if action == "outline" and inputs.get("revise"):
        revised = source_path(inputs["revise"])
        if revised is None or not inputs.get("feedback", "").strip():
            raise ValueError("Say what to change in the outline.")
        return {"--revise": str(revised), "--feedback": inputs["feedback"].strip()}
    if main is None:
        raise ValueError("Choose what to work on first.")
    if action == "outline":
        values = {"--input": str(main)}
        literature = source_path(inputs.get("literature", ""))
        if literature is not None:
            values["--literature"] = str(literature)
        if inputs.get("structure"):
            values["--skeleton-id"] = inputs["structure"]
        else:
            values["--no-skeleton"] = "on"
        return values
    if action == "draft":
        review = source_path(inputs.get("review", ""))
        if review is None:
            raise ValueError("Choose the literature review the draft draws on.")
        return {"--plan": str(main), "--review": str(review), "--accept-sections": "on"}
    values = {"--input": str(main)}
    if action == "gaps":
        papers = papers_file(inputs.get("papers", ""))
        if papers is not None:
            values["--list"] = str(papers)
    return values


def action_estimate(action, inputs):
    """What an action will cost, as the worker's estimate plus "words", or None when the worker could not say."""
    values = job_values(action, inputs)
    command = get_command(ACTIONS[action]["app"], ACTIONS[action]["command"])
    return estimates.estimate(ACTIONS[action]["app"], ACTIONS[action]["command"], jobs.form_flags(command, values))


def input_keys(action, inputs):
    """The source keys an action's output is made from, main input first."""
    keys = []
    for name in ["revise", "source", "literature", "review"]:
        if source_path(inputs.get(name, "")) is not None:
            keys.append(inputs[name])
    return keys


def start_action(action, inputs):
    """Start an action as a job writing a new file, remember what it is made from, and return the file's name."""
    values = job_values(action, inputs)
    prefix = KINDS[action]["pattern"].removesuffix("*.md")
    name = f"{prefix}{datetime.now().strftime(NAME_TIME)}.md"
    values["--output"] = name
    jobs.start_job(ACTIONS[action]["app"], ACTIONS[action]["command"], values)
    papers = papers_label(inputs.get("papers", "")) if action == "gaps" else ""
    record_made_from(name, action, input_keys(action, inputs), papers)
    return name


def running_output(kind, name):
    """The job still writing this output that its page shows, or None."""
    job = jobs.shown_job(ACTIONS[kind]["app"], ACTIONS[kind]["command"])
    if job is None or name not in job["shown"]:
        return None
    return job


# ---- Reading an output ----

def named_works(path):
    """The papers an output names in the .json beside it, by name, or [] when it has none."""
    works_file = path.with_suffix(".json")
    if not works_file.is_file():
        return []
    return maps.named_papers(json.loads(works_file.read_text(encoding="utf-8"))["works"])


def plain_move(match):
    """One outline tag such as "[ANALYSIS_FINDING]:" as its move in bold plain words."""
    return f"**{move_name(match.group(1))}:**"


def reading_text(key):
    """The text of an output or text as a reader wants it: an outline's move tags in plain words, a gap report without
    the raw ranking its papers list replaces."""
    path = source_path(key)
    text = path.read_text(encoding="utf-8")
    if key.startswith("outline:"):
        text = MOVE_TAG.sub(plain_move, text)
    if key.startswith("gaps:") and path.with_suffix(".json").is_file():
        text = text.partition(RANKED_HEADING)[0]
    return text


def output_view(key):
    """One output or text as HTML, with what it was made from, the papers it names and what can follow, or None."""
    path = source_path(key)
    if path is None:
        return None
    kind = key.partition(":")[0]
    text = reading_text(key)
    papers = named_works(path)
    record = load_made_from().get(path.name, {"inputs": [], "papers": ""})
    made_from = []
    for input_key in record["inputs"]:
        made_from.append({"key": input_key, "kind": KINDS[input_key.partition(":")[0]]["label"], "title": title_of(input_key)})
        if not papers and input_key.startswith("review:") and source_path(input_key) is not None:
            papers = named_works(source_path(input_key))
    return {
        "key": key,
        "kind": kind,
        "kind_label": KINDS[kind]["label"],
        "file": path.name,
        "title": title_of(key),
        "html": documents.render_markdown(text),
        "made_from": made_from,
        "checked_against": record["papers"],
        "papers": papers,
        "next": [{"action": action, "title": ACTIONS[action]["title"]} for action in NEXT_ACTIONS.get(kind, [])],
    }
