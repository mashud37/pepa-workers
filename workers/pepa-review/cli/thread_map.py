"""WS5 — Thread-level map: re-cluster the works of one thread at finer granularity.

Pick a saved corpus map, choose one thread (or all), and re-run the corpus-map
pipeline (cli/map.py) over just that thread's works. The works are recovered from
the map's JSON sidecar (thread -> index `base` ids); for older maps without a
sidecar we fall back to matching the rendered 'authors — title' lines to the index.
"""
import json
import re

import numpy as np

import config
from cli import ui, map as map_cmd


def run(map_file=None, thread=None):
    sidecar = _resolve_map(map_file)
    if not sidecar:
        return
    threads = sidecar["threads"]
    source_name = sidecar.get("map_file", "")

    chosen = _choose_threads(threads, thread)
    if not chosen:
        return

    records_by_base, index_model = _index_by_base()
    total = len(chosen)
    for i, t in enumerate(chosen, 1):
        ui.info(f"[{i}/{total}] thread: {t['name']}")
        bases = list(dict.fromkeys(t["bases"] + t.get("also_bases", [])))
        records, vecs = _gather(bases, records_by_base)
        if len(records) < config.MAP_SUB_MIN_THREADS + 1:
            ui.warn(f"only {len(records)} works resolved — too few to sub-cluster, skipping")
            continue
        map_cmd.build_map(
            records, np.array(vecs, dtype=float),
            title=f"Thread map — {t['name']}",
            stem=f"thread_map_{_slug(t['name'])}",
            index_model=index_model,
            min_threads=config.MAP_SUB_MIN_THREADS,
            max_threads=config.MAP_SUB_MAX_THREADS,
            source=source_name,
        )


# ── map / thread selection ────────────────────────────────────────────────────

def _resolve_map(map_file):
    """Return the sidecar dict for the chosen corpus map (loaded or reconstructed)."""
    if map_file:
        path = config.OUTPUT_DIR / map_file
    else:
        maps = sorted(config.OUTPUT_DIR.glob("corpus_map_*.md"), reverse=True)
        if not maps:
            raise SystemExit("No corpus map found. Run: python manage.py map")
        choice = ui.menu("Select a corpus map", [(m.name, "") for m in maps])
        if choice is None:
            return None
        path = maps[choice]

    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    sidecar = path.with_suffix(".json")
    if sidecar.exists():
        return json.loads(sidecar.read_text(encoding="utf-8"))
    ui.warn("no sidecar — matching works from the map text (may be approximate)")
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


# ── index lookup ──────────────────────────────────────────────────────────────

def _index_by_base():
    if not config.INDEX_FILE.exists():
        raise SystemExit("No index found. Run: python manage.py index")
    idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
    by_base = {r["base"]: (r, v) for r, v in zip(idx["records"], idx["vectors"])}
    return by_base, idx.get("model", "")


def _gather(bases, records_by_base):
    records, vecs = [], []
    for b in bases:
        if b in records_by_base:
            r, v = records_by_base[b]
            records.append(r)
            vecs.append(v)
    return records, vecs


# ── fallback: reconstruct threads from the rendered .md ───────────────────────

def _parse_md_fallback(md_path):
    by_line = _index_by_line()
    text = md_path.read_text(encoding="utf-8")
    threads = []
    for block in re.split(r"\n## ", text)[1:]:
        header, *body = block.splitlines()
        name = re.sub(r"^\d+\.\s*", "", header).strip()
        if name.lower().startswith("cross-cutting"):
            continue
        threads.append({"name": name, "bases": _bases_from_lines(body, by_line), "also_bases": []})
    return {"map_file": md_path.name, "threads": threads}


def _bases_from_lines(lines, by_line):
    matched = (re.match(r"-\s+(.*)", ln) for ln in lines)
    bases = (by_line.get(_norm(m.group(1))) for m in matched if m)
    return [b for b in bases if b]


def _index_by_line():
    idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
    return {_norm(f"{r.get('authors', '')} — {r.get('title', '')}"): r["base"]
            for r in idx["records"]}


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower().rstrip(".")


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "thread"
