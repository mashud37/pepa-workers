import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import config
from cli import ui
from corpus.load import para_files
from corpus.parse_para import parse
from skeleton import moves
from backends import llm
from backends import prompt


def build(limit=None, sample=None):
    files = para_files()
    if not files:
        raise SystemExit(
            "No para_*.md files found in corpus.\n"
            "Run pepa-sum to generate paragraph rundowns first."
        )
    if sample and sample < len(files):
        files = random.sample(files, sample)
    if limit:
        files = files[:limit]

    parsed = [(entry["base"], parse(entry["path"])) for entry in files]
    parsed = [(base, sentences) for base, sentences in parsed if sentences]

    sequences = []
    n = len(parsed)
    done = 0
    with ThreadPoolExecutor(max_workers=config.concurrency()) as pool:
        futures = {
            pool.submit(moves.label, sentences): base for base, sentences in parsed
        }
        for future in as_completed(futures):
            base = futures[future]
            sequences.append({"base": base, "moves": future.result()})
            done += 1
            ui.info(f"[{done}/{n}] labelled {base}")

    ui.step("Synthesising skeleton library")
    raw = llm.complete(
        prompt.skeleton_system(),
        prompt.skeleton_prompt(sequences),
        max_tokens=4000,
        quality=True,
    )

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        skeletons = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"Could not parse skeleton JSON from model: {e}\n"
            "Try running python manage.py abstract again."
        )

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_papers": len(sequences),
        "skeletons": skeletons,
    }


def save(library):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.SKELETONS_FILE.write_text(
        json.dumps(library, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load():
    if not config.SKELETONS_FILE.exists():
        return None
    return json.loads(config.SKELETONS_FILE.read_text(encoding="utf-8"))
