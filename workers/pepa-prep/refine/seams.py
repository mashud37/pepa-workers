"""Seam integrity, dehyphenation, and lexical-cohesion gates."""
import math
import re
from collections import Counter

from . import signals

_TERMINAL = tuple(".!?:;\"'”’)]…*")
_WINDOW_TOKENS = 200
_MIN_WINDOW = 80
MERGE_BLOCK = 0.08
SPLIT_BLOCK = 0.70
_HYPHEN_RE = re.compile(r"([^\W\d_]{2,})-$")
_LEAD_WORD_RE = re.compile(r"^([^\W\d_]{2,})")


def _prev_text(lines: list, bound: int) -> str:
    return next((ln.strip() for ln in reversed(lines[:bound]) if ln.strip()), "")


def _next_text(lines: list, bound: int) -> str:
    return next((ln.strip() for ln in lines[bound:] if ln.strip()), "")


def broken_seam(lines: list, bound: int) -> bool:
    """True when the text runs mid-sentence across a unit boundary."""
    prev, nxt = _prev_text(lines, bound), _next_text(lines, bound)
    if not prev or not nxt or prev.startswith("#") or nxt.startswith("#"):
        return False
    first = next((c for c in nxt if c.isalpha()), "")
    return not prev.endswith(_TERMINAL) and not prev[-1].isdigit() and first.islower()


def dehyphen_points(lines: list, vocab: set) -> list:
    """Line indices whose trailing hyphenation joins with the next line into a
    word the book itself uses elsewhere."""
    points = []
    for i, ln in enumerate(lines[:-1]):
        t = ln.rstrip()
        m = _HYPHEN_RE.search(t)
        if not m or t.startswith("#") or lines[i + 1].startswith("#"):
            continue
        lead = _LEAD_WORD_RE.match(lines[i + 1].strip())
        if not lead or not lead.group(1)[0].islower():
            continue
        if (m.group(1) + lead.group(1)).casefold() in vocab:
            points.append(i)
    return points


def _vector(text_lines: list, fw: set) -> Counter:
    counts: Counter = Counter()
    for ln in text_lines:
        counts.update(t for t in signals.tokens(ln) if t not in fw and len(t) > 2)
    return counts


def cosine(a: Counter, b: Counter) -> float:
    dot = sum(v * b[k] for k, v in a.items())
    na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _window(lines: list, bound: int, fw: set, before: bool) -> Counter:
    counts: Counter = Counter()
    rng = range(bound - 1, -1, -1) if before else range(bound, len(lines))
    for i in rng:
        counts.update(t for t in signals.tokens(lines[i]) if t not in fw and len(t) > 2)
        if sum(counts.values()) >= _WINDOW_TOKENS:
            break
    return counts


def seam_cohesion(lines: list, bound: int, fw: set) -> float | None:
    """Cosine across a boundary; None when either side is too small to judge."""
    a = _window(lines, bound, fw, before=True)
    b = _window(lines, bound, fw, before=False)
    if sum(a.values()) < _MIN_WINDOW or sum(b.values()) < _MIN_WINDOW:
        return None
    return cosine(a, b)
