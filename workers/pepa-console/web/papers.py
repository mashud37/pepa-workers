"""List the library's PDFs with page counts and progress, keep the chapter starts a user marks, and draw pages as images.
The Library and Chapters pages show these.
"""
import io
import json
import os
import threading
from pathlib import Path

import pypdfium2 as pdfium

from web import batches, folders, options, paths
from web.settings import SETTINGS

PAGE_COUNTS_FILE_NAME = "page-counts.json"
# Page image widths in pixels: the Chapters page's tiles, its bigger tiles, and the enlarged page.
PAGE_WIDTHS = {
    "": 200,
    "medium": 500,
    "large": 1000,
}
JPEG_QUALITY = 75
PAGE_SIZE = 100
SAVE_COUNTS_EVERY = 200

# Choices for the Pages column's filter. A book has more pages than pepa-prep's book setting.
LENGTHS = {
    "": "Any length",
    "books": "Books",
    "shorter": "Shorter than books",
}
BOOK_PAGES = 100

# What a left-out page is, as the Chapters page offers it; every kind is left out alike, and
# pepa-prep reads pages marked "contents" as the book's printed table of contents.
LEAVE_OUT_KINDS = {
    "": "Not needed",
    "front": "Front matter",
    "acknowledgements": "Acknowledgements",
    "contents": "Contents",
    "notes": "Notes",
    "bibliography": "Bibliography",
    "index": "Index",
}

# The columns the paper list sorts by; a leading "-" in the request turns the order round.
SORT_COLUMNS = [
    "name",
    "pages",
    "prepared",
    "summarised",
]

# PDFium allows one call at a time in a process, and the console answers requests on several threads.
LOCK = threading.Lock()

# Whether page counting is running in the background, so a second visit does not start another.
COUNTING = {"running": False}


# ---- Page counts ----

def count_pages(path):
    """How many pages a PDF has, or 0 when it cannot be opened."""
    with LOCK:
        try:
            document = pdfium.PdfDocument(str(path))
        except pdfium.PdfiumError:
            return 0
        count = len(document)
        document.close()
    return count


def counts_file():
    return SETTINGS["keys_file"].parent / PAGE_COUNTS_FILE_NAME


def load_counts():
    """Every page count kept so far, as {relative name: {"stamp", "pages"}}."""
    if not counts_file().exists():
        return {}
    return json.loads(counts_file().read_text(encoding="utf-8"))


def count_in_background(folder, names):
    """Start counting the pages of PDFs that are new or changed, unless a count is already running."""
    with LOCK:
        if COUNTING["running"]:
            return
        COUNTING["running"] = True
    threading.Thread(target=count_missing, args=(folder, names), daemon=True).start()


def count_missing(folder, names):
    """Count the pages of every PDF not counted since it last changed, saving as it goes."""
    known = load_counts()
    counted = 0
    try:
        for name in names:
            path = folder / name
            if not path.is_file():
                continue
            details = path.stat()
            stamp = f"{details.st_size}:{details.st_mtime}"
            if known.get(name, {}).get("stamp") == stamp:
                continue
            known[name] = {"stamp": stamp, "pages": count_pages(path)}
            counted += 1
            if counted % SAVE_COUNTS_EVERY == 0:
                paths.write_json(counts_file(), known)
        if counted:
            paths.write_json(counts_file(), known)
    finally:
        COUNTING["running"] = False


# ---- The library ----

def progress_by_stem(stems):
    """How many text files pepa-prep wrote for each PDF and how many of those pepa-sum summarised,
    from one look at each output folder."""
    progress = {}
    for stem in stems:
        progress[stem] = {"prepared": 0, "summarised": 0}
    text_folder = paths.chosen("pepa-prep", "results") / "text"
    summary_folder = paths.chosen("pepa-sum", "results")
    summaries = set()
    if summary_folder.is_dir():
        summaries = set(os.listdir(summary_folder))
    if not text_folder.is_dir():
        return progress
    for name in os.listdir(text_folder):
        if not (name.startswith("text_") and name.endswith(".md")):
            continue
        core = name[len("text_"):-len(".md")]
        head, _, tail = core.rpartition("_")
        stem = core
        if core not in progress and head in progress and tail.isdigit():
            stem = head
        if stem not in progress:
            continue
        progress[stem]["prepared"] += 1
        if f"sum_{core}.md" in summaries:
            progress[stem]["summarised"] += 1
    return progress


