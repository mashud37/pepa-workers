"""Resolve pepa-prep/pepa-sum filenames to a shared (stem, chapter) document identity.

Mirrors pepa-sum's paper_stem() (render/markdown.py) so both file families agree
on identity, then further splits a pepa-prep chapter suffix (chapter.py's
write_chapters: `text_{stem}_{i:0{width}d}.md`, width >= 2) so a chapter file
and its own summary land on the same row instead of the whole book's.

The suffix is restricted to 2-3 digits: real chapter counts in this corpus are
1-2 digits wide (write_chapters pads to width 2 minimum), while a bare title
ending in a 4-digit year (e.g. "text_Schubert_2010.md") must NOT be mistaken
for a chapter — confirmed against the real corpus before picking this width.
"""
import re
from pathlib import Path

_PREP_PREFIX = "text_"
_PREP_SUFFIXES = (".md", ".markdown", ".txt")
_SUM_PREFIX = "sum_"
_CHAPTER_RE = re.compile(r"^(.+)_(\d{2,3})$")


def paper_stem(source_name: str) -> str:
    p = Path(source_name)
    stem = p.stem
    if p.suffix.lower() in _PREP_SUFFIXES and stem.startswith(_PREP_PREFIX):
        return stem[len(_PREP_PREFIX):]
    return stem


def split_chapter(stem: str) -> tuple[str, str | None]:
    m = _CHAPTER_RE.match(stem)
    if m:
        return m.group(1), m.group(2)
    return stem, None


def authors_raw(book_stem: str) -> str:
    return book_stem.split("_", 1)[0]


def title_from_text(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    return line.lstrip("#").strip()
    except OSError:
        return None
    return None


def title_from_sum(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i > 5:
                    break
                line = line.strip()
                if line.startswith("#"):
                    return line.lstrip("#").strip()
    except OSError:
        return None
    return None


def body_from_sum(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    cleaned = []
    for line in lines[1:]:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = re.sub(r"^[-*]\s+", "", s)
        s = re.sub(r"^\d+\.\s+", "", s)
        s = s.replace("**", "")
        cleaned.append(s)
    return re.sub(r"\s+", " ", " ".join(cleaned)).strip()


def text_stem_and_chapter(text_filename: str) -> tuple[str, str | None]:
    return split_chapter(paper_stem(text_filename))


def sum_stem_and_chapter(sum_filename: str) -> tuple[str, str | None]:
    stem = Path(sum_filename).stem
    if stem.startswith(_SUM_PREFIX):
        stem = stem[len(_SUM_PREFIX):]
    return split_chapter(stem)
