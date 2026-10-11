"""Keep literature lists as text files of paper names, one per line.
Workers read the same files through `--list`, so a list made here feeds a review.
"""
from pathlib import Path

from web import connections, paths

LISTS_FOLDER = Path("pepa-console") / "lists"
FORBIDDEN = '\\/:*?"<>|'
LONGEST_NAME = 80


def lists_folder():
    """Where the lists are kept, made on first use."""
    folder = paths.project_folder() / LISTS_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_path(name):
    """The file of one list, by its name, whether or not it exists yet.

    Raises:
        ValueError: the name is empty, too long, or holds a character Windows refuses in a file name.
    """
    name = name.strip()
    if not name:
        raise ValueError("Give the list a name.")
    if len(name) > LONGEST_NAME:
        raise ValueError(f"Keep the list's name under {LONGEST_NAME} characters.")
    for character in FORBIDDEN:
        if character in name:
            raise ValueError(f"A list's name cannot hold {FORBIDDEN}.")
    if name.startswith("."):
        raise ValueError("A list's name cannot start with a dot.")
    return lists_folder() / f"{name}.txt"


def read_list(name):
    """The paper names in one list, in the order they were added; empty when there is no such list."""
    path = list_path(name)
    if not path.is_file():
        return []
    stems = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            stems.append(line)
    return stems


def all_lists():
    """Every list with how many papers it holds, by name."""
    found = []
    for path in sorted(lists_folder().glob("*.txt"), key=lambda path: path.stem.lower()):
        found.append({"name": path.stem, "count": len(read_list(path.stem))})
    return found


def write_list(name, stems):
    """Save a list's paper names, one per line."""
    lines = [f"{stem}\n" for stem in stems]
    list_path(name).write_text("".join(lines), encoding="utf-8")


def add_to_list(name, stems):
    """Add papers to a list, made if new, leaving out those already in it, and return how many were added."""
    kept = read_list(name)
    added = 0
    for stem in stems:
        if stem not in kept:
            kept.append(stem)
            added += 1
    write_list(name, kept)
    return added


def remove_from_list(name, stem):
    """Take one paper out of a list."""
    kept = [other for other in read_list(name) if other != stem]
    write_list(name, kept)


def delete_list(name):
    """Remove a list's file; the papers themselves are untouched."""
    path = list_path(name)
    if path.is_file():
        path.unlink()


def stems_of_pdfs(pdf_names):
    """The paper names behind ticked Library items: a book prepared as chapters gives one name per chapter.

    An item not prepared yet gives its own name, which matches its summary once it has one.
    """
    stems = []
    for pdf_name in pdf_names:
        stem = Path(pdf_name).stem
        prepared = paths.prepared_names(stem)
        if not prepared:
            stems.append(stem)
        for text_name in prepared:
            stems.append(text_name[len("text_"):-len(".md")])
    return stems


def list_papers(name):
    """One list's papers with their authors and titles, for the page."""
    return [connections.named(stem) for stem in read_list(name)]