def sort_key(column, row, progress):
    """What one row sorts by for a column: its name, its pages (uncounted last), or its prepared or summarised files."""
    stem = Path(row["relative"]).stem
    if column == "pages":
        return -1 if row["pages"] is None else row["pages"]
    if column in ("prepared", "summarised"):
        return progress[stem][column]
    return Path(row["relative"]).name.lower()


def book_pages():
    """The page count above which pepa-prep treats a PDF as a book: its setting here, else its default."""
    chosen = os.environ.get("PEPAPREP_BOOK_PAGES") or options.load_store().get("pepa-prep", {}).get("PEPAPREP_BOOK_PAGES")
    if chosen and chosen.isdigit():
        return int(chosen)
    return BOOK_PAGES


def fits_length(pages, length, threshold):
    """Whether a PDF passes the length filter; one whose pages are not counted yet passes only "Any length"."""
    if not length:
        return True
    if pages is None:
        return False
    if length == "books":
        return pages > threshold
    return pages <= threshold


def matching_papers(wanted, length):
    """Every PDF, prepared or waiting, whose name holds the wanted text and whose length fits, as name and pages.

    Returns:
        dict with "rows", each with relative and pages; "total", the PDFs before filtering; "present",
        the names still in the folder; and "uncounted", the names whose pages are not counted yet.
    """
    folder = paths.chosen("pepa-prep", "sources")
    present = folders.matching_names(folders.PDFS_WAITING)["names"]
    removed = paths.load_removed()
    names = sorted(set(present) | set(removed), key=str.lower)
    known = load_counts()
    uncounted = [name for name in present if name not in known]
    count_in_background(folder, present)
    threshold = book_pages()
    rows = []
    for name in names:
        pages = known.get(name, {}).get("pages")
        if name not in present:
            pages = removed[name]["pages"]
        if wanted.lower() not in Path(name).name.lower():
            continue
        if not fits_length(pages, length, threshold):
            continue
        rows.append({"relative": name, "pages": pages})
    return {"rows": rows, "total": len(names), "present": present, "uncounted": uncounted}


