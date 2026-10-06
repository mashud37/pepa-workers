"""Printed table-of-contents detection, entry parsing, and page-offset calibration."""
import re
from collections import Counter

from . import pdf
from .text import norm

_SEARCH_CAP = 40
_SEARCH_FRACTION = 0.10
_MIN_ROWS = 5
_MIN_ROWS_TITLED = 3
_EXTEND_MIN_ROWS = 4
_ROW_DENSITY = 0.40
_RIGHT_BAND = 0.15
_MIN_ARABIC = 3
_MAX_INVERSIONS = 0.30
_FOLIO_MIN = 10
_FOLIO_SHARE = 0.60
_OCR_OFFSETS_TRIED = 5
_OCR_OPENING_WORDS = 30
_OPENER_SHARE = 0.70
_LIST_HEADINGS = {
    "tables",
    "figures",
    "illustrations",
    "plates",
    "maps",
}

_NUM_WORDS = (
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?"
    r"|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    r"|one|two|three|four|five|six|seven|eight|nine"
    r"|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
    r"|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth"
    r"|eighteenth|nineteenth|twentieth"
)
_LEADER_RE = re.compile(r"(?:[.·․…] ?){2,}\s*$")
_INLINE_RE = re.compile(r"^(?P<title>.{3,}?)(?:(?:[.·․…] ?){2,}|\s{2,})(?P<no>\S{1,7})$")
_LOOSE_RE = re.compile(r"^(?P<title>\S.{2,}?)\s+(?P<no>\S{1,7})\s*$")
_ARABIC_RE = re.compile(r"^\d{1,4}$")
_ROMAN_RE = re.compile(r"^[ivxlcdm]{1,7}$", re.IGNORECASE)
_FOLIO_RE = re.compile(r"^\d{1,4}$")
_PART_RE = re.compile(r"^(?:part|teil|unit)\b", re.IGNORECASE)
_DOTTED_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){0,3})[.:)]?\s")
_ORDINAL_RE = re.compile(
    r"^(?:(?:chapter|kapitel)\s+\S|[ivxlcdm]{1,7}[.:)]?\s|(?:" + _NUM_WORDS + r")[.:)]?\s)",
    re.IGNORECASE,
)
_VETO_RE = re.compile(
    r"^(?:list of (?:figures|tables|illustrations|maps|plates)"
    r"|(?:abbildungs|tabellen)verzeichnis)\b",
    re.IGNORECASE,
)
_OCR_DIGITS = str.maketrans({
    "I": "1",
    "l": "1",
    "|": "1",
    "O": "0",
    "o": "0",
    "S": "5",
    "s": "5",
    "B": "8",
})
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman(token: str) -> int:
    total = 0
    values = [_ROMAN_VALUES[c] for c in token.lower()]
    for i, v in enumerate(values):
        total += -v if i + 1 < len(values) and v < values[i + 1] else v
    return total


def is_roman(label: str) -> bool:
    """Whether a printed page number is a roman numeral, as books number their front matter."""
    number = _page_no(label)
    return number is not None and number["roman"]


def _page_no(token: str) -> dict | None:
    t = _LEADER_RE.sub("", token).strip().strip("()[]")
    if not t:
        return None
    if _ARABIC_RE.match(t):
        return {"no": int(t), "roman": False}
    if _ROMAN_RE.match(t):
        return {"no": _roman(t), "roman": True}
    repaired = t.translate(_OCR_DIGITS).replace(" ", "")
    if _ARABIC_RE.match(repaired) and any(c.isdigit() for c in t):
        return {"no": int(repaired), "roman": False}
    return None


def _rows(page: list) -> list:
    flat_lines = []
    for block in page:
        for ln in block:
            if ln["text"].strip():
                flat_lines.append(ln)
    lines = sorted(flat_lines, key=lambda ln: (ln["y0"], ln["x0"]))
    rows: list = []
    for ln in lines:
        if rows and _same_row(rows[-1], ln):
            rows[-1]["lines"].append(ln)
            rows[-1]["y0"] = min(rows[-1]["y0"], ln["y0"])
            rows[-1]["y1"] = max(rows[-1]["y1"], ln["y1"])
        else:
            rows.append({"lines": [ln], "y0": ln["y0"], "y1": ln["y1"]})
    for row in rows:
        row["lines"].sort(key=lambda ln: ln["x0"])
        row["x0"] = row["lines"][0]["x0"]
        row["x1"] = max(ln["x1"] for ln in row["lines"])
        row["text"] = norm(" ".join(ln["text"] for ln in row["lines"]))
        chars = sum(len(ln["text"].strip()) for ln in row["lines"])
        bold = sum(len(ln["text"].strip()) for ln in row["lines"] if ln.get("bold"))
        row["bold"] = chars > 0 and bold / chars > 0.5
    return rows


