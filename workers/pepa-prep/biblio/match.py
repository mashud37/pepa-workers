"""Match pepa-sum file stems to Zotero CSL-JSON records.

Each stem is derived from the sum_*.md filename (strip the leading "sum_").
Matching is a token-overlap heuristic: words from the stem that appear in the
Zotero record's title or author fields score one point each. Tokens shorter
than 3 characters are ignored to avoid noise from stop words and initials.
A match is accepted when at least two tokens match.
"""
import json
from pathlib import Path


def load_zotero(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Zotero file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"Expected a CSL-JSON array in {path}")
    return data


def _score(stem: str, record: dict) -> int:
    clean = stem.replace("_", " ").replace("-", " ").lower()
    terms = [t for t in clean.split() if len(t) > 2]
    title = record.get("title", "").lower()
    authors = " ".join(a.get("family", "").lower() for a in record.get("author", []))
    return sum(1 for t in terms if t in title or t in authors)


def match_all(stems: list[str], records: list[dict]) -> dict[str, dict | None]:
    """Return {stem: zotero_record_or_None} for every stem."""
    result: dict = {}
    for stem in stems:
        best, best_score = None, 0
        for rec in records:
            s = _score(stem, rec)
            if s > best_score:
                best_score, best = s, rec
        result[stem] = best if best_score >= 2 else None
    return result
