"""quote_<name>.md — the most information-rich sentences, verbatim.

Deterministic: the sentences are scored and selected by BM25 salience and
copied out exactly, so every quote is guaranteed to appear in the source. No
model call, no hallucination risk.
"""
from extract.passages import salient_sentences


def build(text, signals):
    sentences = salient_sentences(text, signals)
    if not sentences:
        return "_No salient sentences found._"
    return "\n".join(f'- "{s}"' for s in sentences)
