"""Pick each skeleton's representative example papers deterministically
by nearest move distribution under the Hellinger geometry, avoiding an
LLM that would invent paper names.
"""
import math

from skeleton.moves import MOVES

INDEX = {m: i for i, m in enumerate(MOVES)}
N_EXAMPLES = 20


def _move_distribution(move_list):
    v = [0.0] * len(MOVES)
    for m in move_list:
        if m in INDEX:  # OTHER is absent from MOVES and so dropped
            v[INDEX[m]] += 1.0
    total = sum(v)
    return [x / total for x in v] if total else v


def _skeleton_distribution(skeleton):
    v = [0.0] * len(MOVES)
    for stage in skeleton.get("stages", []):
        m = stage.get("move")
        if m in INDEX:
            v[INDEX[m]] += float(stage.get("typical_share", 0) or 0)
    total = sum(v)
    return [x / total for x in v] if total else v


def for_skeleton(skeleton, dists, sequences, n=N_EXAMPLES):
    target = _skeleton_distribution(skeleton)
    ranked = sorted(
        range(len(sequences)),
        key=lambda i: math.sqrt(
            sum((math.sqrt(a) - math.sqrt(b)) ** 2 for a, b in zip(dists[i], target))
        ),
    )
    return [sequences[i]["base"] for i in ranked[:n]]


def attach(skeletons, sequences, n=N_EXAMPLES):
    """Overwrite each skeleton's example_bases with the n nearest real papers."""
    dists = [_move_distribution(s["moves"]) for s in sequences]
    for sk in skeletons:
        sk["example_bases"] = for_skeleton(sk, dists, sequences, n)
    return skeletons
