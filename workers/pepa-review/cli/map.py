"""WS4 — Corpus map: cluster all indexed works into thematic threads.

The clustering math lives in index/cluster.py (cs_ir_stats_reference §2, §3, §5);
this module orchestrates the stages with progress, asks Claude Sonnet to characterise
each thread (theme, discussion, key arguments, key concepts, methods, contexts), and
writes a single Markdown map to output/.
"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np

import config
from cli import ui, progress
from index import cluster
from backends import llm, prompt as prompts


def run(n_threads=None):
    ui.header("Corpus map")

    idx = _load_index()
    records = idx["records"]
    n = len(records)
    ui.info(f"corpus: {n} works")

    vecs = np.array(idx["vectors"], dtype=float)
    vecs_norm = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
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
        min_cs, k, sil = cluster.select_params(coords, n_threads)
        sp.done(f"k={k}  min_cs={min_cs}  silhouette={sil:.3f}")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    sp = progress.StepSpinner("consensus clustering")
    sp.start()
    try:
        labels, coassoc, strength = cluster.consensus_cluster(coords, k, min_cs)
        sp.done(f"{len(set(labels))} threads")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    primary, secondary, outliers = cluster.assign(coassoc, labels)

    sp = progress.StepSpinner("extracting terms (c-TF-IDF)")
    sp.start()
    primary, secondary, terms = cluster.merge_threads(primary, secondary, coords, texts)
    sp.done(f"{len(set(primary.values()))} threads after merge")

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

    outlier_recs = [records[i] for i in outliers]
    stats = {"silhouette": sil, "consensus": float(np.mean(list(strength.values())))}
    out = _write_map(sections, outlier_recs, n, stats)
    ui.ok(f"saved to {out.name}")
    ui.rule()
    for i, s in enumerate(sections, 1):
        extra = f" +{len(s['also'])} shared" if s["also"] else ""
        ui.info(f"  {i:2}. {s['name']}  ({len(s['records'])} works{extra})")
    if outlier_recs:
        ui.info(f"  --. Cross-cutting / outliers  ({len(outlier_recs)} works)")


# ── enrichment ───────────────────────────────────────────────────────────────

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


# ── LLM parse ────────────────────────────────────────────────────────────────

def _parse_response(response, records, also):
    import re

    def extract(label, stop_labels):
        alts = "|".join(r"\*\*" + re.escape(s) for s in stop_labels)
        lookahead = ("(?=" + alts + r"|\Z)") if alts else r"(?=\Z)"
        pattern = r"\*\*" + re.escape(label) + r":\*\*\s*(.+?)" + lookahead
        m = re.search(pattern, response, re.DOTALL)
        if not m:
            return ""
        return re.sub(r"\s*\*+\s*$", "", m.group(1).strip())   # drop a dangling ** from a truncated next label

    def extract_bullets(label, stop_labels):
        items = []
        for line in extract(label, stop_labels).splitlines():
            line = line.lstrip("-•· ").strip()
            if line:
                items.append(line)
        return items

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
        "discussion": extract("Discussion", stops_after_disc),
        "arguments":  extract_bullets("Key arguments", stops_after_args)[:7],
        "concepts":   extract_bullets("Key concepts", stops_after_conc)[:6],
        "methods":    extract("Methods", stops_after_meth),
        "empirical":  extract("Empirical contexts", []),
    }


# ── output ────────────────────────────────────────────────────────────────────

def _write_map(sections, outliers, total_works, stats):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = config.OUTPUT_DIR / f"corpus_map_{ts}.md"

    lines = [
        "# Corpus Map",
        "",
        f"_{total_works} works · {len(sections)} threads · generated {datetime.now().strftime('%Y-%m-%d')}_",
        "",
        f"_Method: UMAP → consensus clustering (HDBSCAN + k-means + Ward) → c-TF-IDF. "
        f"Silhouette {stats['silhouette']:.3f} · mean consensus {stats['consensus']:.2f}._",
        "",
        "---",
        "",
    ]

    for i, s in enumerate(sections, 1):
        lines += [f"## {i}. {s['name']}", ""]

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
        for r in sorted(s["records"], key=lambda x: x.get("authors", "")):
            lines.append(f"- {r.get('authors', '')} — {r.get('title', '')}")
        if s.get("also"):
            lines += ["", "**Also drawn on by this thread (shared with another):**"]
            for r in sorted(s["also"], key=lambda x: x.get("authors", "")):
                lines.append(f"- {r.get('authors', '')} — {r.get('title', '')}")
        lines += ["", "---", ""]

    if outliers:
        lines += [f"## Cross-cutting / outliers ({len(outliers)})", "",
                  "_Works that did not align strongly with any single thread._", ""]
        for r in sorted(outliers, key=lambda x: x.get("authors", "")):
            lines.append(f"- {r.get('authors', '')} — {r.get('title', '')}")
        lines += [""]

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def _load_index():
    if not config.INDEX_FILE.exists():
        raise SystemExit("No index found. Run: python manage.py index")
    idx = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
    if not idx.get("records"):
        raise SystemExit("Index is empty.")
    return idx
