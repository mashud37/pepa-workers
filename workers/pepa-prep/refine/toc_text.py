"""Text-native printed-ToC recovery: locate entries in the markdown, anchor titles."""
import re

from extract import anchor
from extract.anchor import text_key
from extract.shape import _ORD_RE

from . import signals

_ENTRY_MAX = 100
_PROSE_CHARS = 140
_SCAN_CAP = 500
_MAX_TOP = 80
_MIN_ALPHA = 3
_NEAR_LINES = 3
_ANCHOR_SCORE = 0.85
_PROSE_MIN = 600
_TRAIL_RE = re.compile(r"(?:[.·\s]{2,}|\s+)(?:\d{1,4}|[ivxlcdm]{1,4})\s*$", re.IGNORECASE)
_DOTS_RE = re.compile(r"^[.·\d\s]*$")
_MARKER_RE = re.compile(r"^(?:chapter|kapitel|part|teil)\s+(?:\d{1,3}|[ivxlcdm]+|\w+)\s*$",
                        re.IGNORECASE)
_HIER_RE = re.compile(r"^\d{1,2}\.\d")


def _is_toc_word(text: str, keys: set) -> bool:
    hk = text_key(text)
    return any(hk == k or hk.startswith(k + " ") or hk.startswith("inhalt") for k in keys)


def _toc_head(lines: list, heads: list, toc_words: set) -> int | None:
    front = min(len(lines), max(200, len(lines) // 10))
    keys = {text_key(w) for w in toc_words}
    for h in heads:
        if h["line"] < front and _is_toc_word(h["text"], keys):
            return h["line"]
    for i, ln in enumerate(lines[:front]):
        t = ln.strip()
        if t and len(t) <= 40 and text_key(t) in keys:
            return i
    return None


def _collect(lines: list, start: int) -> dict:
    """Scan lines after the ToC heading for entry-shaped rows.

    Returns:
        {"rows": [(line, text)], "end": last line index still inside the ToC}.
    """
    rows, seen, prose_run, end = [], set(), 0, start
    for i in range(start + 1, min(start + 1 + _SCAN_CAP, len(lines))):
        t = lines[i].strip()
        if not t:
            continue
        clean = t.lstrip("#").strip()
        if signals._HEAD_RE.match(lines[i]) and text_key(clean) in seen:
            break
        if len(clean) >= _PROSE_CHARS:
            prose_run += 1
            if prose_run >= 2:
                break
            continue
        prose_run = 0
        if len(clean) <= _ENTRY_MAX:
            rows.append((i, clean))
            seen.add(text_key(clean))
            end = i
    return {"rows": rows, "end": end}


def _entries(rows: list) -> list:
    out = []
    for line, text in rows:
        t = _TRAIL_RE.sub("", text).strip()
        if _DOTS_RE.match(t) or sum(c.isalpha() for c in t) < _MIN_ALPHA:
            continue
        out.append({
            "line": line,
            "text": t,
            "marker": bool(_MARKER_RE.match(t)),
            "hier": bool(_HIER_RE.match(t)),
        })
    return out


def _marker_pairs(entries: list) -> list:
    top = []
    for j, e in enumerate(entries):
        if not e["marker"]:
            continue
        top.append(e)
        if j + 1 < len(entries) and not entries[j + 1]["marker"]:
            top.append(entries[j + 1])
    return top


def _top_level(entries: list) -> list:
    markers = [e for e in entries if e["marker"]]
    if len(markers) >= 3:
        return _marker_pairs(entries)[:_MAX_TOP]
    nums = [e for e in entries
            if not e["hier"] and _ORD_RE.match(e["text"]) and e["text"][0].isdigit()]
    if len(nums) >= 3:
        return nums[:_MAX_TOP]
    return [e for e in entries if not e["hier"]][:_MAX_TOP]


def _in_list_context(lines: list, idx: int) -> bool:
    nxt = ""
    for ln in lines[idx + 1:idx + 4]:
        if ln.strip():
            nxt = ln.strip()
            break
    return bool(_MARKER_RE.match(nxt.lstrip("#").strip())) or bool(
        signals._HEAD_RE.match(nxt) and _MARKER_RE.match(nxt.lstrip("#").strip()))


def _content_bearing(lines: list, idx: int) -> bool:
    prose = sum(len(ln) for ln in lines[idx + 1:idx + 21]
                if ln.strip() and not ln.lstrip().startswith("#"))
    return prose >= _PROSE_MIN and not _in_list_context(lines, idx)


def _title_hits(title: str, index: list, prev: int) -> list:
    hits = [(anchor._score(title, c["text"]), c["line"]) for c in index
            if c["line"] > prev]
    strong = [(s, ln) for s, ln in hits if s >= _ANCHOR_SCORE]
    if not strong:
        return []
    best = max(s for s, _ in strong)
    return sorted(ln for s, ln in strong if s >= best - 0.05)


def _anchor_titles(top: list, cands: list, rng: range, lines: list) -> list:
    """Anchor ToC titles to body candidates in ToC order: for each title take
    the earliest near-best match after the previous anchor, preferring
    content-bearing lines (running heads and divider mini-lists lose)."""
    index = [c for c in cands if c["line"] not in rng]
    out: list = []
    prev = -1
    for e in top:
        hits = _title_hits(e["text"], index, prev)
        solid = [ln for ln in hits if _content_bearing(lines, ln)]
        hits = solid or hits
        if not hits or (out and hits[0] - out[-1][0] <= _NEAR_LINES):
            continue
        out.append((hits[0], e["text"]))
        prev = hits[0]
    return out


def recover(lines: list, heads: list, toc_words: set, cands: list | None = None) -> dict | None:
    """Find the printed ToC inside the markdown and anchor its titles to headings.

    Args:
        lines: Concatenated book lines.
        heads: Markdown headings from signals.headings().
        toc_words: Configured contents-heading words.
        cands: Anchor candidates (defaults to heads).

    Returns:
        {"rng": range, "expected": int, "anchors": [(line, title)]} or None
        when no ToC heading is found in the front window.
    """
    start = _toc_head(lines, heads, toc_words)
    if start is None:
        return None
    collected = _collect(lines, start)
    top = _top_level(_entries(collected["rows"]))
    rng = range(start, collected["end"] + 1)
    return {"rng": rng, "expected": len(top),
            "anchors": _anchor_titles(top, cands or heads, rng, lines)}
