"""Extract a stable per-line stream from a PDF, the shared unit for evaluation.

A stream is a deterministic, JSON-serialisable record of the document's content
lines (running headers, footers, and page numbers already removed, mirroring the
extractor) plus the geometry each predictor needs. Gold corrections and predictor
output are both aligned to this exact line order, so scoring needs no fuzzy matching.
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


def _text_flags(fitz) -> int:
    return fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES


def _keep(ln: dict, drop: set) -> bool:
    t = ln["text"].strip()
    key = hdr_key(t)
    return bool(t) and not (key and key in drop) and not _PAGE_NUM_RE.match(t)


def _block_records(block: list, pi: int, bid: int, lh: float, drop: set) -> list:
    geom = list(_block_geom(block, lh))
    return [{
        "text": ln["text"], "page": pi, "bid": bid, "blank_before": False,
        "geom": [ln[k] for k in _GEOM_KEYS], "block_geom": geom,
    } for ln in block if _keep(ln, drop)]


def _born_digital(doc, fitz, keep: set | None) -> tuple[dict, list]:
    pages = doc_lines(doc, range(doc.page_count), _text_flags(fitz))
    body, heads, lh = doc_stats(pages)
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
    return {"route": "geometry", "body": body, "heads": heads, "lh": lh}, out


def _ocr(path: Path, fitz, cfg: dict, keep: set | None) -> tuple[dict, list]:
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
                "text": t, "page": pi, "bid": pi, "blank_before": blank_before,
                "geom": None, "block_geom": None,
            })
            blank_before = False
    return {"route": "ocr"}, out


def build(path: Path, cfg: dict, keep: set | None = None) -> dict:
    """Build a line stream; keep, if given, limits output to those 0-based page indices.

    Header/footer detection and document statistics are always computed over the
    whole document, then output is filtered, so slicing never weakens header removal.
    """
    fitz = categorise.import_fitz()
    scan = categorise.scan_one(path, fitz)
    if scan is None:
        raise ValueError(f"unreadable PDF: {path.name}")
    pages, fraction = scan
    if categorise.route(pages, fraction, cfg) == "ocr":
        meta, body = _ocr(path, fitz, cfg, keep)
    else:
        with fitz.open(str(path)) as doc:
            meta, body = _born_digital(doc, fitz, keep)
    return {"name": path.stem, "route": meta["route"], "meta": meta, "lines": body}


def save(stream: dict, path: Path) -> None:
    path.write_text(json.dumps(stream, ensure_ascii=False), encoding="utf-8")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
