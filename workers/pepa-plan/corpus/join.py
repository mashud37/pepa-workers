"""Rejoin paragraph summary text to the move labels in sequences.json by
re-reading each para_ file, since labelling kept only the move per
paragraph.
"""
import config
from corpus.parse_para import parse as parse_para


def paired(base, move_list):
    """[(move, text), ...] for a base. zip stops at the shorter of the two, so a
    para_ file that drifted from its stored labels degrades safely rather than
    misaligning the tail."""
    path = config.load()["corpus_dir"] / f"para_{base}.md"
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
