"""Grade book chapter files, quarantine junk, renumber survivors, write report."""
import re
import shutil
import statistics
from collections import defaultdict
from pathlib import Path

from .chapter import _CHAPTER_HEADING_RE

_MIN_KEEP_CHARS = 250
_SHORT_ABS = 1200
_SHORT_REL = 0.12
_REF_REJECT = 0.55
_REF_MAX_SHARE = 0.25
_OVERSIZED_SHARE = 0.70
_OVERSIZED_ABS = 150_000

_REF_LINE_RE = re.compile(r"^\s*#*\s*\(?\d{1,3}[.)]\s+\S")
_CITATION_RE = re.compile(
    r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)|,\s*(?:19|20)\d{2}\b|\bpp?\.\s*\d|\bvol\.\s*\d",
    re.IGNORECASE,
)
_CHAPTER_FILE_RE = re.compile(r"^text_(.+)_(\d+)\.md$")


def book_groups(out_dir: Path) -> dict:
    groups: dict = defaultdict(list)
    for p in sorted(out_dir.glob("text_*_*.md")):
        m = _CHAPTER_FILE_RE.match(p.name)
        if m:
            groups[m.group(1)].append((int(m.group(2)), p))
    for stem in groups:
        groups[stem].sort()
    return dict(groups)


def _file_features(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    paras = [p for p in re.split(r"\n\s*\n", text)
             if p.strip() and not p.lstrip().startswith("#")]
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    refish = sum(1 for ln in body if _REF_LINE_RE.match(ln) or _CITATION_RE.search(ln))
    heads = [ln.strip() for ln in text.splitlines() if ln.lstrip().startswith("#")]
    return {
        "chars": len(text.strip()),
        "paras": len(paras),
        "ref_score": refish / len(body) if body else 0.0,
        "chapter_heads": sum(1 for ln in heads if _CHAPTER_HEADING_RE.match(ln)),
    }


def _typical_chapter_chars(feats: list) -> int:
    real = [f["chars"] for f in feats if f["chars"] >= _SHORT_ABS]
    return statistics.median(real) if real else max((f["chars"] for f in feats), default=0)


def _verdict(feat: dict, share: float, typical: float, lone: bool) -> str:
    if feat["chars"] < _MIN_KEEP_CHARS:
        return "reject:empty"
    if feat["ref_score"] >= _REF_REJECT and share < _REF_MAX_SHARE:
        return "reject:reference-block"
    if feat["chars"] < max(_SHORT_ABS, _SHORT_REL * typical) and feat["paras"] < 3:
        return "reject:too-short"
    if feat["chapter_heads"] >= 2:
        return "flag:multiple-chapters"
    if (lone and feat["chars"] >= _OVERSIZED_ABS) or (not lone and share >= _OVERSIZED_SHARE):
        return "flag:oversized"
    return "keep"


def grade_book(group: list) -> list:
    feats = [_file_features(p) for _, p in group]
    total = sum(f["chars"] for f in feats) or 1
    typical = _typical_chapter_chars(feats)
    lone = len(group) == 1
    rows = []
    for (idx, path), feat in zip(group, feats):
        share = feat["chars"] / total
        rows.append((idx, path, feat, share, _verdict(feat, share, typical, lone)))
    return rows


def apply_grades(out_dir: Path, stem: str, rows: list, dry: bool) -> None:
    review = out_dir / "_review"
    keepers = [path for _, path, _, _, v in rows if not v.startswith("reject")]
    rejects = [path for _, path, _, _, v in rows if v.startswith("reject")]
    if dry:
        return
    if rejects:
        review.mkdir(exist_ok=True)
        for path in rejects:
            shutil.move(str(path), str(review / path.name))
    temps = []
    for i, path in enumerate(keepers):
        t = out_dir / f"_tmp_{i}_{path.name}"
        shutil.move(str(path), str(t))
        temps.append(t)
    width = max(2, len(str(len(temps))))
    for i, t in enumerate(temps, 1):
        shutil.move(str(t), str(out_dir / f"text_{stem}_{i:0{width}d}.md"))


def write_report(out_dir: Path, graded: dict) -> None:
    lines = ["# Chapter validation report", ""]
    kept = sum(1 for rows in graded.values() for r in rows if not r[4].startswith("reject"))
    rejected = sum(1 for rows in graded.values() for r in rows if r[4].startswith("reject"))
    flagged = sum(1 for rows in graded.values() for r in rows if r[4].startswith("flag"))
    lines.append(
        f"{len(graded)} books · {kept} kept ({flagged} flagged) · "
        f"{rejected} quarantined into `_review/`"
    )
    lines.append("")
    for stem in sorted(graded):
        rows = graded[stem]
        lines.append(f"## {stem}")
        lines.append("")
        lines.append("| # | chars | paras | ref% | share | verdict |")
        lines.append("|--:|------:|------:|-----:|------:|---------|")
        for idx, _, feat, share, verdict in rows:
            lines.append(
                f"| {idx} | {feat['chars']:,} | {feat['paras']} | "
                f"{feat['ref_score'] * 100:.0f}% | {share * 100:.0f}% | {verdict} |"
            )
        lines.append("")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