def _same_row(row: dict, ln: dict) -> bool:
    overlap = min(row["y1"], ln["y1"]) - max(row["y0"], ln["y0"])
    height = min(row["y1"] - row["y0"], ln["y1"] - ln["y0"])
    return height > 0 and overlap >= 0.5 * height


def _row_entry(row: dict, width: float, col_right: float) -> dict | None:
    lines = row["lines"]
    right_edge = row["x1"] >= col_right - _RIGHT_BAND * width
    if len(lines) > 1:
        no = _page_no(lines[-1]["text"].strip())
        if no is not None and (right_edge or _LEADER_RE.search(lines[-2]["text"])):
            title = _LEADER_RE.sub("", norm(" ".join(ln["text"] for ln in lines[:-1]))).strip()
            if title:
                return {
                    "title": title,
                    "no": no["no"],
                    "roman": no["roman"],
                    "x0": row["x0"],
                    "bold": row["bold"],
                }
    m = _INLINE_RE.match(row["text"])
    if m and right_edge:
        no = _page_no(m.group("no"))
        if no is not None:
            return {
                "title": m.group("title").strip(),
                "no": no["no"],
                "roman": no["roman"],
                "x0": row["x0"],
                "bold": row["bold"],
            }
    return None


def _loose_entry(row: dict, page_count: int) -> dict | None:
    m = _LOOSE_RE.match(row["text"])
    if not m:
        return None
    no = _page_no(m.group("no"))
    if no is None or (not no["roman"] and no["no"] > max(2 * page_count, 400)):
        return None
    return {
        "title": m.group("title").strip(),
        "no": no["no"],
        "roman": no["roman"],
        "x0": row["x0"],
        "bold": row["bold"],
    }


def _page_entries(rows: list, width: float, page_count: int) -> dict:
    """Map row index → parsed entry, falling back to single-space rows when the
    page has no aligned number column and the loose values read like page numbers."""
    col_right = max((r["x1"] for r in rows), default=0.0)
    strict = {}
    for i, r in enumerate(rows):
        entry = _row_entry(r, width, col_right)
        if entry:
            strict[i] = entry
    if len(strict) >= _MIN_ROWS_TITLED:
        return strict
    loose = {}
    for i, r in enumerate(rows):
        entry = _loose_entry(r, page_count)
        if entry:
            loose[i] = entry
    arabic = [e["no"] for e in loose.values() if not e["roman"]]
    if len(loose) >= _MIN_ROWS and _inversions(arabic) <= _MAX_INVERSIONS:
        return loose
    return strict


def _has_toc_heading(rows: list, toc_words: set) -> bool:
    return any(row["text"].casefold() in toc_words for row in rows[:4])


def _has_veto(rows: list) -> bool:
    return any(_VETO_RE.match(row["text"]) for row in rows[:4])


def is_toc_page(page: list, width: float, page_count: int, toc_words: set) -> bool:
    rows = _rows(page)
    if not rows or _has_veto(rows):
        return False
    entries = _page_entries(rows, width, page_count)
    min_rows = _MIN_ROWS_TITLED if _has_toc_heading(rows, toc_words) else _MIN_ROWS
    return len(entries) >= min_rows and len(entries) >= _ROW_DENSITY * len(rows)


def _extends(page: list, width: float, page_count: int) -> bool:
    rows = _rows(page)
    if not rows or _has_veto(rows):
        return False
    entries = _page_entries(rows, width, page_count)
    return len(entries) >= _EXTEND_MIN_ROWS and len(entries) >= _ROW_DENSITY * len(rows)


def find_toc(pages: list, widths: list, toc_words: set) -> range | None:
    """Locate the printed table of contents in the front of the book.

    Args:
        pages: Per-page line blocks from doc_lines().
        widths: Per-page widths from doc_widths().
        toc_words: Casefolded contents-heading words from config.

    Returns:
        Page range of the ToC, or None when no page passes the structural test.
    """
    n = len(pages)
    limit = min(n, _SEARCH_CAP, max(6, round(n * _SEARCH_FRACTION)))
    for pno in range(limit):
        if is_toc_page(pages[pno], widths[pno], n, toc_words):
            end = pno + 1
            while end < n and _extends(pages[end], widths[end], n):
                end += 1
            return range(pno, end)
    return None


