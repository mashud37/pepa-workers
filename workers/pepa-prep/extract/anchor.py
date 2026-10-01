"""Body-heading index, multi-line assembly, fuzzy title matching, and verification."""
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

from .text import _is_heading, drop_keys, hdr_key, norm

_FUZZY_WINDOWED = 0.75
_FUZZY_GLOBAL = 0.85
_AMBIGUITY_GAP = 0.05
_TOL = 2
_VERIFY_KEEP = 0.70
_MERGE_GAP = 1.6
_MERGE_SIZE = 0.6
_OPENER_FRACTION = 0.25
_MIN_CONTAIN = 8
_MIN_DERIVE = 3

_NUM_PREFIX_RE = re.compile(r"^(?:(?:chapter|kapitel|part|teil) )?[0-9ivxlcdm]{1,7} ")


def text_key(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _variants(text: str) -> list:
    key = text_key(text)
    out = [key]
    stripped = _NUM_PREFIX_RE.sub("", key)
    if stripped and stripped != key:
        out.append(stripped)
    return out


def _merges(cur: dict, ln: dict, lh: float) -> bool:
    return (ln["y0"] - cur["y1"] <= _MERGE_GAP * lh
            and abs(ln["size"] - cur["size"]) <= _MERGE_SIZE)


def _is_candidate(ln: dict, body: float, heads: list) -> bool:
    t = ln["text"].strip()
    caps = t.isupper() and len(t) >= 3 and len(t.split()) <= 14
    return caps or _is_heading(ln, body, heads)


def _page_candidates(pno: int, lines: list, stats: dict) -> list:
    body, heads, lh = stats["body"], stats["heads"], stats["lh"]
    cands: list = []
    cur = None
    for ln in lines:
        if not _is_candidate(ln, body, heads):
            cur = None
            continue
        if cur is not None and _merges(cur, ln, lh):
            cur["text"] = norm(cur["text"] + " " + ln["text"])
            cur["y1"] = ln["y1"]
        else:
            cur = {
                "page": pno,
                "text": norm(ln["text"]),
                "y1": ln["y1"],
                "size": ln["size"],
            }
            cands.append(cur)
    return cands


def _page_lines(page: list, dk: set) -> list:
    lines = []
    for block in page:
        for ln in block:
            if ln["text"].strip() and hdr_key(ln["text"]) not in dk:
                lines.append(ln)
    return lines


def heading_index(pages: list, dims: list, stats: dict) -> list:
    """Per-page heading candidates with multi-line headings assembled into one.

    Args:
        pages: Per-page line blocks from doc_lines().
        dims: Per-page (width, height) from doc_dims().
        stats: {"body", "heads", "lh"} from doc_stats().

    Returns:
        [{"page", "text"}] with 0-based pages, reading order preserved.
    """
    dk = drop_keys(pages)
    out: list = []
    for pno, page in enumerate(pages):
        lines = _page_lines(page, dk)
        cands = _page_candidates(pno, lines, stats)
        if lines and lines[0]["y0"] > _OPENER_FRACTION * dims[pno][1]:
            opener = norm(lines[0]["text"])
            if opener and all(c["text"] != opener for c in cands):
                cands.insert(0, {"page": pno, "text": opener})
        out.extend({"page": c["page"], "text": c["text"]} for c in cands)
    return out


def _ratio(a: str, b: str) -> float:
    sm = SequenceMatcher(None, a, b)
    if sm.real_quick_ratio() < _FUZZY_WINDOWED or sm.quick_ratio() < _FUZZY_WINDOWED:
        return 0.0
    return sm.ratio()


def _pairs(x: str, y: str) -> list:
    pairs = [(x, y)]
    truncatable = min(len(x), len(y)) >= max(_MIN_CONTAIN, 0.4 * max(len(x), len(y)))
    if truncatable and len(y) > len(x) + 4:
        pairs += [(x, y[:len(x)]), (x, y[-len(x):])]
    elif truncatable and len(x) > len(y) + 4:
        pairs += [(x[:len(y)], y), (x[-len(y):], y)]
    return pairs


def _score(a: str, b: str) -> float:
    combos = []
    for x in _variants(a):
        for y in _variants(b):
            if x and y:
                combos.append((x, y))
    ratios = []
    for x, y in combos:
        for p, q in _pairs(x, y):
            ratios.append(_ratio(p, q))
    return max(ratios, default=0.0)


def _matches_exactly(v: str, text: str) -> bool:
    for w in _variants(text):
        if v == w or (len(w) >= _MIN_CONTAIN and (v in w or w in v)):
            return True
    return False


def _exact(title: str, cands: list) -> dict | None:
    for v in _variants(title):
        if len(v) < _MIN_CONTAIN:
            continue
        for c in cands:
            if _matches_exactly(v, c["text"]):
                return {"page": c["page"], "score": 1.0}
    return None


def _fuzzy(title: str, cands: list, threshold: float, need_gap: bool = False) -> dict | None:
    scored = sorted(((_score(title, c["text"]), c["page"]) for c in cands), reverse=True)
    if not scored or scored[0][0] < threshold:
        return None
    best_score, best_page = scored[0]
    if need_gap:
        runner = 0.0
        for s, p in scored[1:]:
            if p != best_page:
                runner = s
                break
        if best_score - runner < _AMBIGUITY_GAP:
            return None
    return {"page": best_page, "score": best_score}


def match(title: str, index: list, target: int | None) -> dict | None:
    """Find the body-heading page for a title: exact tier, then fuzzy tier.

    A known target page restricts the search to ±2 pages and lowers the fuzzy
    threshold; without one the whole book is searched and an ambiguity gap over
    the runner-up is required.

    Returns:
        {"page", "score"} for the best match, or None.
    """
    if not title:
        return None
    if target is not None:
        window = [c for c in index if abs(c["page"] - target) <= _TOL]
        hit = _exact(title, window) or _fuzzy(title, window, _FUZZY_WINDOWED)
        if hit is not None:
            return hit
        wide = [c for c in index if _TOL < abs(c["page"] - target) <= 2 * _TOL]
        return _fuzzy(title, wide, _FUZZY_GLOBAL)
    return _exact(title, index) or _fuzzy(title, index, _FUZZY_GLOBAL, need_gap=True)


def derive_offset(entries: list, index: list) -> int | None:
    """Calibrate printed-page offset by modal voting over strong title matches.

    Each entry votes once per distinct (matched page − printed number); the true
    offset gets a vote from every chapter opening while running-head repeats
    scatter, so the mode is robust to per-chapter headers.
    """
    diffs: Counter = Counter()
    for e in entries:
        if not e["roman"]:
            votes = {c["page"] - e["no"] for c in index
                     if _score(e["title"], c["text"]) >= _FUZZY_GLOBAL}
            diffs.update(votes)
    if not diffs:
        return None
    off, cnt = diffs.most_common(1)[0]
    return off if cnt >= _MIN_DERIVE else None


def verify(candidates: list, index: list) -> dict:
    """Anchor candidate boundaries to body headings.

    Args:
        candidates: [{"title", "page" | None}] with 0-based arithmetic pages.
        index: Heading index from heading_index().

    Returns:
        {"bounds", "verified_fraction"}: bounds as [{"title", "page"}], strictly
        increasing. A matched heading keeps the arithmetic page when the heading
        follows it by ≤2 pages (dividers and full-page art open the unit);
        unmatched candidates keep their arithmetic page only when ≥70% of
        siblings verified.
    """
    hits = []
    for cand in candidates:
        target = cand.get("page")
        hit = match(cand.get("title", ""), index, target)
        if hit is not None:
            page = hit["page"]
            if target is not None and 0 <= page - target <= _TOL:
                page = target
            hits.append((cand, page, True))
        elif target is not None:
            hits.append((cand, target, False))
    if not candidates:
        return {"bounds": [], "verified_fraction": 0.0}
    frac = sum(1 for _, _, ok in hits if ok) / len(candidates)
    keep_arith = frac >= _VERIFY_KEEP
    bounds = sorted(
        ({"title": cand.get("title", ""), "page": page, "matched": ok}
         for cand, page, ok in hits if ok or keep_arith),
        key=lambda b: b["page"],
    )
    out: list = []
    for b in bounds:
        if not out or b["page"] > out[-1]["page"]:
            out.append(b)
    return {"bounds": out, "verified_fraction": frac}
