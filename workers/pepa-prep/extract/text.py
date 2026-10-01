"""Geometry-based paragraph reflow, heading detection, list and table placement, and
markdown rendering."""
import re
import statistics
import unicodedata
from collections import Counter

from . import tables as tables_mod

_TEXT_THRESHOLD = 40
_PAGE_NUM_RE = re.compile(r"^\s*(?:\d{1,4}|[ivxlcdm]{1,6})\s*$", re.IGNORECASE)
_REF_HEADING = re.compile(
    r"(?im)^\s*#*\s*(?:\d+\.?\s*)?"
    r"(references|bibliography|works cited|literature cited|reference list)\s*$"
)
_SECTION_RE = re.compile(
    r"^(?:\d+(?:\.\d+){0,3}\.?\s+\S"
    r"|(?:chapter|section|part)\s+(?:\d+|[ivxlcdm]+)\b"
    r"|abstract|introduction|background|related work|methods?|methodology"
    r"|materials and methods|results?|discussion|conclusions?|summary)\b",
    re.IGNORECASE,
)
_SENT_END = ".?!:’‘”“)\"'"
_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}
_INVISIBLE_RE = re.compile("[\u00ad\u200b\u200c\u200d\ufeff]")
_BULLET_RE = re.compile(r"^(?:[•·●▪◦⁃*]|-)\s+\S")
_NUMBER_RE = re.compile(r"^\(?(?:\d{1,2}|[a-z]|[ivx]{1,4})[.)]\s+\S")
_BULLET_STRIP_RE = re.compile(r"^(?:[•·●▪◦⁃*]|-)\s+")
_WORD_RE = re.compile(r"[^\W\d_]{2,}")
_HYPHENATED_RE = re.compile(r"[^\W\d_]{2,}-[^\W\d_]{2,}")
_HYPHEN_TAIL_RE = re.compile(r"([^\W\d_]{2,})-$")
_LEAD_WORD_RE = re.compile(r"^([^\W\d_]{2,})")
_LIST_KINDS = ("bullet", "number")


def normalise(text: str) -> str:
    """Expand ligatures, drop invisible characters, and compose accents.

    Curly quotes and dashes are left alone: pepa-sum verifies quotes against this
    text character by character.
    """
    for ligature, plain in _LIGATURES.items():
        text = text.replace(ligature, plain)
    text = _INVISIBLE_RE.sub("", text)
    return unicodedata.normalize("NFC", text)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", normalise(text)).strip()


def hdr_key(line: str) -> str | None:
    key = re.sub(r"[^a-z]", "", line.lower())
    return key if len(key) >= 5 else None


def _line_style(spans: list) -> dict:
    sizes: dict = {}
    bold = tot = 0
    for sp in spans:
        n = len(sp["text"].strip())
        if not n:
            continue
        k = round(sp["size"] * 2) / 2
        sizes[k] = sizes.get(k, 0) + n
        tot += n
        if sp.get("flags", 0) & 16 or "bold" in sp.get("font", "").lower():
            bold += n
    size = max(sizes, key=sizes.get) if sizes else 0.0
    return {"size": size, "bold": tot > 0 and bold / tot > 0.6}


def page_lines(page, flags=None) -> list:
    raw = page.get_text("dict") if flags is None else page.get_text("dict", flags=flags)
    blocks = []
    for b in raw["blocks"]:
        if b.get("type") != 0 or not b.get("lines"):
            continue
        lines = []
        for ln in b["lines"]:
            spans = ln["spans"]
            text = "".join(sp["text"] for sp in spans)
            if not text.strip():
                continue
            x0, y0, x1, y1 = ln["bbox"]
            style = _line_style(spans)
            lines.append({
                "text": text,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "size": style["size"],
                "bold": style["bold"],
            })
        if lines:
            blocks.append(lines)
    return blocks


def doc_lines(doc, page_range, flags=None) -> list:
    return [page_lines(doc[pno], flags) for pno in page_range]


def doc_dims(doc, page_range) -> list:
    return [(doc[pno].rect.width, doc[pno].rect.height) for pno in page_range]


def _line_sizes_and_heights(page: list) -> dict:
    sizes: dict = {}
    heights: list = []
    for block in page:
        for ln in block:
            n = len(ln["text"].strip())
            if n:
                sizes[ln["size"]] = sizes.get(ln["size"], 0) + n
                heights.append(ln["y1"] - ln["y0"])
    return {"sizes": sizes, "heights": heights}


def _vocabulary(pages: list) -> set:
    words: set = set()
    for page in pages:
        for block in page:
            for ln in block:
                text = ln["text"]
                words.update(w.casefold() for w in _WORD_RE.findall(text))
                words.update(c.casefold() for c in _HYPHENATED_RE.findall(text))
    return words


def doc_stats(pages: list) -> dict:
    """One pass over every line: body size, heading sizes, median line height, and the
    document's own words.

    Returns:
        {"body": most common font size, "heads": larger sizes descending,
        "lh": median line height, "vocab": every word the document uses, casefolded}.
    """
    sizes: dict = {}
    heights: list = []
    for page in pages:
        counts = _line_sizes_and_heights(page)
        for size, n in counts["sizes"].items():
            sizes[size] = sizes.get(size, 0) + n
        heights.extend(counts["heights"])
    vocab = _vocabulary(pages)
    if not sizes:
        return {"body": 0.0, "heads": [], "lh": 12.0, "vocab": vocab}
    body = max(sizes, key=sizes.get)
    heads = sorted((s for s in sizes if s > body + 0.5), reverse=True)
    lh = statistics.median(heights) if heights else 12.0
    return {"body": body, "heads": heads, "lh": lh, "vocab": vocab}


def drop_keys(pages: list) -> set:
    if len(pages) < 4:
        return set()
    counts: Counter = Counter()
    for page in pages:
        flat = []
        for block in page:
            for ln in block:
                flat.append(ln)
        for ln in flat[:2] + flat[-2:]:
            k = hdr_key(ln["text"])
            if k:
                counts[k] += 1
    threshold = max(3, int(len(pages) * 0.3))
    return {k for k, c in counts.items() if c >= threshold}


def _is_heading(ln: dict, body: float, heading_sizes: list) -> bool:
    t = ln["text"].strip()
    if not t or len(t) > 160:
        return False
    if ln["size"] in heading_sizes:
        return True
    words = t.split()
    if len(words) > 14 or t.rstrip().endswith((".", ",", ";")):
        return False
    if ln["bold"] and (_SECTION_RE.match(t) or t.isupper()):
        return True
    return bool(_SECTION_RE.match(t))


def _level(ln: dict, heading_sizes: list) -> int:
    s = ln["size"]
    if s in heading_sizes:
        return min(heading_sizes.index(s) + 1, 4)
    return min(len(heading_sizes) + 1, 4) if heading_sizes else 2


def _keeps_hyphen(text: str, s: str, vocab: set) -> bool:
    """True when the book itself writes this broken word as a real compound."""
    tail = _HYPHEN_TAIL_RE.search(text)
    lead = _LEAD_WORD_RE.match(s.lstrip())
    if not tail or not lead:
        return False
    joined = (tail.group(1) + lead.group(1)).casefold()
    if joined in vocab:
        return False
    return f"{tail.group(1)}-{lead.group(1)}".casefold() in vocab


def _concat(text: str, s: str, vocab: set | None = None) -> str:
    if not text:
        return s
    if text.endswith("-") and len(text) > 1 and text[-2].isalpha():
        if vocab and _keeps_hyphen(text, s, vocab):
            return text + s.lstrip()
        return text[:-1] + s.lstrip()
    return text + " " + s.lstrip()


def _flush(lines: list, vocab: set, kind: str = "para") -> tuple:
    text = ""
    for ln in lines:
        s = ln["text"].strip()
        if s:
            text = _concat(text, s, vocab)
    if kind == "bullet":
        text = _BULLET_STRIP_RE.sub("", text, count=1)
    return (kind, 0, norm(text))  # lint-style: ignore DT001


def _block_geom(block: list, page_lh: float) -> tuple:
    xs0 = [ln["x0"] for ln in block]
    xs1 = [ln["x1"] for ln in block]
    heights = [ln["y1"] - ln["y0"] for ln in block]
    lh = statistics.median(heights) if heights else page_lh
    left, right = min(xs0), max(xs1)
    return left, right, max(right - left, 1.0), (lh or page_lh)  # lint-style: ignore DT001


def _breaks(prev: dict, cur: dict, geom: tuple) -> bool:
    left, right, width, lh = geom
    gap = cur["y0"] - prev["y1"]
    if gap > 0.6 * lh:
        return True
    if cur["x0"] > left + 0.4 * lh:
        return True
    prev_short = prev["x1"] < right - 0.20 * width
    cur_flush = cur["x0"] <= left + 0.05 * width
    return prev_short and cur_flush and gap >= -0.3 * lh


def _continues(a: str, b: str) -> bool:
    a, b = a.rstrip(), b.lstrip()
    if not a or not b:
        return False
    if a[-1] in _SENT_END:
        return False
    return b[0].islower() or b[0].isdigit() or b[0] in '("'


def _merge_continuations(elements: list) -> list:
    out: list = []
    for el in elements:
        if (el[0] == "para" and out and out[-1][0] == "para"
                and _continues(out[-1][2], el[2])):
            out[-1] = ("para", 0, norm(_concat(out[-1][2], el[2])))
        else:
            out.append(el)
    return out


def _item_starts(block: list) -> dict:
    """Line index to list kind for every line that opens a list item.

    A bullet always opens one. A number opens one only when the block holds at
    least two, so an ordinary sentence beginning "1. " is not mistaken for a list.
    """
    marks = {}
    for i, ln in enumerate(block):
        t = ln["text"].strip()
        if _BULLET_RE.match(t):
            marks[i] = "bullet"
        elif _NUMBER_RE.match(t):
            marks[i] = "number"
    numbered = [i for i, kind in marks.items() if kind == "number"]
    if len(numbered) < 2:
        for i in numbered:
            del marks[i]
    return marks


