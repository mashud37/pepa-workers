"""Cluster every indexed work into thematic threads, ask Claude Sonnet to characterise
each thread, and write one Markdown corpus map to output/.
"""
import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np

import config
from backends import llm
from backends import prompt as prompts
from cli import progress, ui
from index import cluster


def run(n_threads=None):
    idx = _load_index()
    build_map(idx["records"], np.array(idx["vectors"], dtype=float), n_threads=n_threads,
              title="Corpus map", stem="corpus_map", index_model=idx.get("model", ""))


def build_map(records, vecs, n_threads=None, *, title="Corpus map", stem="corpus_map",
              index_model="", min_threads=None, max_threads=None, source=None):
    """Cluster `records` (parallel `vecs`) into threads, characterise each, write map + sidecar.

    Shared by the corpus map (all works) and the thread-level map (one thread's works).
    `min_threads`/`max_threads` override the granularity band; `stem` names the output
    file family; `source` records the parent map a thread-level run drilled into.
    """
    ui.header(title)

    n = len(records)
    ui.info(f"corpus: {n} works")

    vecs = np.asarray(vecs, dtype=float)
    vecs_norm = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)

    cl = _cluster_with_progress(records, vecs_norm, (n_threads, min_threads, max_threads))
    primary, secondary, outliers, terms, strength, sil = (
        cl["primary"], cl["secondary"], cl["outliers"], cl["terms"], cl["strength"], cl["sil"])

    thread_ids = sorted(set(primary.values()), key=lambda t: -sum(1 for v in primary.values() if v == t))
    ui.info(f"{len(thread_ids)} threads · {len(outliers)} cross-cutting · "
            f"{sum(1 for v in secondary.values() if v is not None)} multi-thread · "
            f"mean consensus {np.mean(list(strength.values())):.2f}")

    sp = progress.StepSpinner("loading methods/context fields")
    sp.start()
    try:
        enriched_map = _load_enriched(records)
        sp.done(f"{len(enriched_map)} records enriched")
    except Exception:
        sp.done("partial")
        enriched_map = {}

    clustering = {"primary": primary, "secondary": secondary, "terms": terms}
    sections = _build_sections(thread_ids, records, clustering, vecs_norm, enriched_map)

    outlier_recs = [records[i] for i in outliers]
    stats = {"silhouette": sil, "consensus": float(np.mean(list(strength.values())))}
    meta = {
        "ts": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "title": title,
        "stem": stem,
        "total_works": n,
        "stats": stats,
        "index_model": index_model,
        "source": source,
    }
    out = _write_map(sections, outlier_recs, meta)
    sidecar = _write_sidecar(sections, outlier_recs, meta)
    ui.ok(f"saved to {out.name}")
    ui.info(f"index sidecar: {sidecar.name}")
    ui.rule()
    for i, s in enumerate(sections, 1):
        extra = f" +{len(s['also'])} shared" if s["also"] else ""
        ui.info(f"  {i:2}. {s['name']}  ({len(s['records'])} works{extra})")
    if outlier_recs:
        ui.info(f"  --. Cross-cutting / outliers  ({len(outlier_recs)} works)")
    return out


# ---- Clustering stages (with liveness) ----

