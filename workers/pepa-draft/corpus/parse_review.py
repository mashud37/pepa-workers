"""Parse a pepa-review output markdown file into structured sections."""
import json
from pathlib import Path


def _flush_sub(sub, section, sections, text_parts):
    if sub and section:
        if sub["text"].strip():
            text_parts.append(sub["text"].strip())
        section["subsections"].append(sub)
    return None


def _start_section(line, sub, section, sections, text_parts):
    sub = _flush_sub(sub, section, sections, text_parts)
    if section:
        sections.append(section)
    heading = {"heading": line[3:].strip().rstrip(":"), "subsections": []}
    return {"section": heading, "sub": sub}


def _process_line(line, state):
    sec, sub, sections, works, text_parts, in_works = state
    if line.startswith("## Works drawn on"):
        _flush_sub(sub, sec, sections, text_parts)
        if sec:
            sections.append(sec)
        return {"section": None, "sub": None, "in_works": True}
    if in_works:
        w = line.strip().lstrip("-").strip()
        if w:
            works.append(w)
        return {"section": sec, "sub": sub, "in_works": in_works}
    if line.startswith("## "):
        started = _start_section(line, sub, sec, sections, text_parts)
        return {"section": started["section"], "sub": started["sub"], "in_works": in_works}
    if line.startswith("### ") and sec is not None:
        _flush_sub(sub, sec, sections, text_parts)
        new_sub = {"heading": line[4:].strip(), "text": ""}
        return {"section": sec, "sub": new_sub, "in_works": in_works}
    if sec is not None:
        if sub is None:
            sub = {"heading": "", "text": ""}
        sub["text"] += line + "\n"
    return {"section": sec, "sub": sub, "in_works": in_works}


def parse(path: Path) -> dict:
    """Parse review markdown into sections.

    Args:
        path: Path to the review markdown file.

    Returns:
        dict with keys: sections, works, full_text. The works are the paper names in the
        review's .json beside it, empty when pepa-review wrote none.
    """
    sections, works, text_parts = [], [], []
    sec, sub, in_works = None, None, False
    for line in path.read_text(encoding="utf-8").splitlines():
        state = _process_line(line, (sec, sub, sections, works, text_parts, in_works))
        sec, sub, in_works = state["section"], state["sub"], state["in_works"]
    _flush_sub(sub, sec, sections, text_parts)
    if sec:
        sections.append(sec)
    bases = []
    works_file = path.with_suffix(".json")
    if works_file.is_file():
        bases = json.loads(works_file.read_text(encoding="utf-8"))["works"]
    return {"sections": sections, "works": bases, "full_text": "\n\n".join(text_parts)}


def full_prose(parsed: dict) -> str:
    """Return all prose text concatenated for context retrieval."""
    parts = []
    for s in parsed["sections"]:
        for sub in s["subsections"]:
            if sub["text"].strip():
                parts.append(sub["text"].strip())
    return "\n\n".join(parts)
