"""Resolve pepa-prep/pepa-sum filenames to a shared (stem, chapter)
document identity, mirroring pepa-sum's paper_stem() and splitting off a
pepa-prep chapter suffix so a chapter and its summary share one row.
"""
import re
from pathlib import Path

_PREP_PREFIX = "text_"
_PREP_SUFFIXES = (".md", ".markdown", ".txt")
_SUM_PREFIX = "sum_"
_CHAPTER_RE = re.compile(r"^(.+)_(\d{2,3})$")

# pepa-sum's fixed sum_ template (see pepa-sum/README.md "sum_ template"): every
# brief has these seven top-level bold-labelled bullets, always in this order.
# Mapping label text -> column/FTS field name, so each section is searchable
# on its own (e.g. `lit:foucault`) instead of only as one concatenated blob.
SECTION_LABELS = {
    "question & context": "question_context",
    "empirical context": "empirical_context",
    "literature drawn on": "literature",
    "methods": "methods",
    "arguments": "arguments",
    "key conclusions": "conclusions",
    "discussion items": "discussion",
}
SECTION_FIELDS = tuple(SECTION_LABELS.values())

_TOP_BULLET_RE = re.compile(r"^-\s+\*\*([^*]+?):\*\*\s*(.*)$")


def paper_stem(source_name: str) -> str:
    p = Path(source_name)
    stem = p.stem
    if p.suffix.lower() in _PREP_SUFFIXES and stem.startswith(_PREP_PREFIX):
        return stem[len(_PREP_PREFIX):]
    return stem


def split_chapter(stem: str) -> dict:
    """The book `stem` on its own, and the `chapter` number it carried, or None."""
    m = _CHAPTER_RE.match(stem)
    if m:
        return {"stem": m.group(1), "chapter": m.group(2)}
    return {"stem": stem, "chapter": None}


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


def parse_sum_sections(path: Path) -> dict[str, str]:
    """Split a sum_ file into its seven labelled sections (SECTION_FIELDS).

    Each top-level bullet `- **Label:** ...` starts a new section; indented
    lines (sub-bullets, numbered arguments) that follow belong to it until the
    next recognized top-level bullet. Unrecognized top-level bullets reset the
    current section to none, so any stray content is dropped rather than
    bleeding into the wrong field.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return {}
    sections: dict[str, list[str]] = {}
    current = None
    for line in lines:
        m = _TOP_BULLET_RE.match(line)
        if m:
            current = SECTION_LABELS.get(m.group(1).strip().lower())
            if current is None:
                continue
            rest = m.group(2).strip()
            sections.setdefault(current, [])
            if rest:
                sections[current].append(rest)
            continue
        if current is None:
            continue
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^[-*]\s+", "", s)
        s = re.sub(r"^\d+\.\s+", "", s)
        s = s.replace("**", "")
        sections[current].append(s)
    return {k: re.sub(r"\s+", " ", " ".join(v)).strip() for k, v in sections.items()}


def text_stem_and_chapter(text_filename: str) -> dict:
    return split_chapter(paper_stem(text_filename))


def sum_stem_and_chapter(sum_filename: str) -> dict:
    stem = Path(sum_filename).stem
    if stem.startswith(_SUM_PREFIX):
        stem = stem[len(_SUM_PREFIX):]
    return split_chapter(stem)
