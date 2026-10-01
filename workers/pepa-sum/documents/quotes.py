"""Select the most information-rich sentences by BM25 salience and copy them
out verbatim into quote_<name>.md, with no model call and no hallucination
risk.
"""
from extract.passages import salient_sentences


def build(text, signals):
    sentences = salient_sentences(text, signals)
    if not sentences:
        return "_No salient sentences found._"
    return "\n".join(f'- "{s}"' for s in sentences)
