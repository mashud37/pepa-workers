"""Re-cluster one thread of a saved map at finer granularity by rerunning the map pipeline over its works.
The console's theme pages offer it as Map this theme in detail.
"""
import json
import re

import numpy as np

import config
from cli import map as map_cmd
from cli import ui


def run(map_file=None, thread=None, only_estimate=False):
    sidecar = _resolve_map(map_file)
    if not sidecar:
        return
    threads = sidecar["threads"]
    source_name = sidecar.get("map_file", "")

    chosen = _choose_threads(threads, thread)
    if not chosen:
        return

    index = _index_by_base()
    records_by_base = index["by_base"]
    index_model = index["model"]
    if only_estimate:
        print(json.dumps(_estimate(chosen, records_by_base)))
        return
    total = len(chosen)
    mapped = 0
    for i, t in enumerate(chosen, 1):
        ui.info(f"[{i}/{total}] thread: {t['name']}")
        bases = list(dict.fromkeys(t["bases"] + t.get("also_bases", [])))
        gathered = _gather(bases, records_by_base)
        records = gathered["records"]
        vecs = gathered["vectors"]
        if len(records) < config.MAP_SMALLEST:
            ui.warn(f"only {len(records)} papers; a theme is mapped in detail from {config.MAP_SMALLEST}, skipping")
            continue
        mapped += 1
        slug = map_cmd.slug_of(t["name"])
        map_cmd.build_map(
            records, np.array(vecs, dtype=float),
            title=f"Thread map: {t['name']}",
            stem=f"thread_map_{slug}",
            index_model=index_model,
            min_threads=config.MAP_SUB_MIN_THREADS,
            max_threads=config.MAP_SUB_MAX_THREADS,
            source=source_name,
        )
    if mapped == 0:
        raise SystemExit(f"No theme here has the {config.MAP_SMALLEST} papers a detail map needs.")


def _estimate(chosen, records_by_base):
    """The cost of mapping each chosen thread in detail, added up."""
    band = {"min": config.MAP_SUB_MIN_THREADS, "max": config.MAP_SUB_MAX_THREADS}
    total = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "model": "", "dollars": 0.0, "papers": 0, "upto": True}
    for t in chosen:
        bases = list(dict.fromkeys(t["bases"] + t.get("also_bases", [])))
        records = _gather(bases, records_by_base)["records"]
        one = map_cmd.map_estimate(records, None, band)
        total["calls"] += one["calls"]
        total["input_tokens"] += one["input_tokens"]
        total["output_tokens"] += one["output_tokens"]
        total["papers"] += one["papers"]
        total["model"] = one["model"]
        if one["dollars"] is None or total["dollars"] is None:
            total["dollars"] = None
        else:
            total["dollars"] += one["dollars"]
    return total


# ---- Map and thread selection ----

def _resolve_map(map_file):
    """Return the sidecar dict for the chosen corpus map (loaded or reconstructed)."""
    if map_file:
        path = config.OUTPUT_DIR / map_file
    else:
        maps = sorted(config.OUTPUT_DIR.glob("corpus_map_*.md"), reverse=True)
        if not maps:
            raise SystemExit(f"No corpus map found. Run: {config.COMMAND} map")
        choice = ui.menu("Select a corpus map", [(m.name, "") for m in maps])
        if choice is None:
            return None
        path = maps[choice]

    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    sidecar = path.with_suffix(".json")
    if sidecar.exists():
        return json.loads(sidecar.read_text(encoding="utf-8"))
    ui.warn("no sidecar, matching works from the map text (may be approximate)")
    return _parse_md_fallback(path)


def _choose_threads(threads, thread):
    if thread is not None:
        if str(thread).lower() == "all":
            return threads
        if str(thread).isdigit():
            i = int(thread)
            return [threads[i - 1]] if 1 <= i <= len(threads) else []
        return [t for t in threads if thread.lower() in t["name"].lower()]

    options = [("All threads", f"{len(threads)} threads")]
    options += [(t["name"], f"{len(t['bases'])} works") for t in threads]
    choice = ui.menu("Select a thread to map in detail", options)
    if choice is None:
        return []
    return threads if choice == 0 else [threads[choice - 1]]


# ---- Index lookup ----

def _index_by_base():
    """Load the embedding index keyed by work base id.

    Returns:
        dict with keys "by_base" (dict of base id to (record, vector) pair)
        and "model" (the index's provider/model string).
    """
    from index.store import load_index
    idx = load_index()
    if idx is None:
        raise SystemExit(f"No index found. Run: {config.COMMAND} index")
    by_base = {r["base"]: (r, v) for r, v in zip(idx["records"], idx["vectors"])}
    return {"by_base": by_base, "model": idx.get("model", "")}


def _gather(bases, records_by_base):
    """Return the records and vectors for the given base ids that resolve.

    Returns:
        dict with keys "records" and "vectors", parallel lists.
    """
    records, vecs = [], []
    for b in bases:
        if b in records_by_base:
            r, v = records_by_base[b]
            records.append(r)
            vecs.append(v)
    return {"records": records, "vectors": vecs}


# ---- Fallback: reconstruct threads from the rendered .md ----

def _parse_md_fallback(md_path):
    idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
    by_line = {
        _norm(f"{r.get('authors', '')} - {r.get('title', '')}"): r["base"]
        for r in idx["records"]
    }
    text = md_path.read_text(encoding="utf-8")
    threads = []
    for block in re.split(r"\n## ", text)[1:]:
        header, *body = block.splitlines()
        name = re.sub(r"^\d+\.\s*", "", header).strip()
        if name.lower().startswith("cross-cutting"):
            continue
        matched = (re.match(r"-\s+(.*)", ln) for ln in body)
        bases = [by_line.get(_norm(m.group(1))) for m in matched if m]
        bases = [b for b in bases if b]
        threads.append({"name": name, "bases": bases, "also_bases": []})
    return {"map_file": md_path.name, "threads": threads}


def _norm(s):
    return re.sub(r"\s+", " ", s.replace("\u2014", "-")).strip().lower().rstrip(".")