def _wraps_item(segments: list, prev: dict, ln: dict, lh: float) -> bool:
    """True when this line is the wrapped remainder of the list item above it."""
    if not segments or segments[-1]["kind"] not in _LIST_KINDS or prev is None:
        return False
    return ln["y0"] - prev["y1"] <= 0.6 * lh


def _place(segments: list, ln: dict, opens: bool) -> None:
    if opens or not segments or segments[-1]["kind"] != "para":
        segments.append({"kind": "para", "lines": [ln]})
    else:
        segments[-1]["lines"].append(ln)


def _segment_block(block: list, stats: dict, drop: set, tables: list) -> list:
    geom = _block_geom(block, stats["lh"])
    starts = _item_starts(block)
    segments: list = []
    prev = None
    for i, ln in enumerate(block):
        t = ln["text"].strip()
        key = hdr_key(t)
        if (key and key in drop) or _PAGE_NUM_RE.match(t):
            continue
        table = tables_mod.covering(ln, tables)
        if table:
            segments.append({"kind": "table", "text": table["markdown"]})
            prev = None
            continue
        if _is_heading(ln, stats["body"], stats["heads"]):
            segments.append({"kind": "heading", "level": _level(ln, stats["heads"]), "lines": [ln]})
            prev = None
            continue
        if i in starts:
            segments.append({"kind": starts[i], "lines": [ln]})
        elif _wraps_item(segments, prev, ln, geom[3]):
            segments[-1]["lines"].append(ln)
        else:
            _place(segments, ln, bool(prev and _breaks(prev, ln, geom)))
        prev = ln
    return _elements(segments, stats["vocab"])


def _elements(segments: list, vocab: set) -> list:
    out: list = []
    for seg in segments:
        if seg["kind"] == "table":
            out.append(("table", 0, seg["text"]))
        elif seg["kind"] == "heading":
            out.append(("heading", seg["level"], norm(seg["lines"][0]["text"])))
        else:
            out.append(_flush(seg["lines"], vocab, seg["kind"]))
    return out


def _page_elements(page: list, stats: dict, drop: set, tables: list) -> list:
    """Segment one page, emitting each table once however many blocks it straddles."""
    raw: list = []
    for block in page:
        raw.extend(_segment_block(block, stats, drop, tables))
    out: list = []
    seen: set = set()
    for element in raw:
        if element[0] != "table":
            out.append(element)
        elif element[2] not in seen:
            seen.add(element[2])
            out.append(element)
    return out


def segment(pages: list, stats: dict, drop: set, tables: list | None = None) -> list:
    """Turn extracted page lines into ordered heading, paragraph, list, and table elements.

    Args:
        stats: {"body", "heads", "lh", "vocab"} from doc_stats().
        tables: per-page table boxes from tables.doc_tables(), or None for no tables.
    """
    elements: list = []
    for index, page in enumerate(pages):
        page_tables = tables[index] if tables and index < len(tables) else []
        elements.extend(_page_elements(page, stats, drop, page_tables))
    return _merge_continuations(elements)


def render(elements: list) -> str:
    lines = []
    for kind, level, text in elements:
        if kind == "heading":
            lines.append("#" * level + " " + text)
        elif kind == "bullet":
            lines.append("- " + text)
        else:
            lines.append(text)
    return "\n\n".join(lines).strip() + "\n"


def strip_references(md: str) -> str:
    cut = None
    for m in _REF_HEADING.finditer(md):
        if m.start() >= len(md) * 0.5:
            cut = m.start()
    return md[:cut].rstrip() + "\n" if cut else md


# ---- OCR text (no geometry) ----

def _is_text_heading(line: str) -> bool:
    t = line.strip()
    if not t or len(t) > 120:
        return False
    words = t.split()
    if len(words) > 14 or t.rstrip().endswith((".", ",", ";")):
        return False
    return bool(_SECTION_RE.match(t)) or t.isupper()


def text_drop(pages: list) -> set:
    if len(pages) < 4:
        return set()
    counts: Counter = Counter()
    for p in pages:
        lines = [ln for ln in p.split("\n") if ln.strip()]
        for ln in lines[:2] + lines[-2:]:
            k = hdr_key(ln)
            if k:
                counts[k] += 1
    threshold = max(3, int(len(pages) * 0.3))
    return {k for k, c in counts.items() if c >= threshold}


def _flush_buf(elements: list, buf: list) -> None:
    if buf:
        elements.append(("para", 0, norm(" ".join(buf))))
        buf.clear()


def text_to_elements(pages: list) -> list:
    drop = text_drop(pages)
    elements: list = []
    buf: list = []
    for p in pages:
        for raw in p.split("\n"):
            line = raw.strip()
            if not line:
                _flush_buf(elements, buf)
                continue
            if _PAGE_NUM_RE.match(line) or hdr_key(line) in drop:
                continue
            if _is_text_heading(line):
                _flush_buf(elements, buf)
                elements.append(("heading", 2, line))
            else:
                buf.append(line)
        _flush_buf(elements, buf)
    return _merge_continuations(elements)
