"""List the library's PDFs with page counts and progress, keep the chapter starts a user marks, and draw pages as images.
The Papers and Chapters pages show these.
"""
import io
import json
import os
import threading
from pathlib import Path

import pypdfium2 as pdfium

from web import folders, paths
from web.settings import SETTINGS

PAGE_COUNTS_FILE_NAME = "page-counts.json"
BYTES_PER_MEGABYTE = 1024 * 1024
THUMBNAIL_WIDTH = 200
LARGE_WIDTH = 1000
JPEG_QUALITY = 75
# A PDF longer than this is offered the chapter marker.
BOOK_PAGES = 50

# Choices for the length filter: a PDF is shown when it has more pages than this.
LONGER_THAN = [
    0,
    50,
    100,
    200,
    400,
]

# PDFium allows one call at a time in a process, and the console answers requests on several threads.
LOCK = threading.Lock()


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


def page_counts(folder, names):
    """The page count of every PDF named, read once and kept until the file changes."""
    store = SETTINGS["keys_file"].parent / PAGE_COUNTS_FILE_NAME
    known = {}
    if store.exists():
        known = json.loads(store.read_text(encoding="utf-8"))
    counts = {}
    changed = False
    for name in names:
        details = (folder / name).stat()
        stamp = f"{details.st_size}:{details.st_mtime}"
        if known.get(name, {}).get("stamp") != stamp:
            known[name] = {"stamp": stamp, "pages": count_pages(folder / name)}
            changed = True
        counts[name] = known[name]["pages"]
    if changed:
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps(known), encoding="utf-8")
    return counts


# ---- The library ----

def summarised_files(stem):
    """How many of a PDF's prepared text files pepa-sum has summarised."""
    folder = paths.chosen("pepa-sum", "results")
    count = 0
    for name in paths.prepared_names(stem):
        if (folder / f"sum_{name[len('text_'):]}").exists():
            count += 1
    return count


def paper_rows(wanted, longer_than):
    """A row for every PDF waiting to be prepared that matches the name filter and is longer than the page filter.

    Returns:
        dict with "rows", each with name, relative path, pages, size, prepared and summarised
        state and whether it is set aside, and "total", the number of PDFs before filtering.
    """
    folder = paths.chosen("pepa-prep", "sources")
    names = folders.matching_names(folders.PDFS_WAITING)["names"]
    counts = page_counts(folder, names)
    excluded = paths.load_excluded()
    rows = []
    for name in sorted(names, key=str.lower):
        leaf = Path(name).name
        stem = Path(name).stem
        if wanted.lower() not in leaf.lower() or counts[name] <= longer_than:
            continue
        rows.append({
            "name": leaf,
            "relative": name,
            "pages": counts[name],
            "size": f"{(folder / name).stat().st_size / BYTES_PER_MEGABYTE:.1f} MB",
            "prepared": len(paths.prepared_names(stem)),
            "summarised": summarised_files(stem),
            "skip_prep": leaf in excluded["pepa-prep"],
            "skip_sum": leaf in excluded["pepa-sum"],
            "marked": marks_file(stem).exists(),
            "book": counts[name] > BOOK_PAGES,
        })
    return {"rows": rows, "total": len(names)}


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
        dict with "name", "relative", "pages", "starts" (PDF pages from 1), and "source",
        which says whether the starts were marked by hand, found by pepa-prep, or are not there yet.
    """
    path = source_path(relative)
    stem = path.stem
    found_file = paths.project_folder() / "pepa-prep" / "data" / "found" / f"{stem}.json"
    starts = []
    source = "none"
    if marks_file(stem).exists():
        starts = json.loads(marks_file(stem).read_text(encoding="utf-8"))["starts"]
        source = "marked"
    elif found_file.exists():
        starts = json.loads(found_file.read_text(encoding="utf-8"))["starts"]
        source = "found"
    return {"name": path.name, "relative": relative, "pages": count_pages(path), "starts": starts, "source": source}


def save_marks(relative, starts):
    """Keep the chapter starts the user marked, as PDF pages from 1; no starts removes the marks.

    Raises:
        ValueError: a start is not a page of this PDF.
    """
    path = source_path(relative)
    pages = count_pages(path)
    numbers = sorted({int(start) for start in starts if start.isdigit()})
    for number in numbers:
        if number < 1 or number > pages:
            raise ValueError(f"Page {number} is not in this PDF.")
    target = marks_file(path.stem)
    if not numbers:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"starts": numbers}), encoding="utf-8")
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
