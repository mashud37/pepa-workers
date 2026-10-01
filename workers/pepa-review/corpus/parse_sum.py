"""Parse a sum_ Markdown file into a structured dict: line one is the
source filename, then a title heading and fixed bold-labelled fields in
order.
"""
import re
from pathlib import Path

_FIELD_ORDER = [
    ("question",    re.compile(r"^- \*\*Question\s*&\s*context:\*\*\s*", re.M)),
    ("empirical",   re.compile(r"^- \*\*Empirical\s*context:\*\*\s*", re.M)),
    ("literature",  re.compile(r"^- \*\*Literature\s*drawn\s*on:\*\*\s*", re.M)),
    ("methods",     re.compile(r"^- \*\*Methods:\*\*\s*", re.M)),
    ("arguments",   re.compile(r"^- \*\*Arguments:\*\*\s*", re.M)),
    ("conclusions", re.compile(r"^- \*\*Key\s*conclusions:\*\*\s*", re.M)),
    ("discussion",  re.compile(r"^- \*\*Discussion\s*items:\*\*\s*", re.M)),
]


def parse_sum(path):
    """Return dict with keys: base, source_file, title, question, empirical,
    literature, methods, arguments (list), arguments_text, conclusions, discussion.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    source_file = lines[0].strip() if lines else ""

    title = ""
    for line in lines:
        if line.startswith("## "):
            title = line[3:].strip()
            break

    field_spans = []
    for name, pat in _FIELD_ORDER:
        m = pat.search(text)
        if m:
            field_spans.append((m.start(), m.end(), name))
    field_spans.sort()

    fields = {}
    for i, (start, end, name) in enumerate(field_spans):
        next_start = field_spans[i + 1][0] if i + 1 < len(field_spans) else len(text)
        fields[name] = text[end:next_start].strip()

    args_text = fields.get("arguments", "")
    args_items = re.split(r"\n\s*\d+\.\s+", args_text)
    args_list = [item.strip() for item in args_items if item.strip()]

    stem = Path(path).stem
    base = stem[4:] if stem.startswith("sum_") else stem

    return {
        "base": base,
        "source_file": source_file,
        "title": title,
        "question": fields.get("question", ""),
        "empirical": fields.get("empirical", ""),
        "literature": fields.get("literature", ""),
        "methods": fields.get("methods", ""),
        "arguments": args_list,
        "arguments_text": args_text,
        "conclusions": fields.get("conclusions", ""),
        "discussion": fields.get("discussion", ""),
    }
