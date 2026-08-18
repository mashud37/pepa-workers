"""Reproduce the pipeline's pre-merge per-line decisions (heading detection,
block flushes, paragraph breaks) using the extractor's own primitives, so
pipeline changes rescore without relabelling.
"""
from extract.text import (
    _breaks,
    _concat,
    _continues,
    _is_heading,
    _is_text_heading,
    norm,
)

HEAD, PARA, CONT, LIST, DROP = "HEAD", "PARA", "CONT", "LIST", "DROP"
BOUNDARY = {HEAD, PARA, LIST}


def _geometry(stream: dict) -> list:
    body, heads = stream["meta"]["body"], stream["meta"]["heads"]
    labels: list = []
    prev = None
    prev_bid = None
    para_open = False
    for rec in stream["lines"]:
        if rec["bid"] != prev_bid:
            para_open, prev = False, None
        x0, y0, x1, y1, size, bold = rec["geom"]
        ld = {
            "text": rec["text"],
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "size": size,
            "bold": bold,
        }
        if _is_heading(ld, body, heads):
            labels.append(HEAD)
            para_open, prev, prev_bid = False, None, rec["bid"]
            continue
        broke = prev is not None and _breaks(prev, ld, tuple(rec["block_geom"]))
        labels.append(PARA if (not para_open or broke) else CONT)
        para_open, prev, prev_bid = True, ld, rec["bid"]
    return labels


def _ocr(stream: dict) -> list:
    labels: list = []
    para_open = False
    for rec in stream["lines"]:
        if _is_text_heading(rec["text"]):
            labels.append(HEAD)
            para_open = False
            continue
        labels.append(PARA if (not para_open or rec["blank_before"]) else CONT)
        para_open = True
    return labels


def _elements(labels: list, texts: list) -> list:
    """Rebuild para/heading elements, each tagged with the source line it starts at."""
    els: list = []
    for i, lab in enumerate(labels):
        if lab in (HEAD, PARA, LIST):
            els.append({"kind": "head" if lab == HEAD else "para",
                        "text": texts[i], "start": i})
        elif els:
            els[-1]["text"] = norm(_concat(els[-1]["text"], texts[i]))
    return els


def _demote_continuations(els: list) -> set:
    """Mirror extract.text._merge_continuations, recording collapsed boundary lines."""
    out: list = []
    demote: set = set()
    for el in els:
        if (el["kind"] == "para" and out and out[-1]["kind"] == "para"
                and _continues(out[-1]["text"], el["text"])):
            start = out[-1]["start"]
            out[-1] = {"kind": "para", "start": start, "text": norm(_concat(out[-1]["text"], el["text"]))}
            demote.add(el["start"])
        else:
            out.append(el)
    return demote


def predict(stream: dict, merge: bool = False) -> list:
    labels = _ocr(stream) if stream["route"] == "ocr" else _geometry(stream)
    if not merge:
        return labels
    texts = [rec["text"] for rec in stream["lines"]]
    demote = _demote_continuations(_elements(labels, texts))
    return [CONT if i in demote else lab for i, lab in enumerate(labels)]
