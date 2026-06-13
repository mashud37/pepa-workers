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


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _tokenize(text):
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()


def _split_sentences(text):
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def salient_sentences(text, signals, k=12, min_words=8, max_words=60):
    """The k most information-rich whole sentences, verbatim, most-salient first.

    Each sentence is whitespace-normalised to a single line, screened for
    footnote/header/citation noise, then scored with BM25 against the paper's
    own key terms (noun phrases + entities) plus the academic cue phrases, so
    the picks carry the paper's concepts and arguments. Length bounds drop
    fragments and runaway sentences. Verbatim by construction."""
    candidates = []
    for s in _split_sentences(text):
        s = re.sub(r"(?<=[a-z])-\s*\n\s*(?=[a-z])", "", s)   # join line-broken words
        s = re.sub(r"\s+", " ", s).strip()                   # collapse wraps to one line
        if min_words <= len(s.split()) <= max_words and not _looks_noisy(s):
            candidates.append(s)
    if len(candidates) <= k:
        return candidates

    key_terms = signals.get("noun_phrases", []) + signals.get("entities", [])
    query = _tokenize(" ".join(key_terms)) + _CUE_TERMS
    scores = BM25Okapi([_tokenize(s) for s in candidates]).get_scores(query)
    ranked = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    return [candidates[i] for i in ranked[:k]]


def _looks_noisy(s):
    """Reject footnotes, interview logs, page headers, and citation dumps —
    the text pypdf interleaves into the body — as quote candidates."""
    if not s[:1].isalpha() or not s[0].isupper():
        return True
    if s[-1] not in ".!?\"'”’":
        return True
    if sum(c.isdigit() for c in s) / len(s) > 0.06:
        return True
    if re.search(r"\b\d{4}\.\d{1,3}\b", s):          # year.footnote, e.g. 2015.30
        return True
    if re.search(r"\bInterviews?\b", s):             # interview-log footnotes
        return True
    if len(re.findall(r"\b(?:19|20)\d\d\b", s)) >= 3:  # citation dump
        return True
    return False


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
