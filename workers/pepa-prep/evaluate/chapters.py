"""Score the chapter-boundary detector against hand-corrected gold files
under data/eval/chapters/. The detector reruns at scoring time, so pipeline
improvements rescore without relabelling.
"""
import re
import statistics
from pathlib import Path

from extract.categorise import import_fitz, route, scan_one
from extract.chapter import detect_chapters
from extract.text import doc_dims, doc_lines, doc_stats
from extract.workers import _text_flags

_ROOT = Path(__file__).parent.parent
_EVAL_DIR = _ROOT / "data" / "eval"
GOLD_DIR = _EVAL_DIR / "chapters"
SELECTION = GOLD_DIR / "selection.tsv"
REPORT = _EVAL_DIR / "chapters_report.md"

_SUFFIX = ".chapters.md"
TOLERANCE = 1

_LEGEND = (
    "# Chapter gold: one row per chapter start: <pdf-page><TAB><title>.\n"
    "# Pages are 1-based PDF pages (what a PDF viewer shows), not printed folios.\n"
    "# Fix wrong pages, delete spurious rows, add missing rows; titles are context only.\n"
    "# A ToC/outline-listed part divider is its own unit; an unlisted one (title-only\n"
    "# page before a chapter) opens the following chapter, one row at the divider page.\n"
)
_ROW_RE = re.compile(r"^\s*(\d{1,4})(?:[\t ]+(.*))?$")


def ensure_dirs() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)


def selection(input_folder: Path) -> list:
    out = []
    for raw in SELECTION.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(input_folder / line)
    return out


def predict_book(path: Path, cfg: dict) -> dict:
    """Run the production routing + chapter detector on one PDF.

    Args:
        path: Source PDF.
        cfg: Loaded config dict.

    Returns:
        {"name", "route", "bounds", "meta"}; bounds is [] unless route == "book".
    """
    fitz = import_fitz()
    scan = scan_one(path, fitz)
    if scan is None:
        raise ValueError("unreadable PDF")
    n, fraction = scan["pages"], scan["fraction"]
    r = route(n, fraction, cfg)
    if r != "book":
        return {"name": path.stem, "route": r, "bounds": [], "meta": {"strategy": "none"}}
    with fitz.open(str(path)) as doc:
        pages = doc_lines(doc, range(doc.page_count), _text_flags(fitz))
        dims = doc_dims(doc, range(doc.page_count))
        detected = detect_chapters(doc, pages, dims, doc_stats(pages), cfg)
        bounds, meta = detected["bounds"], detected["meta"]
    return {"name": path.stem, "route": r, "bounds": bounds, "meta": meta}


def write_gold(pred: dict) -> dict:
    """Write the correctable gold file; never overwrite existing corrections.

    Returns:
        {"path": written or existing file, "kept": True if an existing file was left alone}.
    """
    path = GOLD_DIR / f"{pred['name']}{_SUFFIX}"
    if path.exists():
        return {"path": path, "kept": True}
    rows = [f"{b['page'] + 1}\t{b['title']}" for b in pred["bounds"]]
    path.write_text(_LEGEND + "\n" + "\n".join(rows) + ("\n" if rows else ""),
                    encoding="utf-8")
    return {"path": path, "kept": False}


def parse_gold(text: str) -> list:
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _ROW_RE.match(line)
        if m:
            rows.append((int(m.group(1)) - 1, (m.group(2) or "").strip()))
    return sorted(rows)


def pending(input_folder: Path) -> list:
    return [(gp.name[: -len(_SUFFIX)], input_folder / f"{gp.name[: -len(_SUFFIX)]}.pdf", gp)
            for gp in sorted(GOLD_DIR.glob(f"*{_SUFFIX}"))]


def score(gold: list, pred: list, tol: int = TOLERANCE) -> dict:
    """Greedy one-to-one page matching within ±tol; exact = page-perfect share."""
    matched = []
    free = sorted(pred)
    for g in sorted(gold):
        best = min((p for p in free if abs(p - g) <= tol),
                   key=lambda p: abs(p - g), default=None)
        if best is not None:
            free.remove(best)
            matched.append((g, best))
    tp = len(matched)
    prec = tp / len(pred) if pred else 1.0
    rec = tp / len(gold) if gold else 1.0
    return {
        "n_gold": len(gold),
        "n_pred": len(pred),
        "precision": prec,
        "recall": rec,
        "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
        "exact": sum(g == p for g, p in matched) / tp if tp else 0.0,
        "over": len(pred) - tp,
        "under": len(gold) - tp,
    }


def grade_one(pdf_path: Path, gold_path: Path, cfg: dict) -> dict:
    """Score one book's detected chapters against its gold file.

    Returns:
        {"result": score dict or None, "note": explanation when result is None}.
    """
    if not pdf_path.exists():
        return {"result": None, "note": "source PDF not found"}
    gold = [pg for pg, _ in parse_gold(gold_path.read_text(encoding="utf-8"))]
    pred = predict_book(pdf_path, cfg)
    if pred["route"] != "book":
        note = f"route is {pred['route']}: chapter detection only runs on the book route"
        return {"result": None, "note": note}
    pages = [b["page"] for b in pred["bounds"]] or [0]
    res = score(gold, pages)
    res["strategy"] = pred["meta"]["strategy"]
    res["offset"] = pred["meta"].get("offset")
    res["verified"] = pred["meta"].get("verified")
    res["notes"] = pred["meta"].get("notes", [])
    return {"result": res, "note": ""}


def aggregate(scores: list) -> dict:
    return {
        "files": len(scores),
        "f1": statistics.mean(s["f1"] for s in scores) if scores else 0.0,
        "exact": statistics.mean(s["exact"] for s in scores) if scores else 0.0,
        "over": sum(s["over"] for s in scores),
        "under": sum(s["under"] for s in scores),
    }


def write_report(rows: list) -> None:
    agg = aggregate([r for _, r in rows])
    out = [
        "# Chapter detection report",
        "",
        "Compares detected chapter starts against your corrected reference pages.",
        "",
        f"Match score (0-100%, higher is better; matched within ±{TOLERANCE} page(s)):",
        f"{agg['files']} book(s) · average {agg['f1'] * 100:.1f}% · "
        f"exact-page {agg['exact'] * 100:.1f}% · "
        f"{agg['over']} spurious · {agg['under']} missed",
        "",
        "P/R/F1 = precision / recall / match score for that book.",
        "",
        "| book | strategy | gold | pred | P | R | F1 | exact | ver% | offset | diagnosis |",
        "|------|----------|-----:|-----:|--:|--:|---:|------:|-----:|-------:|-----------|",
    ]
    for name, r in rows:
        off = "" if r.get("offset") is None else str(r["offset"])
        ver = "" if r.get("verified") is None else f"{r['verified'] * 100:.0f}"
        notes = " · ".join(r.get("notes", []))
        out.append(
            f"| {name} | {r['strategy']} | {r['n_gold']} | {r['n_pred']} | "
            f"{r['precision'] * 100:.0f} | {r['recall'] * 100:.0f} | "
            f"{r['f1'] * 100:.1f} | {r['exact'] * 100:.0f} | {ver} | {off} | {notes} |"
        )
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
