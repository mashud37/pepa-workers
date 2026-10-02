"""Show any file an app reads or writes inside the console: markdown rendered, text as text, a PDF in place.
The viewer, file browser and guide pages use it.
"""
import json
import math
import os
from datetime import datetime
from pathlib import Path

import markdown

from web import paths

GUIDES_FOLDER = Path(__file__).resolve().parent.parent / "guides"

MARKDOWN_EXTENSIONS = [
    "tables",
    "fenced_code",
    "sane_lists",
]

KIND_BY_SUFFIX = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".log": "text",
    ".yaml": "text",
    ".yml": "text",
    ".csv": "text",
    ".tsv": "text",
    ".json": "json",
    ".jsonl": "text",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".html": "page",
    ".docx": "docx",
}

# Every document one paper can have, where it sits, and the file name built from the paper's stem.
PAPER_DOCUMENTS = [
    {"label": "Source PDF", "app": "pepa-prep", "slot": "sources", "pattern": "{stem}.pdf"},
    {"label": "Source PDF", "app": "pepa-sum", "slot": "sources", "pattern": "{stem}.pdf"},
    {"label": "Prepared text", "app": "pepa-prep", "slot": "results", "pattern": "text/text_{stem}.md"},
    {"label": "Brief", "app": "pepa-sum", "slot": "results", "pattern": "sum_{stem}.md"},
    {"label": "Rundown", "app": "pepa-sum", "slot": "results", "pattern": "para_{stem}.md"},
    {"label": "Quotes", "app": "pepa-sum", "slot": "results", "pattern": "quote_{stem}.md"},
]

PAPER_PREFIXES = [
    "text_",
    "sum_",
    "para_",
    "quote_",
]

TEXT_LIMIT = 2_000_000
PAGE_SIZE = 100
TIME_FORMAT = "%d %b %Y, %H:%M"


# ---- Rendering ----

def render_markdown(text):
    """Markdown as HTML. Every `<` is escaped first, so a file can never put its own HTML or script on the page.

    The workers indent nested lists by two spaces, so two spaces mark one level here too.
    """
    safe = text.replace("<", "&lt;")
    return markdown.markdown(safe, extensions=MARKDOWN_EXTENSIONS, tab_length=2)


def docx_text(path):
    """The paragraphs of a Word file as plain text, one per line."""
    import docx
    document = docx.Document(str(path))
    return "\n\n".join(paragraph.text for paragraph in document.paragraphs)


def size_text(size):
    """A file size as people read it: bytes, KB or MB."""
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{math.ceil(size / 1024)} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def document_view(path):
    """Everything the viewer shows for one file: its kind, and its content when it is shown as text.

    Returns:
        dict with "kind", "name", "size", "modified", and "html" or "text" for the kinds shown inline.
    """
    stat = path.stat()
    kind = KIND_BY_SUFFIX.get(path.suffix.lower(), "other")
    view = {
        "kind": kind,
        "name": path.name,
        "title": paper_stem(path.name).replace("_", " "),
        "size": size_text(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime(TIME_FORMAT),
        "html": "",
        "text": "",
        "cut": False,
    }
    if kind in ["markdown", "text", "json"] and stat.st_size > TEXT_LIMIT:
        view["cut"] = True
    if kind == "markdown":
        view["html"] = render_markdown(path.read_text(encoding="utf-8", errors="replace")[:TEXT_LIMIT])
    elif kind == "text":
        view["text"] = path.read_text(encoding="utf-8", errors="replace")[:TEXT_LIMIT]
    elif kind == "json":
        view["text"] = json_text(path)
    elif kind == "docx":
        view["text"] = docx_text(path)
    return view


def json_text(path):
    """A JSON file laid out with indents, or as it is when it does not parse."""
    raw = path.read_text(encoding="utf-8", errors="replace")[:TEXT_LIMIT]
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except ValueError:
        return raw


# ---- One paper's documents ----

def paper_stem(file_name):
    """The paper a file belongs to, from its name: `sum_Smith_2020.md` belongs to `Smith_2020`."""
    stem = Path(file_name).stem
    for prefix in PAPER_PREFIXES:
        if stem.startswith(prefix):
            return stem[len(prefix):]
    return stem


def related_documents(file_name):
    """Every document of the same paper that exists, in reading order, as links the viewer shows as tabs."""
    stem = paper_stem(file_name)
    found = []
    for document in PAPER_DOCUMENTS:
        folder = paths.chosen(document["app"], document["slot"])
        relative = document["pattern"].format(stem=stem)
        if (folder / relative).is_file():
            found.append({
                "label": document["label"],
                "app": document["app"],
                "slot": document["slot"],
                "relative": relative,
            })
    return found


# ---- Browsing a folder ----

def visible_entries(here, wanted):
    """The files and folders directly in a folder whose names contain the wanted text, hidden ones left out."""
    if not here.is_dir():
        return []
    found = []
    with os.scandir(here) as entries:
        for entry in entries:
            if not entry.name.startswith(".") and wanted.lower() in entry.name.lower():
                found.append(entry)
    return found


def folder_listing(folder, inside, wanted, page):
    """One page of a folder's files and sub-folders, newest first, filtered by a piece of the name.

    Args:
        inside: the sub-folder being shown, relative to the folder; empty for the folder itself.
        wanted: only names containing this text, ignoring case; empty shows everything.
        page: which page of PAGE_SIZE entries, counting from 1.

    Returns:
        dict with "rows", "total", "page", "pages", and "parent", the sub-folder one level up.
    """
    rows = []
    for entry in visible_entries(folder / inside, wanted):
        stat = entry.stat()
        rows.append({
            "name": entry.name,
            "relative": str(Path(inside) / entry.name) if inside else entry.name,
            "is_folder": entry.is_dir(),
            "modified": stat.st_mtime,
            "when": datetime.fromtimestamp(stat.st_mtime).strftime(TIME_FORMAT),
            "size": "" if entry.is_dir() else size_text(stat.st_size),
        })
    rows.sort(key=lambda row: row["modified"], reverse=True)
    rows.sort(key=lambda row: not row["is_folder"])
    pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
    page = min(max(page, 1), pages)
    start = (page - 1) * PAGE_SIZE
    parent = str(Path(inside).parent) if inside else None
    if parent == ".":
        parent = ""
    return {
        "rows": rows[start:start + PAGE_SIZE],
        "total": len(rows),
        "page": page,
        "pages": pages,
        "parent": parent,
    }


# ---- Guides ----

def guide_names():
    """The guide pages that exist, by file name without its ending, with the getting-started page first."""
    names = sorted(path.stem for path in GUIDES_FOLDER.glob("*.md"))
    names.sort(key=lambda name: name != "index")
    return names


def guide_page(name):
    """One guide rendered as HTML with its first heading as the title, or None when there is no such guide."""
    path = GUIDES_FOLDER / f"{name}.md"
    if name not in guide_names():
        return None
    text = path.read_text(encoding="utf-8")
    title = name
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return {"name": name, "title": title, "html": render_markdown(text)}
