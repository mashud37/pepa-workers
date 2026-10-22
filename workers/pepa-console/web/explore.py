"""Search the library through pepa-read, and find the papers closest to a text through pepa-review.
The Explore page lists both; each result opens its paper page.
"""
import json
import math
from datetime import datetime
from pathlib import Path

from werkzeug.utils import secure_filename

from web import connections, documents, estimates, jobs, paths

SEARCH_PAGE_SIZE = 20
# Advanced search: each box looks in one part of a brief, by the name pepa-read gives that part.
SEARCH_FIELDS = [
    {"name": "title", "label": "Title"},
    {"name": "context", "label": "Question and context"},
    {"name": "empirical", "label": "Empirical context"},
    {"name": "lit", "label": "Literature drawn on"},
    {"name": "methods", "label": "Methods"},
    {"name": "arguments", "label": "Arguments"},
    {"name": "conclusions", "label": "Key conclusions"},
    {"name": "discussion", "label": "Discussion items"},
]
# The user's own texts, kept in the project so every worker that takes a text can be handed one.
TEXTS_FOLDER = Path("pepa-console") / "texts"
TEXT_SUFFIXES = [
    ".md",
    ".txt",
    ".docx",
]
PASTED_NAME = "Pasted %Y-%m-%d %H%M%S"
PASTED_NAME_WORDS = 8
FIND_PATTERN = "similar_*.json"


def snippet_parts(snippet):
    """A search snippet as plain and matched pieces; pepa-read wraps each matched word in square brackets."""
    pieces = snippet.split("[")
    parts = [{"text": pieces[0], "matched": False}]
    for piece in pieces[1:]:
        matched, _, plain = piece.partition("]")
        parts.append({"text": matched, "matched": True})
        parts.append({"text": plain, "matched": False})
    return parts


def wanted_search(form):
    """What a search asks for, from the page's address: the plain words, the author, and each brief part's words."""
    wanted = {"q": form.get("q", "").strip(), "author": form.get("author", "").strip()}
    for field in SEARCH_FIELDS:
        wanted[field["name"]] = form.get(field["name"], "").strip()
    return wanted


def field_terms(name, text):
    """A box's words as pepa-read's `part:word` terms.

    Anything but a letter or digit splits words, as the index does; a lone letter left over, such as
    the s of "Hall's", is dropped, since it would ask for an s of its own.
    """
    spaced = ""
    for character in text:
        spaced += character if character.isalnum() else " "
    terms = []
    for word in spaced.split():
        if len(word) > 1:
            terms.append(f"{name}:{word}")
    return " ".join(terms)


def search(wanted, page):
    """One page of pepa-read's results for what `wanted_search` read.

    Returns:
        dict with "results", "total", "page" and "pages", and "failed", True when pepa-read gave no
        answer, as it does for a query it cannot read or when there is no search index yet.
    """
    query = wanted["q"]
    for field in SEARCH_FIELDS:
        query = query + " " + field_terms(field["name"], wanted[field["name"]])
    offset = (page - 1) * SEARCH_PAGE_SIZE
    flags = ["--json", "--limit", str(SEARCH_PAGE_SIZE), "--offset", str(offset)]
    if wanted["author"]:
        flags = flags + ["--author", wanted["author"].replace('"', "")]
    flags = flags + ["--", query.strip()]
    reply = jobs.json_reply("pepa-read", "search", flags)
    if reply is None:
        return {"results": [], "total": 0, "page": page, "pages": 0, "failed": True}
    results = []
    for found in reply["results"]:
        stem = documents.paper_stem(found["text_path"] or found["sum_path"])
        name = connections.named(stem)
        results.append({
            "stem": stem,
            "title": name["title"],
            "authors": name["authors"],
            "parts": snippet_parts(found["snippet"]),
            "summarised": found["has_sum"],
        })
    return {
        "results": results,
        "total": reply["total"],
        "page": page,
        "pages": math.ceil(reply["total"] / SEARCH_PAGE_SIZE),
        "failed": False,
    }


# ---- Find by document ----

def texts_folder():
    """Where the user's own texts are kept, made on first use."""
    folder = paths.project_folder() / TEXTS_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def pasted_name(text):
    """A new file name for pasted text, from its first words, or from the time when it has none."""
    words = []
    for word in text.split():
        cleaned = "".join(letter for letter in word if letter.isalnum() or letter in "-'")
        if cleaned:
            words.append(cleaned)
        if len(words) == PASTED_NAME_WORDS:
            break
    if not words:
        return datetime.now().strftime(PASTED_NAME) + ".md"
    stem = " ".join(words)
    name = stem + ".md"
    number = 2
    while (texts_folder() / name).exists():
        name = f"{stem} {number}.md"
        number += 1
    return name


def save_text(upload, pasted):
    """Keep an uploaded file or pasted text as markdown among the user's texts, and return its file name.

    Raises:
        ValueError: neither a file nor any text, or a file of a kind that holds no plain text.
    """
    folder = texts_folder()
    if upload is not None and upload.filename:
        name = secure_filename(upload.filename)
        suffix = Path(name).suffix.lower()
        if suffix not in TEXT_SUFFIXES:
            raise ValueError("Choose a .md, .txt or .docx file.")
        upload.save(folder / name)
        if suffix != ".docx":
            return name
        text = documents.docx_text(folder / name)
        (folder / name).unlink()
        name = Path(name).stem + ".md"
    elif pasted.strip():
        text = pasted
        name = pasted_name(pasted)
    else:
        raise ValueError("Paste a text or choose a file first.")
    (folder / name).write_text(text, encoding="utf-8")
    return name


def saved_text(name):
    """The path of one of the user's texts by its file name, or None when there is no such text."""
    path = texts_folder() / Path(name).name
    if not name or not path.is_file():
        return None
    return path


def document_estimate(path):
    """The embedding a text needs, worded, or None when pepa-review could not say."""
    reply = jobs.json_reply("pepa-review", "similar", ["--input", str(path), "--estimate"])
    if reply is None:
        return None
    return {"pieces": reply["pieces"], "words": estimates.cost_words(reply)}


def find_document(path):
    """Have pepa-review find the papers closest to a text, and return the name of the file it kept them in, or None when it gave no answer."""
    reply = jobs.json_reply("pepa-review", "similar", ["--input", str(path), "--json"])
    if reply is None:
        return None
    return reply["saved"]


def finds_folder():
    """Where pepa-review keeps every Find by document run."""
    return paths.chosen("pepa-review", "results")


def earlier_finds():
    """Every kept Find by document run, newest first, with the text it was for and when it ran."""
    kept = sorted(finds_folder().glob(FIND_PATTERN), key=lambda path: path.stat().st_mtime, reverse=True)
    finds = []
    for path in kept:
        record = json.loads(path.read_text(encoding="utf-8"))
        finds.append({
            "file": path.name,
            "input": record["input"],
            "when": record["when"].replace("T", " ")[:16],
            "count": len(record["results"]),
        })
    return finds


def kept_find(name):
    """One kept Find by document run with its papers named, closest first, or None when there is no such run."""
    path = finds_folder() / Path(name).name
    if not path.match(FIND_PATTERN) or not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    papers = []
    for found in record["results"]:
        paper = connections.named(found["base"])
        paper["score"] = found["score"]
        papers.append(paper)
    return {
        "file": path.name,
        "input": record["input"],
        "when": record["when"].replace("T", " ")[:16],
        "papers": papers,
    }
