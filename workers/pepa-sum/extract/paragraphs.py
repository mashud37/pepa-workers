"""Paragraph segmentation and a deterministic one-sentence-per-paragraph rundown.

PDF text extraction gives messy line breaks, so paragraphs are recovered from
blank-line gaps, with runts merged and overlong blocks split on sentences. The
extractive rundown picks each paragraph's most central sentence (highest cosine
similarity to the rest) — verbatim, no model, the free alternative to the LLM
rundown. See cs_ir_stats_reference.md §1.7 (cosine) for the centrality idea.
"""
import re

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

# Heading that starts the body proper (everything before it is title, authors,
# affiliations, abstract, keywords).
_INTRO_RE = re.compile(r"(?im)^\s*(?:\d+\.?\s*|[ivx]+\.?\s*)?introduction\b")

# Headings that mark trailing matter after the conclusion (references are
# already removed upstream). The first one in the back half ends the body.
_BACKMATTER_RE = re.compile(
    r"(?im)^\s*(?:\d+\.?\s*)?("
    r"acknowledge?ments?|appendix|appendices|notes?|endnotes?|funding|"
    r"conflicts? of interest|competing interests?|author contributions?|"
    r"declarations?|disclosure statement|supplementary( material)?|"
    r"about the authors?|author biograph(y|ies)|biographical notes?|orcid"
    r")\b"
)


def body_span(text):
    """Trim a paper to its body: from the Introduction heading to just before
    any back-matter (acknowledgements, appendix, notes, author bios, ...).

    Used for the paragraph rundown so abstract/metadata at the front and
    trailing matter at the back don't become bullets. Both boundaries are
    optional — when a marker isn't found that edge is left untouched."""
    start = 0
    intro = _INTRO_RE.search(text)
    if intro and intro.start() <= len(text) * 0.4:
        start = intro.start()

    end = len(text)
    floor = max(start, int(len(text) * 0.5))
    for bm in _BACKMATTER_RE.finditer(text):
        if bm.start() >= floor:
            end = bm.start()
            break
    return text[start:end].strip()


def split_paragraphs(text, min_chars=200, max_chars=1500):
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    paragraphs, buffer = [], ""
    for block in blocks:
        buffer = f"{buffer} {block}".strip() if buffer else block
        if len(buffer) >= min_chars:
            paragraphs.extend(_split_long(buffer, max_chars))
            buffer = ""
    if buffer:
        paragraphs.extend(_split_long(buffer, max_chars))
    return paragraphs


def _split_long(para, max_chars):
    if len(para) <= max_chars:
        return [para]
    sentences = _sentences(para)
    chunks, buffer = [], ""
    for s in sentences:
        buffer = f"{buffer} {s}".strip() if buffer else s
        if len(buffer) >= max_chars:
            chunks.append(buffer)
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return chunks or [para]


def _sentences(para):
    return [s.strip() for s in _SENT_SPLIT.split(para) if s.strip()]


def extractive_rundown(paragraphs):
    return [_collapse(_central_sentence(p)) for p in paragraphs]


def _collapse(s):
    return re.sub(r"\s+", " ", s).strip()


def _central_sentence(para):
    sentences = _sentences(para)
    if len(sentences) <= 1:
        return para.strip()
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        X = TfidfVectorizer(stop_words="english").fit_transform(sentences)
    except ValueError:
        return sentences[0]
    centrality = (X @ X.T).sum(axis=1)
    return sentences[int(centrality.argmax())]
