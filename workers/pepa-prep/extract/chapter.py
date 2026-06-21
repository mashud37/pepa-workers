"""Chapter splitting — by PDF outline (TOC) or heading pattern."""
import re
from pathlib import Path

from .text import render, strip_references

_NUM_WORDS = (
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?"
    r"|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    r"|one|two|three|four|five|six|seven|eight|nine"
    r"|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
    r"|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth"
    r"|eighteenth|nineteenth|twentieth"
)
_CHAPTER_HEADING_RE = re.compile(
    r"^\s*#*\s*(?:chapter|part)\s+(?:\d{1,3}|[ivxlcdm]+|" + _NUM_WORDS + r")\b",
    re.IGNORECASE,
)
_MIN_CHAPTER_CHARS = 1500


def toc_chapters(doc) -> list | None:
    try:
        toc = doc.get_toc(simple=True)
    except Exception:
        toc = None
    if not toc:
        return None
    top = min(level for level, _, _ in toc)
    marks = [(title, page - 1) for level, title, page in toc if level == top and page >= 1]
    if len(marks) < 2:
        return None
    chapters = []
    for i, (title, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else doc.page_count
        if end > start:
            chapters.append((title, range(start, max(start + 1, end))))
    return chapters or None


def _is_chapter_heading(el: tuple) -> bool:
    if el[0] != "heading":
        return False
    t = el[2].strip()
    return len(t.split()) <= 8 and bool(_CHAPTER_HEADING_RE.match(t))


def _chapter_text_len(group: list) -> int:
    return sum(len(t) for k, _, t in group if k == "para")


def split_into_chapters(elements: list) -> list:
    if sum(1 for el in elements if _is_chapter_heading(el)) < 2:
        return [elements]
    chapters, current = [], []
    for el in elements:
        if (_is_chapter_heading(el) and current
                and _chapter_text_len(current) >= _MIN_CHAPTER_CHARS):
            chapters.append(current)
            current = [el]
        else:
            current.append(el)
    if current:
        chapters.append(current)
    return chapters


def write_chapters(stem: str, out_dir: Path, chapters: list) -> str:
    width = max(2, len(str(len(chapters))))
    for i, elements in enumerate(chapters, 1):
        md = strip_references(render(elements))
        (out_dir / f"text_{stem}_{i:0{width}d}.md").write_text(md, encoding="utf-8")
    return f"{len(chapters)} chapter file(s)"
