"""Chapter-shape plausibility: count/size priors, ordinal sequences, boundary repair."""
import re
import statistics

_MIN_CHAPTER_CHARS = 1500
_OVERSPLIT_UNITS = 8
_OVERSPLIT_MEDIAN_PAGES = 3
_TOC_OVERLAP = 0.5
_BLANK_PAGE_CHARS = 200
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}

_ORD_RE = re.compile(
    r"^(?:(?:chapter|kapitel|part|teil)\s+)?(\d{1,3}|[ivxlcdm]{1,7})\b[.:)]?(?:\s|$)",
    re.IGNORECASE,
)


def ordinals(titles: list) -> list:
    out = []
    for t in titles:
        m = _ORD_RE.match(t.strip())
        if not m:
            out.append(None)
            continue
        tok = m.group(1)
        if tok.isdigit():
            out.append(int(tok))
        else:
            values = [_ROMAN_VALUES.get(c, 0) for c in tok.lower()]
            out.append(sum(-v if i + 1 < len(values) and v < values[i + 1] else v
                           for i, v in enumerate(values)))
    return out


def _runs(nums: list) -> list:
    runs: list = []
    for n in nums:
        if n is None:
            continue
        if runs and n > runs[-1][-1]:
            runs[-1].append(n)
        else:
            runs.append([n])
    return runs


def spans(bounds: list, page_count: int) -> list:
    starts = [b["page"] for b in bounds]
    return [z - a for a, z in zip(starts, starts[1:] + [page_count])]


def plausible(bounds: list, page_count: int, cfg: dict) -> dict:
    """Gate a candidate split against count/size priors.

    Returns:
        {"ok", "notes"}: ok is True when the split is acceptable.
    """
    n = len(bounds)
    if n < 2:
        return {"ok": False, "notes": ["fewer than 2 units"]}
    if n > cfg.get("max_chapters", 80):
        return {"ok": False,
                "notes": [f"{n} units exceed max_chapters {cfg.get('max_chapters', 80)}"]}
    median_span = statistics.median(spans(bounds, page_count))
    if n >= _OVERSPLIT_UNITS and median_span < _OVERSPLIT_MEDIAN_PAGES:
        return {"ok": False,
                "notes": [f"{n} units at median {median_span:.0f} page(s): over-split"]}
    return {"ok": True, "notes": []}


def diagnose(bounds: list, page_count: int) -> list:
    """Human-readable shape signals for warnings and the evaluation report."""
    notes = []
    n = len(bounds)
    if not n:
        return notes
    median_span = statistics.median(spans(bounds, page_count))
    nums = ordinals([b["title"] for b in bounds])
    runs = [r for r in _runs(nums) if len(r) >= 3]
    for r in runs:
        missing = sorted(set(range(r[0], r[-1] + 1)) - set(r))
        if missing:
            notes.append("ordinal gap: missing "
                         + ", ".join(str(m) for m in missing[:6]))
    if len(runs) > 1:
        notes.append(f"{len(runs)} ordinal runs: numbering restarts (parts?)")
    if n >= _OVERSPLIT_UNITS and median_span < 6:
        notes.append(f"{n} units at median {median_span:.0f} page(s): check for over-split")
    return notes


def _unit_chars(pages: list, start: int, stop: int) -> int:
    total = 0
    for page in pages[start:stop]:
        for block in page:
            for ln in block:
                total += len(ln["text"].strip())
    return total


def _backfill(bounds: list, pages: list) -> int:
    """Pull each boundary back over up to two near-blank pages (blank versos and
    title-only part dividers open the unit that follows them)."""
    moved = 0
    for i, b in enumerate(bounds):
        floor = bounds[i - 1]["page"] + 1 if i else 0
        page = b["page"]
        for _ in range(2):
            if page - 1 < floor:
                break
            chars = _unit_chars(pages, page - 1, page)
            if chars >= _BLANK_PAGE_CHARS:
                break
            page -= 1
            if chars > 0:
                break
        if page != b["page"]:
            b["page"] = page
            moved += 1
    return moved


def _drop_furniture(bounds: list, pages: list, drop_pages: set) -> tuple[list, int]:
    kept = []
    dropped = 0
    for i, b in enumerate(bounds):
        stop = bounds[i + 1]["page"] if i + 1 < len(bounds) else len(pages)
        overlap = sum(1 for p in range(b["page"], stop) if p in drop_pages)
        if stop > b["page"] and overlap / (stop - b["page"]) >= _TOC_OVERLAP:
            dropped += 1
        else:
            kept.append(b)
    return (kept, dropped) if dropped and len(kept) >= 2 else (bounds, 0)


def _drop_leading(bounds: list, pages: list) -> int:
    dropped = 0
    while len(bounds) > 2 and not bounds[0].get("matched", True):
        if _unit_chars(pages, bounds[0]["page"], bounds[1]["page"]) >= _MIN_CHAPTER_CHARS:
            break
        bounds.pop(0)
        dropped += 1
    return dropped


def _merge_small(bounds: list, pages: list) -> int:
    merged = 0
    i = 0
    while i < len(bounds) and len(bounds) > 2:
        stop = bounds[i + 1]["page"] if i + 1 < len(bounds) else len(pages)
        if (bounds[i].get("matched", True)
                or _unit_chars(pages, bounds[i]["page"], stop) >= _MIN_CHAPTER_CHARS):
            i += 1
            continue
        bounds.pop(i + 1 if i + 1 < len(bounds) else i)
        merged += 1
    return merged


def repair(bounds: list, pages: list, drop_pages: set) -> dict:
    """Post-process boundaries: drop contents/figure-list units, drop unverified
    leading fragments, merge sub-minimum units forward, backfill over dividers.

    Interior sub-minimum units merge forward (a divider opens the next chapter);
    a trailing one merges backward, both keep the content. The leading drop
    loses content, so it spares title-verified units. Never repairs below 2
    boundaries.

    Returns:
        {"bounds", "notes"}: notes describes every adjustment made.
    """
    bounds = [dict(b) for b in bounds]
    notes = []
    bounds, dropped = _drop_furniture(bounds, pages, drop_pages)
    if dropped:
        notes.append(f"dropped {dropped} contents/list-page unit(s)")
    dropped = _drop_leading(bounds, pages)
    if dropped:
        notes.append(f"dropped {dropped} front-matter fragment(s)")
    merged = _merge_small(bounds, pages)
    if merged:
        notes.append(f"merged {merged} sub-minimum unit(s)")
    if _backfill(bounds, pages):
        notes.append("backfilled boundaries over blank/divider pages")
    return {"bounds": bounds, "notes": notes}
