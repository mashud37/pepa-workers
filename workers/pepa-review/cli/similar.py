"""Find the indexed papers closest to a document, such as a draft or a paper not in the corpus.
The console's Find by document page reads each run's file.
"""
import json
from datetime import datetime
from pathlib import Path

import config
from cli import ui

PIECE_CHARS = 5000
MOST_PIECES = 40
SHOWN = 20
# A conservative count for an estimate: real English text runs closer to four characters a token.
CHARS_PER_TOKEN = 3
# List prices in US dollars per million input tokens; a provider missing here has no known price.
PRICE_PER_MILLION = {
    "gemini/gemini-embedding-001": 0.15,
}
LOCAL_PROVIDERS = [
    "ollama",
]


def pieces_of(text):
    """The document cut into pieces the size the index embeds, at most MOST_PIECES of them."""
    pieces = []
    for start in range(0, len(text), PIECE_CHARS):
        piece = text[start:start + PIECE_CHARS].strip()
        if piece:
            pieces.append(piece)
    return pieces[:MOST_PIECES]


def estimate(pieces):
    """How much embedding the pieces takes: tokens, and dollars at list price or None when unknown."""
    embed = config.embed_config()
    if not embed["provider"]:
        raise SystemExit(config.EMBED_MISSING)
    characters = sum(len(piece) for piece in pieces)
    tokens = -(-characters // CHARS_PER_TOKEN)
    model = f"{embed['provider']}/{embed['model']}"
    dollars = None
    if embed["provider"] in LOCAL_PROVIDERS:
        dollars = 0.0
    elif model in PRICE_PER_MILLION:
        dollars = tokens * PRICE_PER_MILLION[model] / 1_000_000
    return {"pieces": len(pieces), "tokens": tokens, "model": model, "dollars": dollars}


def closest(pieces):
    """The indexed papers closest to the pieces' average direction, closest first."""
    import numpy as np

    from index.embeddings import embed
    from index.store import checked_index
    index = checked_index()
    vectors = np.array(embed(pieces)["vectors"], dtype=float)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    centre = vectors.mean(axis=0)
    matrix = np.array(index["vectors"], dtype=float)
    scores = matrix @ centre / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(centre) + 1e-9)
    order = np.argsort(scores)[::-1][:SHOWN]
    found = []
    for position in order:
        record = index["records"][position]
        found.append({
            "base": record["base"],
            "authors": record["authors"],
            "title": record["title"],
            "score": round(float(scores[position]), 3),
        })
    return found


def save(path, cost, found):
    """Keep one run's papers in output/, since every run is paid for, and return the file written."""
    when = datetime.now()
    out = config.OUTPUT_DIR / f"similar_{path.stem}_{when.strftime('%Y%m%d_%H%M%S')}.json"
    record = {
        "input": path.name,
        "when": when.isoformat(timespec="seconds"),
        "pieces": cost["pieces"],
        "model": cost["model"],
        "results": found,
    }
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def run(input_file, only_estimate=False, as_json=False):
    path = Path(input_file)
    if not path.is_file():
        raise SystemExit(f"No file at {input_file}")
    pieces = pieces_of(path.read_text(encoding="utf-8", errors="replace"))
    if not pieces:
        raise SystemExit(f"{path.name} holds no text")
    cost = estimate(pieces)
    if only_estimate:
        print(json.dumps(cost))
        return
    if not as_json:
        ui.header("Papers closest to a document")
        ui.info(f"{path.name}: {cost['pieces']} piece(s), about {cost['tokens']:,} tokens with {cost['model']}")
    found = closest(pieces)
    saved = save(path, cost, found)
    if as_json:
        print(json.dumps({"results": found, "pieces": cost["pieces"], "saved": saved.name}))
        return
    ui.table(found, ["score", "authors", "title"])
    ui.ok(f"saved {saved}")
