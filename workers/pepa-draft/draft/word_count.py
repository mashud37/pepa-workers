"""Accurate word counting that handles quoted material correctly."""
import re

_PATTERN = re.compile(
    '[“”][^“”\n]{1,600}[“”]'
    '|'
    '[‘’][^‘’\n]{1,600}[‘’]'
    '|'
    '⟪[^⟫]{1,4000}⟫',
)


def guard(text: str) -> dict:
    """Replace quoted passages with placeholder tokens.

    Args:
        text: Input text that may contain quoted passages.

    Returns:
        Dict with keys masked_text (text with quotes replaced by tokens)
        and qmap (token to original quoted text).
    """
    qmap = {}
    pieces = []
    last_end = 0
    for match in _PATTERN.finditer(text):
        token = f"§Q{len(qmap)}§"
        qmap[token] = match.group(0)
        pieces.append(text[last_end:match.start()])
        pieces.append(token)
        last_end = match.end()
    pieces.append(text[last_end:])
    return {"masked_text": "".join(pieces), "qmap": qmap}


def unguard(text: str, qmap: dict) -> str:
    for token, original in qmap.items():
        text = text.replace(token, original)
    return text


def count(text: str) -> int:
    """Return word count, treating quoted passages as their natural word count."""
    guarded = guard(text)
    return len(unguard(text, guarded["qmap"]).split())


def trim_to_target(text: str, target: int) -> str:
    """Remove filler phrases to approach target word count.

    Args:
        text: Input text (multi-paragraph OK).
        target: Target word count.

    Returns:
        Trimmed text, possibly still over target if fillers are exhausted.
    """
    FILLERS = [
        (r"\bIt is (important|worth noting|clear) that\b,?\s*", ""),
        (r"\bAs (mentioned|noted|discussed) (above|previously|earlier)\b,?\s*", ""),
        (r"\bIn (terms|light) of\b", "regarding"),
        (r"\bdue to the fact that\b", "because"),
        (r"\bin order to\b", "to"),
        (r"\bat this point in time\b", "now"),
        (r"\bthe fact that\b", "that"),
        (r"\bvery (important|significant|relevant)\b", r"\1"),
        (r"\bquite (important|significant|relevant)\b", r"\1"),
        (r"\bbasically\b,?\s*", ""),
        (r"\bessentially\b,?\s*", ""),
        (r"\bfundamentally\b,?\s*", ""),
        (r"\boverall\b,?\s*", ""),
    ]
    current = count(text)
    if current <= target:
        return text
    for pattern, replacement in FILLERS:
        if count(text) <= target:
            break
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        text = re.sub(r"  +", " ", text).strip()
    return text
