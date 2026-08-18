"""Heading hygiene: false-heading demotion, running heads, recurring templates."""
import re
import statistics
from collections import defaultdict

from extract.anchor import text_key
from extract.shape import _ORD_RE

from . import signals

_MIN_RECUR = 3
_RUNNING_GAP = 5000
_TEMPLATE_GAP = 8000
_MAX_TITLE_WORDS = 12
_PROSE_FW_RATIO = 0.40
_TERMINAL = ".!?:;\"'”’)]…"
_SENTENCE_RE = re.compile(r"\)[.,]|[.!?]\s+[A-ZÄÖÜ]")


def _strong(text: str) -> int:
    score = 0
    if text.endswith("-") or text.endswith(","):
        score += 1
    first = ""
    for c in text:
        if c.isalpha():
            first = c
            break
    if first.islower() and not _ORD_RE.match(text):
        score += 1
    if _SENTENCE_RE.search(text):
        score += 1
    return score


def _weak(text: str, next_line: str, fw: set) -> int:
    score = 0
    if len(text.split()) > _MAX_TITLE_WORDS:
        score += 1
    toks = signals.tokens(text)
    if toks and sum(t in fw for t in toks) / len(toks) >= _PROSE_FW_RATIO:
        score += 1
    dangling = text and text[-1] not in _TERMINAL
    first = ""
    for c in next_line:
        if c.isalpha():
            first = c
            break
    if dangling and first.islower():
        score += 1
    return score


def false_headings(lines: list, heads: list, fw: set) -> list:
    """Heading lines that are broken prose, judged by derived structural features."""
    out = []
    for h in heads:
        t = h["text"].strip()
        if _ORD_RE.match(t) and len(t.split()) <= 8:
            continue
        next_text = ""
        for ln in lines[h["line"] + 1:h["line"] + 4]:
            if ln.strip():
                next_text = ln.strip()
                break
        strong = _strong(t)
        if strong and strong + _weak(t, next_text, fw) >= 2:
            out.append(h["line"])
    return out


def recurring(heads: list, offs: list) -> dict:
    """Split repeated heading keys into page-frequency running heads and
    chapter-frequency template markers by the char gap between occurrences.
    A repeated key that carries the same ordinal every time (\"CHAPTER 2\" three
    times) is a running head regardless of gap: chapters do not repeat numbers."""
    groups: dict = defaultdict(list)
    texts: dict = {}
    for h in heads:
        k = text_key(h["text"])
        if k:
            groups[k].append(h["line"])
            texts.setdefault(k, h["text"])
    out: dict = {"running": [], "template": {}}
    for k, ls in groups.items():
        if len(ls) < _MIN_RECUR:
            continue
        gaps = [offs[b] - offs[a] for a, b in zip(ls, ls[1:])]
        median = statistics.median(gaps)
        if median <= _RUNNING_GAP or _ORD_RE.match(texts[k].strip()):
            out["running"].extend(ls)
        elif median >= _TEMPLATE_GAP:
            out["template"][k] = ls
    return out
