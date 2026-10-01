"""Orchestrate the label, correct, and score workflow and write the
evaluation report. The CLI layer owns the loops and UI; streams and
corrections live under data/eval/.
"""
import statistics
from pathlib import Path

from . import lines, metrics, predict, review

_ROOT = Path(__file__).parent.parent
_EVAL_DIR = _ROOT / "data" / "eval"
STREAM_DIR = _EVAL_DIR / "streams"
REVIEW_DIR = _EVAL_DIR / "review"
REPORT = _EVAL_DIR / "report.md"
SELECTION = _EVAL_DIR / "selection.tsv"

_SUFFIX = ".tags.md"


def ensure_dirs() -> None:
    STREAM_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def parse_pages(spec: str) -> set | None:
    """Parse a 1-based page spec like '1-4,9' into a 0-based index set; '' or '*' = all."""
    spec = spec.strip()
    if not spec or spec in ("*", "all"):
        return None
    keep: set = set()
    for part in spec.split(","):
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            keep.update(range(lo - 1, hi))
        else:
            keep.add(int(part) - 1)
    return keep


def selection(input_folder: Path) -> list:
    """Read selection.tsv: 'filename<TAB>page-spec' rows → [(path, keep_set)]."""
    out = []
    for raw in SELECTION.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, spec = line.partition("\t")
        out.append((input_folder / name.strip(), parse_pages(spec)))
    return out


def build_stream(path: Path, cfg: dict, keep: set | None = None) -> dict:
    stream = lines.build(path, cfg, keep)
    lines.save(stream, STREAM_DIR / f"{stream['name']}.json")
    return stream


def write_review(stream: dict) -> dict:
    """Render the correctable tag file; never overwrite existing corrections.

    Returns:
        {"path": written or existing file, "kept": True if an existing file was left alone}.
    """
    path = REVIEW_DIR / f"{stream['name']}{_SUFFIX}"
    if path.exists():
        return {"path": path, "kept": True}
    texts = [rec["text"] for rec in stream["lines"]]
    path.write_text(review.render(texts, predict.predict(stream)), encoding="utf-8")
    return {"path": path, "kept": False}


def pending() -> list:
    out = []
    for rp in sorted(REVIEW_DIR.glob(f"*{_SUFFIX}")):
        name = rp.name[: -len(_SUFFIX)]
        sp = STREAM_DIR / f"{name}.json"
        if sp.exists():
            out.append((name, sp, rp))
    return out


def grade_one(stream_path: Path, review_path: Path) -> dict:
    """Score the gold tags against both the pre-merge baseline and the merged predictor.

    Returns:
        {"base": metrics dict or None, "merged": metrics dict or None, "note": message}.
    """
    stream = lines.load(stream_path)
    gold = review.parse(review_path.read_text(encoding="utf-8"))["labels"]
    base = predict.predict(stream, merge=False)
    if len(gold) != len(base):
        note = (f"line count mismatch (file {len(gold)} vs stream {len(base)}): "
                "lines were added/removed; re-create with label")
        return {"base": None, "merged": None, "note": note}
    merged = predict.predict(stream, merge=True)
    note = "tags identical to baseline (uncorrected, or already perfect)" if gold == base else ""
    return {"base": metrics.score(gold, base), "merged": metrics.score(gold, merged), "note": note}


def aggregate(scores: list) -> dict:
    return {
        "files": len(scores),
        "f1": statistics.mean(m["f1"] for m in scores) if scores else 0.0,
        "windowdiff": statistics.median(m["windowdiff"] for m in scores) if scores else 0.0,
        "pk": statistics.median(m["pk"] for m in scores) if scores else 0.0,
        "over_seg": sum(m["over_seg"] for m in scores),
        "under_seg": sum(m["under_seg"] for m in scores),
        "junk": sum(m["junk"] for m in scores),
    }


def write_report(rows: list) -> None:
    base = aggregate([b for _, b, _ in rows])
    mrg = aggregate([m for _, _, m in rows])
    out = [
        "# Segmentation evaluation report",
        "",
        "Compares detected line boundaries against your corrections.",
        "",
        "Match score (0-100%, higher is better):",
        f"{mrg['files']} file(s) · average {mrg['f1'] * 100:.1f}% with merge "
        f"({base['f1'] * 100:.1f}% pre-merge, {(mrg['f1'] - base['f1']) * 100:+.1f} points) · "
        f"median WindowDiff {mrg['windowdiff']:.3f} (lower is better) · "
        f"over-splits {base['over_seg']}→{mrg['over_seg']} · "
        f"{mrg['under_seg']} missed · {mrg['junk']} junk lines",
        "",
        "merge = the continuation merge applied in production (extract/text.py); "
        "pre-merge is the raw geometry/OCR baseline.",
        "",
        "| file | lines | junk | F1 base | F1 merge | Δ | over base | over merge | "
        "under | type% | WD | Pk |",
        "|------|------:|-----:|--------:|---------:|--:|----------:|-----------:|"
        "------:|------:|---:|---:|",
    ]
    for name, b, m in rows:
        out.append(
            f"| {name} | {m['lines']} | {m['junk']} | {b['f1'] * 100:.1f} | "
            f"{m['f1'] * 100:.1f} | {(m['f1'] - b['f1']) * 100:+.1f} | {b['over_seg']} | "
            f"{m['over_seg']} | {m['under_seg']} | {m['type_acc'] * 100:.0f} | "
            f"{m['windowdiff']:.3f} | {m['pk']:.3f} |"
        )
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
