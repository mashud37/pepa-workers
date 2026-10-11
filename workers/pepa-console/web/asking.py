"""Read the conversations pepa-review's ask command keeps, and start each new question as a job.
The Ask tab under Explore lists, shows and continues them.
"""
import json
from datetime import datetime
from pathlib import Path

from web import documents, jobs, lists, maps

CONVERSATION_PATTERN = "ask_*.json"
CONVERSATION_NAME = "ask_%Y%m%d_%H%M%S.json"


def conversations():
    """Every kept conversation, newest first, with its first question, its list and how many questions it holds."""
    folder = maps.results_folder()
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob(CONVERSATION_PATTERN), key=lambda path: path.stat().st_mtime, reverse=True):
        conversation = json.loads(path.read_text(encoding="utf-8"))
        found.append({
            "file": path.name,
            "title": conversation["title"],
            "list": conversation["list"],
            "questions": len(conversation["turns"]),
            "when": conversation["turns"][-1]["when"].replace("T", " ")[:16],
        })
    return found


def conversation_view(name):
    """One conversation with each answer as HTML and its papers named, or None when it does not exist yet."""
    path = maps.results_folder() / Path(name).name
    if not path.match(CONVERSATION_PATTERN) or not path.is_file():
        return None
    conversation = json.loads(path.read_text(encoding="utf-8"))
    turns = []
    for turn in conversation["turns"]:
        turns.append({
            "question": turn["question"],
            "answer": documents.render_markdown(turn["answer"]),
            "when": turn["when"].replace("T", " ")[:16],
        })
    return {
        "file": path.name,
        "title": conversation["title"],
        "list": conversation["list"],
        "turns": turns,
        "papers": maps.named_papers(conversation["works"]),
    }


def new_name():
    """A file name for a new conversation, from the time it starts."""
    return datetime.now().strftime(CONVERSATION_NAME)


def start_question(question, conversation_name, list_name):
    """Start pepa-review answering one question as a job, and return the job's id.

    Raises:
        ValueError: no question, or a list name that is not allowed.
    """
    if not question.strip():
        raise ValueError("Write a question first.")
    values = {"--question": question.strip(), "--conversation": Path(conversation_name).name}
    if list_name:
        values["--list"] = str(lists.list_path(list_name))
    return jobs.start_job("pepa-review", "ask", values)


def running_question(conversation_name):
    """The newest question job for this conversation that its page still shows, or None."""
    job = jobs.shown_job("pepa-review", "ask")
    if job is None or conversation_name not in job["shown"]:
        return None
    return job

