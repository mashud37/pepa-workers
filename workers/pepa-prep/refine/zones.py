"""Front/back-matter zoning: classify apparatus units by density features."""
import re

from . import signals

_MARKER_RE = re.compile(
    r"\bISBN\b|©|Copyright\s+(?:19|20)\d{2}|Library of Congress|CIP-Titelaufnahme",
    re.IGNORECASE,
)
_STOP_FLOOR = 0.18
_DIGIT_CEIL = 0.06
_SHORT_LINE = 45
_SHORT_SHARE = 0.70
_CAPS_SHARE = 0.30
_MIN_LINES = 20
_PROSE_LINE = 150
_PROSE_MAX = 5
_MARKER_SCAN = 60
_MIN_SIGNALS = 2


def _features(lines: list, fw: set) -> dict:
    body = [ln.strip() for ln in lines if ln.strip()]
    toks = []
    for ln in body:
        toks.extend(signals.tokens(ln))
    alnum = 0
    digits = 0
    for ln in body:
        for c in ln:
            alnum += c.isalnum()
            digits += c.isdigit()
    caps = sum(1 for ln in body
               if sum(c.isupper() for c in ln) >= 0.7 * max(1, sum(c.isalpha() for c in ln)))
    return {
        "lines": len(body),
        "stop_ratio": sum(t in fw for t in toks) / len(toks) if toks else 0.0,
        "digit_density": digits / alnum if alnum else 0.0,
        "short_share": sum(len(ln) < _SHORT_LINE for ln in body) / len(body) if body else 0.0,
        "caps_share": caps / len(body) if body else 0.0,
        "prose_lines": sum(len(ln) >= _PROSE_LINE for ln in body),
        "marker": any(_MARKER_RE.search(ln) for ln in body[:_MARKER_SCAN]),
    }


def is_apparatus(lines: list, fw: set) -> dict:
    """Judge a unit as apparatus (index, bibliography, title/copyright pages).

    Requires almost no prose paragraphs plus at least two density signals, so a
    preface or introduction never qualifies.

    Returns:
        {"apparatus": bool verdict, "reasons": the density signals that fired}.
    """
    f = _features(lines, fw)
    if f["lines"] < _MIN_LINES or f["prose_lines"] >= _PROSE_MAX:
        return {"apparatus": False, "reasons": []}
    reasons = []
    if f["stop_ratio"] < _STOP_FLOOR:
        reasons.append("low function-word share")
    if f["digit_density"] >= _DIGIT_CEIL:
        reasons.append("digit-dense")
    if f["short_share"] >= _SHORT_SHARE:
        reasons.append("list-like short lines")
    if f["caps_share"] >= _CAPS_SHARE:
        reasons.append("caps-heavy")
    if f["marker"]:
        reasons.append("ISBN/copyright markers")
    return {"apparatus": len(reasons) >= _MIN_SIGNALS, "reasons": reasons}
