"""Chapter splitting — verified outline, printed-ToC anchoring, or heading pattern."""
import re
import statistics
from pathlib import Path

from . import anchor, shape, toc
from .text import _is_heading, norm, render, strip_references

_CHAPTER_HEADING_RE = re.compile(
    r"^\s*#*\s*(?:chapter|kapitel|part|teil)\s+(?:\d{1,3}|[ivxlcdm]+|"
    + toc._NUM_WORDS + r")\b",
    re.IGNORECASE,
)
_MIN_CHAPTER_CHARS = shape._MIN_CHAPTER_CHARS
_MIN_ACCEPT = 0.50
_FULL_ACCEPT = 0.70
_DEFAULT_TOC_WORDS = ("contents", "table of contents", "inhalt", "inhaltsverzeichnis")


def _toc_words(cfg: dict) -> set:
    return {w.casefold() for w in cfg.get("toc_headings", _DEFAULT_TOC_WORDS)}


def outline_candidates(doc) -> dict:
    try:
        raw = doc.get_toc(simple=True)
    except Exception:
        raw = None
    levels: dict = {}
    for level, title, page in raw or []:
        if page >= 1:
            levels.setdefault(level, []).append({"title": norm(title), "page": page - 1})
    return levels


def _outline_results(doc, index: list, page_count: int, cfg: dict) -> list:
    results = []
    for level, cands in sorted(outline_candidates(doc).items()):
        if not 2 <= len(cands) <= 2 * cfg.get("max_chapters", 80):
            continue
        bounds, frac = anchor.verify(cands, index)
        ok, _ = shape.plausible(bounds, page_count, cfg)
        if ok:
            results.append((frac, "outline", bounds, None, level))
    return results


def _toc_results(doc, pages: list, entries: list, index: list, cfg: dict) -> list:
    chap = [e for e in entries if e["level"] <= 1]
    if len(chap) < 2:
        return []
    offsets = []
    for off in (toc.folio_offset(pages), toc.label_offset(doc, entries),
                anchor.derive_offset(chap, index)):
        if off is not None and off not in offsets:
            offsets.append(off)
    results = []
    for off in offsets or [None]:
        cands = [{"title": e["title"],
                  "page": e["no"] + off if off is not None and not e["roman"] else None}
                 for e in chap]
        bounds, frac = anchor.verify(cands, index)
        ok, _ = shape.plausible(bounds, len(pages), cfg)
        if ok:
            results.append((frac, "toc", bounds, off, 1))
    return results


def _rank(result: tuple, page_count: int) -> tuple:
    frac, _, bounds, _, level = result
    median_span = statistics.median(shape.spans(bounds, page_count))
    return frac >= _FULL_ACCEPT, 6 <= median_span <= 70, -level, frac


def detect_chapters(doc, pages: list, dims: list, stats: tuple,
                    cfg: dict) -> tuple[list, dict]:
    """Locate chapter boundaries as page indices; the strategy drives the output path.

    Args:
        doc: Open PyMuPDF document.
        pages: Per-page line blocks from doc_lines().
        dims: Per-page (width, height) from doc_dims().
        stats: (body, heads, lh) from doc_stats().
        cfg: Loaded config dict.

    Returns:
        (boundaries, meta): boundaries as [{"title", "page"}] with 0-based start
        pages, meta = {"strategy", "verified", "offset", "notes"} where strategy
        is "outline" | "toc" | "regex" | "none".
    """
    page_count = len(pages)
    index = anchor.heading_index(pages, dims, stats)
    widths = [d[0] for d in dims]
    toc_rng = toc.find_toc(pages, widths, _toc_words(cfg))
    entries = toc.parse_entries(pages, toc_rng, widths, _toc_words(cfg)) if toc_rng else []
    if toc_rng is not None:
        index = [c for c in index if c["page"] not in toc_rng]

    results = _outline_results(doc, index, page_count, cfg)
    results += _toc_results(doc, pages, entries, index, cfg)
    results.sort(key=lambda r: _rank(r, page_count), reverse=True)
    if results and results[0][0] >= _MIN_ACCEPT:
        frac, strategy, bounds, off, _ = results[0]
        drop_pages = set(toc_rng or ()) | toc.find_lists(pages, widths)
        bounds, notes = shape.repair(bounds, pages, drop_pages)
        if len(bounds) >= 2:
            notes += shape.diagnose(bounds, page_count)
            return bounds, {"strategy": strategy, "verified": frac,
                            "offset": off, "notes": notes}

    bounds = _regex_boundaries(pages, stats)
    if bounds:
        return bounds, {"strategy": "regex", "verified": None, "offset": None,
                        "notes": shape.diagnose(bounds, page_count)}
    return [], {"strategy": "none", "verified": None, "offset": None, "notes": []}


def _is_regex_boundary(ln: dict, stats: tuple) -> bool:
    t = norm(ln["text"])
    return (_is_heading(ln, stats[0], stats[1]) and len(t.split()) <= 8
            and bool(_CHAPTER_HEADING_RE.match(t)))


def _regex_boundaries(pages: list, stats: tuple) -> list:
    bounds: list = []
    chars = 0
    lines = ((pno, ln) for pno, page in enumerate(pages) for block in page for ln in block)
    for pno, ln in lines:
        if _is_regex_boundary(ln, stats):
            if not bounds or chars >= _MIN_CHAPTER_CHARS:
                bounds.append({"title": norm(ln["text"]), "page": pno})
                chars = 0
        else:
            chars += len(norm(ln["text"]))
    return bounds if len(bounds) >= 2 else []


def _is_chapter_heading(el: tuple) -> bool:
    if el[0] != "heading":
        return False
    t = el[2].strip()
    return len(t.split()) <= 8 and bool(_CHAPTER_HEADING_RE.match(t))


def _chapter_text_len(group: list) -> int:
    return sum(len(t) for k, _, t in group if k == "para")


def split_into_chapters(elements: list) -> list:
    if sum(1 for el in elements if _is_chapter_heading(el)) < 2:
        return [elements]
    chapters, current = [], []
    for el in elements:
        if (_is_chapter_heading(el) and current
                and _chapter_text_len(current) >= _MIN_CHAPTER_CHARS):
            chapters.append(current)
            current = [el]
        else:
            current.append(el)
    if current:
        chapters.append(current)
    return chapters


def write_chapters(stem: str, out_dir: Path, chapters: list) -> str:
    width = max(2, len(str(len(chapters))))
    for i, elements in enumerate(chapters, 1):
        md = strip_references(render(elements))
        (out_dir / f"text_{stem}_{i:0{width}d}.md").write_text(md, encoding="utf-8")
    return f"{len(chapters)} chapter file(s)"
