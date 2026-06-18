"""Rebuild the skeleton library from an already-completed Message Batch.

When a batch finishes but the run crashes before the library is saved (e.g. the
synthesis step fails), the paid-for labelling results are not lost: they live in
the batch's results JSONL, retrievable from the API for 29 days. This rebuilds the
move sequences from that file and runs synthesis again — no re-billing.

The batch's custom_ids are `p{idx}` over para_files() in sorted order, so the same
corpus reproduces the idx -> paper mapping exactly. Reconstructed sequences are
checkpointed to data/sequences.json before synthesis, so the recovered work is
banked even if synthesis needs another attempt.
"""
import json
import sys

import config
from cli import ui
from corpus.load import para_files
from corpus.parse_para import parse as parse_para
from skeleton import moves, build


def _load_results(path):
    raws = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            result = obj.get("result", {})
            if result.get("type") != "succeeded":
                continue
            msg = result["message"]
            raws[obj["custom_id"]] = "".join(
                b["text"] for b in msg["content"] if b.get("type") == "text"
            ).strip()
    return raws


def recover(jsonl_path):
    files = para_files()
    n = len(files)
    ui.info("Steps: 1/3 Load batch results · 2/3 Rebuild sequences · 3/3 Synthesise")

    ui.step("Loading batch results")
    raws = _load_results(jsonl_path)
    ui.info(f"loaded {len(raws)} succeeded result(s) from batch file")
    missing = [f"p{i}" for i in range(n) if f"p{i}" not in raws]
    if len(raws) != n:
        ui.warn(f"corpus has {n} papers but batch file has {len(raws)} results — "
                f"{len(missing)} unmatched; mapping requires an unchanged corpus")

    ui.step(f"Rebuilding move sequences for {n} paper(s)")
    sequences = []
    for idx, entry in enumerate(files):
        base = entry["base"]
        ui.info(f"[{idx + 1}/{n}] {base}")
        raw = raws.get(f"p{idx}")
        if raw is None:
            continue
        sentences = parse_para(entry["path"])
        if not sentences:
            continue
        sequences.append({"base": base, "moves": moves.parse(raw, len(sentences))})

    build._checkpoint_sequences(sequences)
    skeletons = build.synthesise(sequences)
    return {
        "n_papers": len(sequences),
        "recovered_from": str(jsonl_path),
        "skeletons": skeletons,
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        raise SystemExit("Usage: python -m skeleton.recover <batch_results.jsonl>")
    library = recover(argv[0])
    build.save(library)
    ui.info(f"saved {len(library['skeletons'])} skeleton(s) -> {config.SKELETONS_FILE}")


if __name__ == "__main__":
    main()