def find_lists(pages: list, widths: list) -> set:
    """Pages in the front window that are figure/table/plate lists (ToC-shaped
    pages under a veto heading): navigation furniture to exclude from units."""
    n = len(pages)
    limit = min(n, _SEARCH_CAP, max(6, round(n * _SEARCH_FRACTION)))
    hits: set = set()
    for pno in range(limit):
        rows = _rows(pages[pno])
        if not rows or not _has_veto(rows):
            continue
        if len(_page_entries(rows, widths[pno], n)) >= _MIN_ROWS_TITLED:
            hits.add(pno)
            end = pno + 1
            while end < limit and _extends(pages[end], widths[end], n):
                hits.add(end)
                end += 1
    return hits


def _inversions(nos: list) -> float:
    if len(nos) < 2:
        return 0.0
    return sum(1 for a, b in zip(nos, nos[1:]) if b < a) / (len(nos) - 1)


def _is_furniture(text: str, toc_words: set) -> bool:
    t = norm(text).casefold()
    if t in toc_words or _FOLIO_RE.match(t):
        return True
    rest = " ".join(w for w in t.split() if w not in toc_words and not _FOLIO_RE.match(w))
    return not rest


def _numbered_depth(title: str) -> int | None:
    t = title.strip()
    if _PART_RE.match(t):
        return 0
    m = _DOTTED_RE.match(t)
    if m:
        return min(m.group(1).count(".") + 1, 3)
    return 1 if _ORDINAL_RE.match(t) else None


def _assign_levels(entries: list) -> None:
    """Level 0 = part/unit rows, 1 = chapters, 2+ = subsections.

    Numbered rows get their numbering depth. Unnumbered rows are chapter-level
    when the ToC has no numbering at all, when they sit before the first or
    after the last numbered row (front/back matter), or when bold marks them
    out among mostly non-bold rows; otherwise they are subsections.
    """
    depths = [_numbered_depth(e["title"]) for e in entries]
    numbered = [i for i, d in enumerate(depths) if d is not None and d >= 1]
    bold_minority = sum(1 for e in entries if e["bold"]) < 0.5 * len(entries)
    for i, e in enumerate(entries):
        if depths[i] is not None:
            e["level"] = depths[i]
        elif (not numbered or i < numbered[0] or i > numbered[-1]
              or (bold_minority and e["bold"])):
            e["level"] = 1
        else:
            e["level"] = 2


def parse_entries(pages: list, toc_range: range, widths: list,
                  toc_words: set = frozenset()) -> list:
    """Parse ToC rows into entries; abstain (return []) when the parse looks wrong.

    Returns:
        [{"title", "no", "roman", "level"}] with level 0 as the top division.
    """
    entries: list = []
    open_title = ""
    for pno in toc_range:
        rows = _rows(pages[pno])
        page_entries = _page_entries(rows, widths[pno], len(pages))
        for i, row in enumerate(rows):
            if _is_furniture(row["text"], toc_words):
                continue
            entry = page_entries.get(i)
            if entry is None:
                open_title = norm(f"{open_title} {row['text']}") if open_title else row["text"]
                continue
            if open_title:
                entry["title"] = norm(f"{open_title} {entry['title']}")
                open_title = ""
            entries.append(entry)
    arabic = [e["no"] for e in entries if not e["roman"]]
    if len(arabic) < _MIN_ARABIC or _inversions(arabic) > _MAX_INVERSIONS:
        return []
    _assign_levels(entries)
    return entries