def _cluster_with_progress(records, vecs_norm, band):
    """Run the clustering pipeline stage by stage, each behind its own spinner.

    `band` is (n_threads, min_threads, max_threads) passed to select_params.
    Returns primary/secondary/outliers maps, c-TF-IDF terms, strength, and silhouette.
    """
    n_threads, min_threads, max_threads = band
    texts = [cluster.pool_text(r) for r in records]

    sp = progress.StepSpinner("building ensemble features")
    sp.start()
    try:
        features = cluster.ensemble_features(records, vecs_norm)
        sp.done(f"{features.shape[1]} dims")
    except Exception:
        sp.done("dense only")
        features = vecs_norm

    sp = progress.StepSpinner("reducing (UMAP)")
    sp.start()
    coords = cluster.reduce_dims(features)
    sp.done(f"{coords.shape[1]} dims")

    sp = progress.StepSpinner("selecting granularity")
    sp.start()
    try:
        params = cluster.select_params(coords, n_threads, min_threads, max_threads)
        k, min_cs, sil = params["k"], params["min_cs"], params["silhouette"]
        sp.done(f"k={k}  min_cs={min_cs}  silhouette={sil:.3f}")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    sp = progress.StepSpinner("consensus clustering")
    sp.start()
    try:
        consensus = cluster.consensus_cluster(coords, k, min_cs)
        sp.done(f"{len(set(consensus['labels']))} threads")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    assigned = cluster.assign(consensus["coassoc"], consensus["labels"])

    sp = progress.StepSpinner("extracting terms (c-TF-IDF)")
    sp.start()
    merged = cluster.merge_threads(assigned["primary"], assigned["secondary"], coords, texts)
    sp.done(f"{len(set(merged['primary'].values()))} threads after merge")

    return {
        "primary": merged["primary"],
        "secondary": merged["secondary"],
        "outliers": assigned["outliers"],
        "terms": merged["terms"],
        "strength": consensus["strength"],
        "sil": sil,
    }


# ---- Per-thread characterisation ----

def _build_sections(thread_ids, records, clustering, vecs_norm, enriched_map):
    """Ask the LLM to characterise each thread; return parsed section dicts."""
    primary, secondary, terms = clustering["primary"], clustering["secondary"], clustering["terms"]
    base_to_idx = {r["base"]: i for i, r in enumerate(records)}
    sections = []
    total = len(thread_ids)
    for ci, tid in enumerate(thread_ids):
        members = [records[i] for i, t in primary.items() if t == tid]
        also = [records[i] for i, s in secondary.items() if s == tid]
        sp = progress.StepSpinner(f"[{ci+1}/{total}] thread")
        sp.start()
        try:
            central = cluster.most_central(members, base_to_idx, vecs_norm)
            enriched = [dict(r, **enriched_map.get(r["base"], {})) for r in central]
            response = llm.complete(
                prompts.map_system(),
                prompts.map_thread_prompt(enriched, total_in_cluster=len(members),
                                          top_terms=terms.get(tid, [])),
                max_tokens=1400,
                quality=True,
            )
            section = _parse_response(response, members, also)
            sp.done(section["name"][:45])
            sections.append(section)
        except Exception as e:
            sp.done("error")
            raise SystemExit(str(e))
    return sections


# ---- Enrichment ----

def _load_enriched(records):
    """Load methods/empirical from sum_ files (not stored in index)."""
    from corpus.parse_sum import parse_sum
    out = {}
    for r in records:
        sp = r.get("sum_path")
        if sp and Path(sp).exists():
            try:
                p = parse_sum(sp)
                out[r["base"]] = {"methods": p.get("methods", ""), "empirical": p.get("empirical", "")}
            except Exception:
                pass
    return out


# ---- LLM parse ----

def _extract_field(response, label, stop_labels):
    alts = "|".join(r"\*\*" + re.escape(s) for s in stop_labels)
    lookahead = ("(?=" + alts + r"|\Z)") if alts else r"(?=\Z)"
    pattern = r"\*\*" + re.escape(label) + r":\*\*\s*(.+?)" + lookahead
    m = re.search(pattern, response, re.DOTALL)
    if not m:
        return ""
    return re.sub(r"\s*\*+\s*$", "", m.group(1).strip())


def _extract_bullets(response, label, stop_labels):
    items = []
    for line in _extract_field(response, label, stop_labels).splitlines():
        line = line.lstrip("-•· ").strip()
        if line:
            items.append(line)
    return items


