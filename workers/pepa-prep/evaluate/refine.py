"""Unit-boundary evaluation for markdown refinement: gold rows vs the engine.

Gold files hold one row per true unit start, identified by the unit's first
line in the book's concatenated markdown. The engine re-runs at scoring time,
so refinement improvements re-score without relabelling.
"""
import statistics
from pathlib import Path

from evaluate.chapters import score
from refine import engine

_ROOT = Path(__file__).parent.parent
_EVAL_DIR = _ROOT / "data" / "eval"
GOLD_DIR = _EVAL_DIR / "refine"
SELECTION = GOLD_DIR / "selection.tsv"
REPORT = _EVAL_DIR / "refine_report.md"

_SUFFIX = ".units.md"
TOLERANCE = 3
_ROW_CHARS = 100
_MIN_KEY = 4

_LEGEND = (
    "# One row per chapter start: <occurrence><TAB><first line of the chapter>.\n"
    "#\n"
    "# The scorer searches the book's full text, including its table of contents,\n"
    "# for lines matching <first line>. A chapter's title often appears in two\n"
    "# places: once as a table-of-contents entry, and again as the heading where\n"
    "# the chapter actually starts. occurrence identifies which of those matches\n"
    "# is the true start: 1 = the first matching line found in the book (usually\n"
    "# the table-of-contents entry), 2 = the second (usually the real heading).\n"
    "#\n"
    "# Default to 1. Set it to 2 or higher only when the title you copied also\n"
    "# appears earlier in the book, so the first match is not the real start.\n"
    "#\n"
    "# To avoid the issue entirely, use a line from the chapter's opening\n"
    "# paragraph rather than its heading as <first line> — body text rarely\n"
    "# repeats, so occurrence stays 1.\n"
    "#\n"
    "# Correct wrong rows, delete rows that are not real chapter starts, and add\n"
    "# missing rows by copying a chapter's exact first line from the markdown.\n"
    "# Leading #'s and truncation to 100 characters are tolerated.\n"
)


def ensure_dirs() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)


def selection() -> list:
    out = []
    for raw in SELECTION.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _norm(text: str) -> str:
    return " ".join(text.replace("#", " ").split()).casefold()[:_ROW_CHARS - 10]


def _first_line(lines: list, start: int) -> str:
    return next((ln.strip() for ln in lines[start:] if ln.strip()), "")


def _occurrence(lines: list, start: int, text: str) -> int:
    key = _norm(text)
    return sum(1 for ln in lines[: start + 1] if _norm(ln) == key)


def prefill(book: dict) -> list:
    rows = []
    for start in book["starts"]:
        text = _first_line(book["lines"], start)[:_ROW_CHARS]
        rows.append((_occurrence(book["lines"], start, text), text))
    return rows


def write_gold(stem: str, rows: list) -> tuple[Path, bool]:
    """Write the correctable gold file; never overwrite existing corrections."""
    path = GOLD_DIR / f"{stem}{_SUFFIX}"
    if path.exists():
        return path, True
    body = "\n".join(f"{occ}\t{text}" for occ, text in rows)
    path.write_text(_LEGEND + "\n" + body + ("\n" if body else ""), encoding="utf-8")
    return path, False


def parse_gold(text: str) -> list:
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        occ, _, t = line.partition("\t")
        if t.strip() and occ.strip().isdigit():
            rows.append((int(occ), t.strip()))
    return rows


def locate(rows: list, lines: list) -> tuple[list, list]:
    """Resolve gold rows to global line indices; returns (bounds, misses)."""
    bounds, misses = [], []
    for occ, text in rows:
        key = _norm(text)
        if len(key) < _MIN_KEY:
            misses.append(text)
            continue
        hits = [i for i, ln in enumerate(lines) if _norm(ln) == key]
        if len(hits) >= occ:
            bounds.append(hits[occ - 1])
        else:
            misses.append(text)
    return sorted(bounds), misses


def pending() -> list:
    return [(gp.name[: -len(_SUFFIX)], gp) for gp in sorted(GOLD_DIR.glob(f"*{_SUFFIX}"))]


def grade_one(stem: str, group: list, gold_path: Path, cfg: dict) -> tuple:
    book = engine.load_book(stem, group)
    gold, misses = locate(parse_gold(gold_path.read_text(encoding="utf-8")), book["lines"])
    if not gold:
        return None, "no gold row could be located in the markdown"
    plan = engine.analyse(book, cfg)
    res = {
        "base": score(gold, book["starts"], tol=TOLERANCE),
        "refined": score(gold, plan["bounds"], tol=TOLERANCE),
        "plan": plan,
    }
    note = f"{len(misses)} gold row(s) not found" if misses else ""
    return res, note


def aggregate(scores: list) -> dict:
    return {
        "files": len(scores),
        "base_f1": statistics.mean(s["base"]["f1"] for s in scores) if scores else 0.0,
        "f1": statistics.mean(s["refined"]["f1"] for s in scores) if scores else 0.0,
    }


def write_report(rows: list) -> None:
    agg = aggregate([r for _, r in rows])
    out = [
        "# Markdown refinement report",
        "",
        "Compares your corrected chapter-start files (in data/eval/refine/) against "
        "what the refinement engine predicts, before and after its repairs.",
        "",
        f"Match score (0-100%, higher is better; a boundary counts as matched within "
        f"±{TOLERANCE} lines):",
        f"{agg['files']} book(s) · average {agg['base_f1'] * 100:.1f}% → "
        f"{agg['f1'] * 100:.1f}%",
        "",
        "| book | your chapters | before repair | after repair | match before | "
        "match after | repairs made | why |",
        "|------|-----:|-----:|--------:|--------:|-----------:|---------|-----------|",
    ]
    for name, r in rows:
        out.append(
            f"| {name} | {r['base']['n_gold']} | {r['base']['n_pred']} | "
            f"{r['refined']['n_pred']} | {r['base']['f1'] * 100:.1f}% | "
            f"{r['refined']['f1'] * 100:.1f}% | {engine.actions_summary(r['plan'])} | "
            f"{' · '.join(r['plan']['notes'])} |"
        )
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
