"""List and read the literature reviews pepa-review writes, and start a new one from an outline.
The Reviews tab under Explore shows them.
"""
from datetime import datetime
from pathlib import Path

from web import documents, estimates, jobs, lists, maps

REVIEW_PATTERN = "review_*.md"
STRUCTURES = {
    "synthesise": "Find the sections in the papers",
    "follow": "Follow my outline",
}
TIME_FORMAT = "%Y-%m-%d %H:%M"


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
    """One review as HTML with its file name, or None when there is no such review."""
    path = maps.results_folder() / Path(name).name
    if not path.match(REVIEW_PATTERN) or not path.is_file():
        return None
    return {
        "file": path.name,
        "outline": path.stem.removeprefix("review_").rsplit("_", 2)[0],
        "html": documents.render_markdown(path.read_text(encoding="utf-8")),
    }


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


def start_review(text_path, list_name, structure):
    """Start pepa-review writing the review as a job, and return the job's id."""
    return jobs.start_job("pepa-review", "review", review_values(text_path, list_name, structure))