def ocr_contents_starts(pages: list, contents: list) -> list:
    """The 0-based chapter start pages a scanned book's printed contents names.

    Args:
        pages: OCR text of every page, left-out pages included.
        contents: 0-based pages the user marked as Contents.

    Returns:
        Sorted start pages, or an empty list when fewer than two can be placed.
    """
    if not contents:
        return []
    lined = []
    for text in pages:
        lined.append([[{"text": line} for line in text.splitlines()]])
    lines = []
    for page in contents:
        lines.extend(pages[page].splitlines())
    entries = []
    for line in lines:
        if _VETO_RE.match(norm(line)) or norm(line).casefold() in _LIST_HEADINGS:
            break
        entry = _loose_entry({"text": norm(line), "x0": 0, "bold": False}, len(pages))
        if entry:
            entry["title"] = _LEADER_RE.sub("", entry["title"]).strip()
            entries.append(entry)
    arabic = [e["no"] for e in entries if not e["roman"]]
    if len(arabic) < _MIN_ARABIC or _inversions(arabic) > _MAX_INVERSIONS:
        return []
    _assign_levels(entries)
    chapters = [e for e in entries if e["level"] <= 2 and not e["roman"]]
    lengths = sorted(len(text) for text in pages if text.strip())
    short = _OPENER_SHARE * lengths[len(lengths) // 2] if lengths else 0
    best = {"hits": 0, "starts": set()}
    for offset, _ in _folio_votes(lined).most_common(_OCR_OFFSETS_TRIED):
        placed = _place_titles(chapters, pages, offset, short)
        if placed["hits"] > best["hits"]:
            best = placed
    starts = best["starts"] - set(contents)
    if best["hits"] < 2 or len(starts) < 2:
        return []
    return sorted(starts)


def _title_on_page(title: str, text: str) -> bool:
    """Whether a contents title's first words open a page's OCR text, its chapter number left aside."""
    words = norm(title).casefold().split()
    if words and (not any(c.isalpha() for c in words[0]) or _ROMAN_RE.match(words[0])):
        words = words[1:]
    if not words:
        return False
    opening = " ".join(text.casefold().replace("|", " ").split()[:_OCR_OPENING_WORDS])
    return " ".join(words[:3]) in opening


def _place_titles(entries: list, pages: list, offset: int, short: float) -> dict:
    """Each chapter's start page at a page offset, moved up to two pages to the first page that opens with its title.

    A title found away from the offset moves the offset for the entries after it, as unnumbered plates do.
    A subsection-level entry starts a chapter only when its title opens a short page, as chapter openers are.

    Returns:
        {"hits": titles found on their pages, "starts": set of 0-based start pages}.
    """
    hits = 0
    starts = set()
    for entry in entries:
        page = entry["no"] + offset
        found = False
        for shift in (-2, -1, 0, 1, 2):
            near = page + shift
            if 0 <= near < len(pages) and _title_on_page(entry["title"], pages[near]):
                page = near
                offset = near - entry["no"]
                hits += 1
                found = True
                break
        if not 0 <= page < len(pages):
            continue
        if entry["level"] <= 1 or (found and len(pages[page]) < short):
            starts.add(page)
    return {"hits": hits, "starts": starts}


def label_offset(doc, entries: list) -> int | None:
    """Offset from PDF page labels: 0-based pdf index = printed number + offset."""
    arabic = [e for e in entries if not e["roman"]]
    if not arabic:
        return None
    probes = [arabic[len(arabic) // 4], arabic[len(arabic) // 2], arabic[-1]]
    diffs = Counter()
    for e in probes:
        try:
            hit = pdf.page_with_label(doc, str(e["no"]))
        except Exception:
            return None
        if hit is not None:
            diffs[hit - e["no"]] += 1
    if not diffs:
        return None
    off, cnt = diffs.most_common(1)[0]
    return off if cnt >= 2 else None


_FOLIO_EDGE_RE = re.compile(r"^(\d{1,4})\b(?:\s|$)|\s(\d{1,4})$")


def _flat_lines(page: list) -> list:
    flat = []
    for block in page:
        for ln in block:
            if ln["text"].strip():
                flat.append(ln)
    return flat


def _folio_digits(m, t: str) -> str:
    for g in m.groups():
        if g:
            return g
    return t


def _folio_votes(pages: list) -> Counter:
    """How many printed page numbers in headers and footers point to each offset between PDF page and printed number."""
    diffs: Counter = Counter()
    for pno, page in enumerate(pages):
        flat = _flat_lines(page)
        for ln in flat[:2] + flat[-2:]:
            t = ln["text"].strip()
            m = _FOLIO_RE.match(t) or _FOLIO_EDGE_RE.search(t)
            if m:
                folio = _folio_digits(m, t)
                diffs[pno - int(folio)] += 1
    return diffs


def folio_offset(pages: list) -> int | None:
    """Offset from printed folio lines in page headers/footers (modal, gated)."""
    diffs = _folio_votes(pages)
    if not diffs:
        return None
    off, cnt = diffs.most_common(1)[0]
    return off if cnt >= _FOLIO_MIN and cnt / sum(diffs.values()) >= _FOLIO_SHARE else None
