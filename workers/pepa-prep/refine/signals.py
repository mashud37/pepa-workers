"""Shared text features: headings, function words, char-level shape priors."""
import re
import statistics
from collections import Counter
from itertools import accumulate

from extract import shape

_HEAD_RE = re.compile(r"^(#{1,6})\s*(\S.*)$")
_WORD_RE = re.compile(r"[^\W\d_]+")
_FUNCTION_WORDS = 40
PAGE_CHARS = 2000
MIN_UNIT_CHARS = shape._MIN_CHAPTER_CHARS
OVERSIZED_CHARS = 150_000
_OVERSPLIT_UNITS = 8
_OVERSPLIT_MEDIAN = 3 * PAGE_CHARS
_MAX_TITLE_WORDS = 8
_CAPS_MAX = 70


def headings(lines: list) -> list:
    out = []
    for i, ln in enumerate(lines):
        m = _HEAD_RE.match(ln)
        if m:
            out.append({"line": i, "level": len(m.group(1)), "text": m.group(2).strip()})
    return out


def _plain_candidate(text: str) -> bool:
    if not text or len(text) > _CAPS_MAX or text.startswith("#"):
        return False
    caps = text.isupper() and sum(c.isalpha() for c in text) >= 3
    numbered = text[0].isdigit() and any(c.isalpha() for c in text)
    return caps or numbered


def anchor_heads(lines: list, heads: list) -> list:
    """Heading candidates for title anchoring: markdown headings plus short
    all-caps or number-led plain lines (OCR-flattened chapter openers)."""
    have = {h["line"] for h in heads}
    out = list(heads)
    for i, ln in enumerate(lines):
        t = ln.strip()
        if i not in have and _plain_candidate(t):
            out.append({"line": i, "level": 0, "text": t})
    out.sort(key=lambda h: h["line"])
    return out


def char_offsets(lines: list) -> list:
    return list(accumulate((len(ln) + 1 for ln in lines), initial=0))


def tokens(text: str) -> list:
    return _WORD_RE.findall(text.casefold())


def lexicon(lines: list) -> tuple[set, set]:
    """One tokenizing pass returning (function words, full vocabulary)."""
    counts: Counter = Counter()
    for ln in lines:
        counts.update(tokens(ln))
    return {w for w, _ in counts.most_common(_FUNCTION_WORDS)}, set(counts)


def unit_spans(bounds: list, offs: list) -> list:
    stops = list(bounds[1:]) + [len(offs) - 1]
    return [offs[z] - offs[a] for a, z in zip(bounds, stops)]


def unit_titles(bounds: list, lines: list, heads: list) -> list:
    stops = list(bounds[1:]) + [len(lines)]
    titles = []
    for a, z in zip(bounds, stops):
        head = next((h["text"] for h in heads if a <= h["line"] < z), None)
        if head is None:
            head = next((ln.strip() for ln in lines[a:z] if ln.strip()), "")
        titles.append(head)
    return titles


def ordinal_opener(title: str) -> bool:
    t = title.strip()
    return bool(shape._ORD_RE.match(t)) and len(t.split()) <= _MAX_TITLE_WORDS


def plausible(spans: list, cfg: dict) -> tuple[bool, list]:
    """Gate a candidate partition against count/size priors; True means acceptable."""
    n = len(spans)
    if n < 1:
        return False, ["no units"]
    cap = cfg.get("max_chapters", 80)
    if n > cap:
        return False, [f"{n} units exceed max_chapters {cap}"]
    median = statistics.median(spans)
    if n >= _OVERSPLIT_UNITS and median < _OVERSPLIT_MEDIAN:
        return False, [f"{n} units at median {median / 1000:.1f}k chars — over-split"]
    return True, []


def missing_ordinals(titles: list) -> set:
    nums = shape.ordinals(titles)
    missing: set = set()
    for r in (r for r in shape._runs(nums) if len(r) >= 3):
        missing |= set(range(r[0], r[-1] + 1)) - set(r)
    return missing


def diagnose(spans: list, titles: list) -> list:
    """Human-readable shape verdicts for the refinement report."""
    notes = []
    n = len(spans)
    if not n:
        return notes
    median = statistics.median(spans)
    if n >= _OVERSPLIT_UNITS and median < _OVERSPLIT_MEDIAN:
        notes.append(f"{n} units at median {median / 1000:.1f}k chars — over-split")
    over = [i + 1 for i, s in enumerate(spans) if s >= OVERSIZED_CHARS]
    if over:
        notes.append("oversized unit(s) " + ", ".join(str(i) for i in over[:4])
                      + " — under-split suspect")
    missing = sorted(missing_ordinals(titles))
    if missing:
        notes.append("ordinal gap: missing " + ", ".join(str(m) for m in missing[:6]))
    runs = [r for r in shape._runs(shape.ordinals(titles)) if len(r) >= 3]
    if len(runs) > 1:
        notes.append(f"{len(runs)} ordinal runs — numbering restarts (parts?)")
    return notes
