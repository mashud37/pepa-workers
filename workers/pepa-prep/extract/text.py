"""Geometry-based paragraph reflow, heading detection, and markdown rendering."""
import re
import statistics
from collections import Counter

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


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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


def doc_stats(pages: list) -> dict:
    """One pass over every line: body size, heading sizes, and median line height.

    Returns:
        {"body": most common font size, "heads": larger sizes descending,
        "lh": median line height}.
    """
    sizes: dict = {}
    heights: list = []
    for page in pages:
        counts = _line_sizes_and_heights(page)
        for size, n in counts["sizes"].items():
            sizes[size] = sizes.get(size, 0) + n
        heights.extend(counts["heights"])
    if not sizes:
        return {"body": 0.0, "heads": [], "lh": 12.0}
    body = max(sizes, key=sizes.get)
    heads = sorted((s for s in sizes if s > body + 0.5), reverse=True)
    lh = statistics.median(heights) if heights else 12.0
    return {"body": body, "heads": heads, "lh": lh}


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


def _concat(text: str, s: str) -> str:
    if not text:
        return s
    if text.endswith("-") and len(text) > 1 and text[-2].isalpha():
        return text[:-1] + s.lstrip()
    return text + " " + s.lstrip()


def _flush(lines: list) -> tuple:
    text = ""
    for ln in lines:
        s = ln["text"].strip()
        if s:
            text = _concat(text, s)
    return ("para", 0, norm(text))  # lint-style: ignore DT001


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


def _segment_block(block: list, body: float, heading_sizes: list, drop: set, geom: tuple) -> list:
    elements: list = []
    para, prev = [], None
    for ln in block:
        t = ln["text"].strip()
        key = hdr_key(t)
        if (key and key in drop) or _PAGE_NUM_RE.match(t):
            continue
        if _is_heading(ln, body, heading_sizes):
            if para:
                elements.append(_flush(para))
                para = []
            elements.append(("heading", _level(ln, heading_sizes), norm(t)))
            prev = None
            continue
        if para and prev and _breaks(prev, ln, geom):
            elements.append(_flush(para))
            para = []
        para.append(ln)
        prev = ln
    if para:
        elements.append(_flush(para))
    return elements


def segment(pages: list, body: float, heading_sizes: list, drop: set, page_lh: float) -> list:
    elements: list = []
    for page in pages:
        for block in page:
            geom = _block_geom(block, page_lh)
            elements.extend(_segment_block(block, body, heading_sizes, drop, geom))
    return _merge_continuations(elements)


def render(elements: list) -> str:
    lines = []
    for kind, level, text in elements:
        lines.append("#" * level + " " + text if kind == "heading" else text)
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
