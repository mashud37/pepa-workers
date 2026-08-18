"""Let a user manually correct chapter boundaries for an extracted book by
editing marker lines in one concatenated file, then rewrite the numbered
chapter files to match.
"""
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_CHAPTER_FILE_RE = re.compile(r"^text_(.+)_(\d+)\.md$")
_MARKER = "<!-- chapter -->"
_MARKER_RE = re.compile(r"^\s*<!--\s*chapter\s*-->\s*$", re.IGNORECASE)

# The instructions carry a literal example marker, so the book text is delimited by
# a distinct sentinel line rather than by scanning for the next "-->".
_BODY_SENTINEL = "<!-- (book text begins below this line; do not edit above) -->"

_HEADER = f"""\
<!-- ================================================================
  CHAPTER SPLIT EDITOR
  Add a line containing exactly:  {_MARKER}
  at each point where a new chapter should begin.
  Markers already in the file mark the current chapter boundaries.
  Save the file and close the editor when done.
  Do NOT edit the book text, only add or remove marker lines.
================================================================ -->
{_BODY_SENTINEL}
"""


@dataclass
class Book:
    """One source document and its current on-disk representation."""

    stem: str
    kind: str  # "single" | "chaptered"
    files: list[Path]  # ordered by chapter number; length 1 for a single book
    size: int  # total bytes across files

    @property
    def nchap(self) -> int:
        return len(self.files)


def list_books(out_dir: Path) -> dict[str, Book]:
    """Group every extracted text file by its source book.

    A file matching text_<stem>_<NN>.md is a chapter of book <stem>; any other
    text_*.md is a single-file book named by the rest of the filename. The two
    schemes do not overlap for a given stem, so grouping is unambiguous.
    """
    chapters: dict[str, list[Path]] = {}
    singles: dict[str, Path] = {}
    for p in sorted(out_dir.glob("text_*.md")):
        m = _CHAPTER_FILE_RE.match(p.name)
        if m:
            chapters.setdefault(m.group(1), []).append(p)
        else:
            singles[p.name[len("text_"):-len(".md")]] = p

    books: dict[str, Book] = {}
    for stem, files in chapters.items():
        files = sorted(files, key=_chapter_number)
        books[stem] = Book(stem, "chaptered", files,
                           sum(f.stat().st_size for f in files))
    for stem, path in singles.items():
        if stem not in books:
            books[stem] = Book(stem, "single", [path], path.stat().st_size)
    return books


def _chapter_number(path: Path) -> int:
    m = _CHAPTER_FILE_RE.match(path.name)
    return int(m.group(2)) if m else 0


def build_editor_body(book: Book) -> str:
    """Concatenate a book's files, marking each existing chapter boundary."""
    parts = [p.read_text(encoding="utf-8").strip() for p in book.files]
    return f"\n\n{_MARKER}\n\n".join(parts)


def prepare_editor_file(book: Book, tmp_path: Path) -> None:
    """Write the book's content, prefixed with editor instructions, to tmp_path."""
    tmp_path.write_text(_HEADER + "\n" + build_editor_body(book) + "\n",
                        encoding="utf-8")


def open_editor(path: Path) -> None:
    """Open path in $EDITOR, falling back to notepad on Windows or nano on POSIX."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        editor = "notepad" if os.name == "nt" else "nano"
    subprocess.run([editor, str(path)], check=True)


def apply_markers(tmp_path: Path, book: Book, out_dir: Path) -> dict:
    """Parse marker lines, split, rewrite the book's chapter files.

    A single-block book left without markers is unchanged (count 0). Otherwise the
    book's current files are removed and the chunks are written as numbered chapter
    files. Deletion targets the book's known paths exactly, never a glob, so a book
    cannot clobber a differently named sibling.

    Returns:
        {"count": chapter files written, "warnings": list of warning strings}.
    """
    raw = tmp_path.read_text(encoding="utf-8")

    # Drop everything up to and including the sentinel; the header holds an example
    # marker, so anchoring on the sentinel is the only reliable cut point.
    _, sep, after = raw.partition(_BODY_SENTINEL)
    if sep:
        raw = after

    chunks = _split_on_markers(raw)
    warnings: list[str] = []

    if not chunks:
        warnings.append("file is empty, nothing written")
        return {"count": 0, "warnings": warnings}

    if book.kind == "single" and len(chunks) < 2:
        warnings.append("no <!-- chapter --> markers added, file unchanged")
        return {"count": 0, "warnings": warnings}

    for existing in book.files:
        if existing.exists():
            existing.unlink()

    width = max(2, len(str(len(chunks))))
    for i, chunk in enumerate(chunks, 1):
        text = chunk.strip() + "\n"
        (out_dir / f"text_{book.stem}_{i:0{width}d}.md").write_text(text, encoding="utf-8")

    return {"count": len(chunks), "warnings": warnings}


def _split_on_markers(raw: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for line in raw.splitlines(keepends=True):
        if _MARKER_RE.match(line):
            if current:
                chunks.append("".join(current))
            current = []
        else:
            current.append(line)
    if current:
        chunks.append("".join(current))
    return [c for c in chunks if c.strip()]