def _parse_response(response, records, also):
    stops_after_disc = ["Key arguments", "Key concepts", "Methods", "Empirical contexts"]
    stops_after_args = ["Key concepts", "Methods", "Empirical contexts"]
    stops_after_conc = ["Methods", "Empirical contexts"]
    stops_after_meth = ["Empirical contexts"]

    name_m = re.search(r"\*\*Theme:\*\*\s*(.+)", response)
    name = name_m.group(1).strip() if name_m else "Unnamed thread"

    return {
        "name":       name,
        "records":    records,
        "also":       also,
        "discussion": _extract_field(response, "Discussion", stops_after_disc),
        "arguments":  _extract_bullets(response, "Key arguments", stops_after_args)[:7],
        "concepts":   _extract_bullets(response, "Key concepts", stops_after_conc)[:6],
        "methods":    _extract_field(response, "Methods", stops_after_meth),
        "empirical":  _extract_field(response, "Empirical contexts", []),
    }


# ---- Output ----

def _write_map(sections, outliers, meta):
    stats = meta["stats"]
    out = config.OUTPUT_DIR / f"{meta['stem']}_{meta['ts']}.md"

    lines = [
        f"# {meta['title']}",
        "",
        f"_{meta['total_works']} works · {len(sections)} threads · "
        f"generated {datetime.now().strftime('%Y-%m-%d')}_",
        "",
        f"_Method: UMAP → consensus clustering (HDBSCAN + k-means + Ward) → c-TF-IDF. "
        f"Silhouette {stats['silhouette']:.3f} · mean consensus {stats['consensus']:.2f}._",
        "",
        "---",
        "",
    ]
    for i, s in enumerate(sections, 1):
        lines += _render_section(i, s)

    if outliers:
        lines += [
            f"## Cross-cutting / outliers ({len(outliers)})",
            "",
            "_Works that did not align strongly with any single thread._",
            "",
        ]
        lines += [_work_line(r) for r in sorted(outliers, key=lambda x: x.get("authors", ""))]
        lines += [""]

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def _work_line(r):
    return f"- {r.get('authors', '')} - {r.get('title', '')}"


def _render_section(i, s):
    lines = [f"## {i}. {s['name']}", ""]
    if s.get("discussion"):
        lines += ["**Discussion:**", "", s["discussion"], ""]
    if s.get("arguments"):
        lines += ["**Key arguments:**"] + [f"- {a}" for a in s["arguments"]] + [""]
    if s.get("concepts"):
        lines += ["**Key concepts:**"] + [f"- {c}" for c in s["concepts"]] + [""]
    if s.get("methods"):
        lines += [f"**Methods:** {s['methods']}", ""]
    if s.get("empirical"):
        lines += [f"**Empirical contexts:** {s['empirical']}", ""]

    lines += [f"**Works ({len(s['records'])}):**"]
    lines += [_work_line(r) for r in sorted(s["records"], key=lambda x: x.get("authors", ""))]
    if s.get("also"):
        lines += ["", "**Also drawn on by this thread (shared with another):**"]
        lines += [_work_line(r) for r in sorted(s["also"], key=lambda x: x.get("authors", ""))]
    return lines + ["", "---", ""]


def _write_sidecar(sections, outliers, meta):
    """Machine-readable sibling of the .md map: thread -> index `base` ids.

    Lets the thread-level map (cli/thread_map.py) pull a thread's works back out of
    the index without fuzzy-matching the rendered 'authors - title' lines.
    """
    out = config.OUTPUT_DIR / f"{meta['stem']}_{meta['ts']}.json"
    payload = {
        "title":       meta["title"],
        "map_file":    f"{meta['stem']}_{meta['ts']}.md",
        "generated":   datetime.now().strftime("%Y-%m-%d"),
        "index_model": meta["index_model"],
        "total_works": meta["total_works"],
        "stats":       meta["stats"],
        "source":      meta["source"],
        "threads": [
            {
                "id":         i,
                "name":       s["name"],
                "bases":      [r["base"] for r in s["records"]],
                "also_bases": [r["base"] for r in s.get("also", [])],
            }
            for i, s in enumerate(sections, 1)
        ],
        "outliers": [r["base"] for r in outliers],
    }
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _load_index():
    from index.store import load_index
    idx = load_index()
    if idx is None:
        raise SystemExit(f"No index found. Run: {config.COMMAND} index")
    if not idx.get("records"):
        raise SystemExit("Index is empty.")
    return idx