def paper_rows(wanted, length, page, sort="name"):
    """One page of rows for the PDFs waiting to be prepared that match the name and length filters.

    Returns:
        dict with "rows", each with name, relative path, pages (None while not counted), prepared
        and summarised counts and whether it is set aside; "total", the PDFs before filtering;
        "shown", the PDFs after filtering; "page" and "pages"; and "counting", the PDFs not counted yet.
    """
    found = matching_papers(wanted, length)
    matching = found["rows"]
    present = found["present"]
    column = sort.lstrip("-")
    if column in ("prepared", "summarised"):
        everything = progress_by_stem([Path(row["relative"]).stem for row in matching])
    else:
        everything = {}
    matching.sort(key=lambda row: sort_key(column, row, everything), reverse=sort.startswith("-"))
    page_count = max(1, (len(matching) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(1, page), page_count)
    shown = matching[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    progress = progress_by_stem([Path(row["relative"]).stem for row in shown])
    waiting = batches.waiting_stems()
    excluded = paths.load_excluded()
    rows = []
    for row in shown:
        leaf = Path(row["relative"]).name
        stem = Path(row["relative"]).stem
        rows.append({
            "name": leaf,
            "relative": row["relative"],
            "pages": row["pages"],
            "prepared": progress[stem]["prepared"],
            "summarised": progress[stem]["summarised"],
            "skip_prep": leaf in excluded["pepa-prep"],
            "skip_sum": leaf in excluded["pepa-sum"],
            "in_batch": stem in waiting or any(name.startswith(stem + "_") for name in waiting),
            "marked": marks_file(stem).exists(),
            "removed": row["relative"] not in present,
        })
    return {
        "rows": rows,
        "total": found["total"],
        "shown": len(matching),
        "page": page,
        "pages": page_count,
        "counting": len(found["uncounted"]),
    }


def remove_copies(names):
    """Delete the PDF copies of papers already prepared, remembering their page counts so the Library keeps them.

    Returns:
        dict with "removed", how many copies went, and "kept", the names not prepared yet.

    Raises:
        ValueError: the PDFs are in a folder the user linked rather than pepa-prep's own.
    """
    if not paths.own_pdf_folder():
        raise ValueError("These PDFs sit in a folder you linked; the console never deletes from it.")
    folder = paths.chosen("pepa-prep", "sources")
    removed = paths.load_removed()
    kept = []
    for name in names:
        path = folder / name
        if not path.is_file() or Path(name).name != name:
            continue
        if not paths.prepared_names(path.stem):
            kept.append(name)
            continue
        removed[name] = {"pages": count_pages(path)}
        path.unlink()
    paths.write_json(paths.removed_file(), removed)
    return {"removed": len(names) - len(kept), "kept": kept}


# ---- Chapter starts ----

def marks_file(stem):
    return paths.project_folder() / "pepa-prep" / "data" / "marks" / f"{stem}.json"


def source_path(relative):
    """The PDF a relative name points at inside the PDF folder, or None when it points anywhere else."""
    folder = paths.chosen("pepa-prep", "sources").resolve()
    path = (folder / relative).resolve()
    if folder not in path.parents or path.suffix.lower() != ".pdf" or not path.is_file():
        return None
    return path


def chapter_view(relative):
    """What the Chapters page shows for one PDF: its pages and the starts already marked or found.

    Returns:
        dict with "name", "relative", "pages", "starts" and "skips" (PDF pages from 1), "kinds"
        (what each left-out page is, by page), and "source",
        which says whether the starts were marked by hand, found by pepa-prep, or are not there yet.
    """
    path = source_path(relative)
    stem = path.stem
    found_file = paths.project_folder() / "pepa-prep" / "data" / "found" / f"{stem}.json"
    starts = []
    skips = []
    kinds = {}
    source = "none"
    if marks_file(stem).exists():
        marked = json.loads(marks_file(stem).read_text(encoding="utf-8"))
        starts = marked.get("starts", [])
        skips = marked.get("skip", [])
        for page, kind in marked.get("kinds", {}).items():
            kinds[int(page)] = kind
        source = "marked"
    elif found_file.exists():
        starts = json.loads(found_file.read_text(encoding="utf-8"))["starts"]
        source = "found"
    return {
        "name": path.name,
        "relative": relative,
        "pages": count_pages(path),
        "starts": starts,
        "skips": skips,
        "kinds": kinds,
        "source": source,
    }


def page_numbers(values, pages):
    """The page numbers given as form values, sorted and checked against the PDF's length.

    Raises:
        ValueError: a number is not a page of this PDF.
    """
    numbers = sorted({int(value) for value in values if value.isdigit()})
    for number in numbers:
        if number < 1 or number > pages:
            raise ValueError(f"Page {number} is not in this PDF.")
    return numbers


def save_marks(relative, starts, skips, kinds):
    """Keep the chapter starts and left-out pages the user marked, as PDF pages from 1; none removes the marks.

    Args:
        kinds: what each left-out page is, as {page text: kind}; a blank kind is left out of the file.

    Raises:
        ValueError: a page is not in this PDF, or a kind is not one of LEAVE_OUT_KINDS.
    """
    path = source_path(relative)
    pages = count_pages(path)
    marked = {"starts": page_numbers(starts, pages), "skip": page_numbers(skips, pages), "kinds": {}}
    for page in marked["skip"]:
        kind = kinds.get(str(page), "")
        if kind not in LEAVE_OUT_KINDS:
            raise ValueError(f"Page {page}: {kind} is not a kind of page that can be left out.")
        if kind:
            marked["kinds"][str(page)] = kind
    target = marks_file(path.stem)
    if not marked["starts"] and not marked["skip"]:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(marked), encoding="utf-8")
    os.replace(temporary, target)


def page_image(relative, number, width):
    """One page of a PDF drawn as a JPEG this many pixels wide, or None when there is no such page."""
    path = source_path(relative)
    with LOCK:
        document = pdfium.PdfDocument(str(path))
        if number < 1 or number > len(document):
            document.close()
            return None
        page = document[number - 1]
        scale = width / page.get_size()[0]
        bitmap = page.render(scale=scale, grayscale=True)
        image = bitmap.to_pil().convert("L")
        bitmap.close()
        page.close()
        document.close()
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()
