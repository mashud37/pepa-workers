"""List and read the literature reviews pepa-review writes, and start a new one from an outline.
The Reviews tab under Explore shows them.
"""
import json
from datetime import datetime
from pathlib import Path

from web import documents, estimates, jobs, lists, maps

REVIEW_PATTERN = "review_*.md"
STRUCTURES = {
    "synthesise": "Find the sections in the papers",
    "follow": "Follow my outline",
}
TIME_FORMAT = "%Y-%m-%d %H:%M"
NAME_TIME = "%Y%m%d_%H%M%S"
# Where pepa-review starts the list of works a review drew on; the page shows them beside the review instead.
WORKS_HEADING = "\n\n---\n\n## Works drawn on"


def all_reviews():
    """Every review pepa-review has written, newest first, named by the outline it was written from."""
    folder = maps.results_folder()
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob(REVIEW_PATTERN), key=lambda path: path.stat().st_mtime, reverse=True):
        outline = path.stem.removeprefix("review_").rsplit("_", 2)[0]
        found.append({
            "file": path.name,
            "outline": outline,
            "when": datetime.fromtimestamp(path.stat().st_mtime).strftime(TIME_FORMAT),
        })
    return found


def review_view(name):
    """One review as HTML with the papers it drew on named, or None when there is no such review yet."""
    path = maps.results_folder() / Path(name).name
    if not path.match(REVIEW_PATTERN) or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    papers = []
    works_file = path.with_suffix(".json")
    if works_file.is_file():
        papers = maps.named_papers(json.loads(works_file.read_text(encoding="utf-8"))["works"])
        text = text.partition(WORKS_HEADING)[0]
    return {
        "file": path.name,
        "outline": path.stem.removeprefix("review_").rsplit("_", 2)[0],
        "html": documents.render_markdown(text),
        "papers": papers,
    }


def new_name(text_path):
    """A file name for a new review, from the outline's name and the time it starts."""
    return f"review_{text_path.stem}_{datetime.now().strftime(NAME_TIME)}.md"


def running_review(name):
    """The newest review job writing this review that its page still shows, or None."""
    job = jobs.shown_job("pepa-review", "review")
    if job is None or name not in job["shown"]:
        return None
    return job


def review_values(text_path, list_name, structure):
    """The form values a review job runs with: the outline, the papers and the structure.

    Raises:
        ValueError: an unknown structure, or a list name that is not allowed.
    """
    if structure not in STRUCTURES:
        raise ValueError("Choose how the review is structured.")
    values = {"--input": str(text_path), "--structure": structure}
    if list_name:
        values["--list"] = str(lists.list_path(list_name))
    else:
        values["--auto"] = "on"
    return values


def review_estimate(text_path, list_name, structure):
    """What a review will cost, worded, or None when pepa-review could not say."""
    values = review_values(text_path, list_name, structure)
    flags = ["--input", values["--input"], "--structure", structure]
    if "--list" in values:
        flags = flags + ["--list", values["--list"]]
    return estimates.estimate("pepa-review", "review", flags)


def start_review(text_path, list_name, structure, name):
    """Start pepa-review writing the review into the file `name` as a job, and return the job's id."""
    values = review_values(text_path, list_name, structure)
    values["--output"] = name
    return jobs.start_job("pepa-review", "review", values)
