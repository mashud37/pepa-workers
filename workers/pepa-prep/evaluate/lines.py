"""Extract a stable per-line stream from a PDF: content lines plus geometry,
headers, footers, and page numbers removed. Gold corrections and predictor
output align to this exact line order.
"""
import json
from pathlib import Path

from extract import categorise
from extract.ocr import ocr_pages
from extract.text import (
    _PAGE_NUM_RE,
    _block_geom,
    doc_lines,
    doc_stats,
    drop_keys,
    hdr_key,
    text_drop,
)

_GEOM_KEYS = ("x0", "y0", "x1", "y1", "size", "bold")


def _keep(ln: dict, drop: set) -> bool:
    t = ln["text"].strip()
    key = hdr_key(t)
    return bool(t) and not (key and key in drop) and not _PAGE_NUM_RE.match(t)


def _block_records(block: list, pi: int, bid: int, lh: float, drop: set) -> list:
    geom = list(_block_geom(block, lh))
    return [{
        "text": ln["text"],
        "page": pi,
        "bid": bid,
        "blank_before": False,
        "geom": [ln[k] for k in _GEOM_KEYS],
        "block_geom": geom,
    } for ln in block if _keep(ln, drop)]


def _born_digital(doc, fitz, keep: set | None) -> dict:
    """Extract lines from a born-digital PDF using the production geometry pipeline.

    Returns:
        {"meta": {"route", "body", "heads", "lh"}, "lines": extracted line records}.
    """
    text_flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES
    pages = doc_lines(doc, range(doc.page_count), text_flags)
    stats = doc_stats(pages)
    body, heads, lh = stats["body"], stats["heads"], stats["lh"]
    drop = drop_keys(pages)
    out: list = []
    bid = 0
    for pi, page in enumerate(pages):
        if keep is not None and pi not in keep:
            continue
        for block in page:
            recs = _block_records(block, pi, bid, lh, drop)
            if recs:
                out.extend(recs)
                bid += 1
    return {"meta": {"route": "geometry", "body": body, "heads": heads, "lh": lh}, "lines": out}


def _ocr(path: Path, fitz, cfg: dict, keep: set | None) -> dict:
    """Extract lines from a scanned PDF's OCR text.

    Returns:
        {"meta": {"route": "ocr"}, "lines": extracted line records}.
    """
    pages = ocr_pages(path, fitz, cfg)
    drop = text_drop(pages)
    out: list = []
    for pi, page in enumerate(pages):
        if keep is not None and pi not in keep:
            continue
        blank_before = True  # a page break flushes the buffer, like text_to_elements
        for raw in page.split("\n"):
            t = raw.strip()
            if not t:
                blank_before = True
                continue
            if _PAGE_NUM_RE.match(t) or hdr_key(t) in drop:
                continue
            out.append({
                "text": t,
                "page": pi,
                "bid": pi,
                "blank_before": blank_before,
                "geom": None,
                "block_geom": None,
            })
            blank_before = False
    return {"meta": {"route": "ocr"}, "lines": out}


def build(path: Path, cfg: dict, keep: set | None = None) -> dict:
    """Build a line stream; keep, if given, limits output to those 0-based page indices.

    Header/footer detection and document statistics are always computed over the
    whole document, then output is filtered, so slicing never weakens header removal.
    """
    fitz = categorise.import_fitz()
    scan = categorise.scan_one(path, fitz)
    if scan is None:
        raise ValueError(f"unreadable PDF: {path.name}")
    pages, fraction = scan["pages"], scan["fraction"]
    if categorise.route(pages, fraction, cfg) == "ocr":
        extracted = _ocr(path, fitz, cfg, keep)
    else:
        with fitz.open(str(path)) as doc:
            extracted = _born_digital(doc, fitz, keep)
    meta, body = extracted["meta"], extracted["lines"]
    return {"name": path.stem, "route": meta["route"], "meta": meta, "lines": body}


def save(stream: dict, path: Path) -> None:
    path.write_text(json.dumps(stream, ensure_ascii=False), encoding="utf-8")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
