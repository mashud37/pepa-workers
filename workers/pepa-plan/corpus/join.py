"""Re-join paragraph summary text to the move labels already in sequences.json.

The labelling pass kept one move per paragraph and discarded the text, so the
within-section progression — how a run of ANALYSIS_FINDING paragraphs actually
unfolds — isn't recoverable from sequences.json alone. But every para_ file is
still on disk and its numbering aligns 1:1 with the stored labels, so we re-read
the text and pair it back without re-labelling. A 'section' is a maximal run of
one move.
"""
import config
from corpus.parse_para import parse as parse_para


def paired(base, move_list):
    """[(move, text), ...] for a base. zip stops at the shorter of the two, so a
    para_ file that drifted from its stored labels degrades safely rather than
    misaligning the tail."""
    path = config.corpus_dir() / f"para_{base}.md"
    if not path.exists():
        return []
    return list(zip(move_list, parse_para(path)))


def sections(pairs, move):
    """Maximal runs of `move`, each an ordered list of paragraph texts."""
    runs, current = [], []
    for m, text in pairs:
        if m == move:
            current.append(text)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs
