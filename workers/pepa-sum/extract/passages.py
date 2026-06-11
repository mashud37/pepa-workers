"""TREC-style passage retrieval: surface the information-rich passages.

The paper is split into paragraph passages and scored with BM25 against a
salience query built from the document's own top noun phrases plus generic
academic cue phrases ("we argue", "our contribution", "results show"). The
highest-scoring passages — plus any explicitly labelled section (abstract,
methods, conclusion) — are returned in document order, focusing the model on
argument-bearing text rather than front-matter and references.
"""
import re

from rank_bm25 import BM25Okapi

# Cue phrases that mark the rhetorical moves a summary must capture.
_CUE_TERMS = (
    "argue contribution contributions propose hypothesis research question "
    "method methods approach data dataset sample analysis results findings "
    "conclude conclusion discussion implications limitations framework theory "
    "evidence demonstrate significant"
).split()

# Section headings worth keeping whole, regardless of BM25 rank.
_SECTION_RE = re.compile(
    r"^\s*(?:\d+\.?\s*)?(abstract|introduction|background|related work|"
    r"method|methods|methodology|materials and methods|results|findings|"
    r"discussion|conclusion|conclusions)\b",
    re.IGNORECASE,
)


def _tokenize(text):
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()


def _split_passages(text, min_chars=200, max_chars=1500):
    """Paragraph passages, merging runts and splitting overlong blocks."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    passages, buffer = [], ""
    for block in blocks:
        buffer = f"{buffer}\n\n{block}".strip() if buffer else block
        if len(buffer) >= min_chars:
            passages.append(buffer[:max_chars])
            buffer = ""
    if buffer:
        passages.append(buffer)
    return passages


def select_passages(text, signals, k=12):
    """Top-k information-rich passages in document order, sections kept whole.

    Returns a list of passage strings. Falls back to the head of the document
    for very short inputs where BM25 has nothing to rank."""
    passages = _split_passages(text)
    if len(passages) <= k:
        return passages

    query = _tokenize(" ".join(signals.get("noun_phrases", []))) + _CUE_TERMS
    tokenized = [_tokenize(p) for p in passages]
    scores = BM25Okapi(tokenized).get_scores(query)

    ranked = sorted(range(len(passages)), key=lambda i: scores[i], reverse=True)
    keep = set(ranked[:k])
    keep.update(i for i, p in enumerate(passages) if _SECTION_RE.match(p))
    return [passages[i] for i in sorted(keep)]
