"""Assemble a literature review from works chosen by map browsing, keyword search, or a
stem list, then draft or synthesise them into sections.
"""
import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from itertools import count
from pathlib import Path

import numpy as np

import config
from backends import llm
from backends import prompt as prompts
from cli import progress, ui
from corpus.metadata import display_label, work_list


def run(outline_file=None, auto=False, list_file=None):
    ui.header("Literature review")

    sp = progress.StepSpinner("scanning corpus")
    sp.start()
    works = work_list()
    sp.done(f"{len(works)} works")
    if not works:
        raise SystemExit("No papers found in corpus. Check CORPUS_DIR configuration.")

    outline_result = _get_outline(outline_file)
    outline = outline_result["text"]
    outline_stem = outline_result["stem"]
    if not outline:
        raise SystemExit("No outline provided.")
    ui.ok(f"outline: {len(outline)} chars")

    if list_file:
        selected = _list_select(works, list_file)
    else:
        selected = _select(outline, auto, works)
    if not selected:
        raise SystemExit("No works selected.")
    ui.ok(f"selected: {len(selected)} works")

    mode = "synthesise" if auto else _ask_mode()
    debates = _biblio_debates(selected) if config.use_biblio() else None
    sig = debates["sig"] if debates else None

    if mode == "follow":
        review_text = _draft_follow(outline, selected, _debate_block_global(debates))
    else:
        review_text = _draft_synthesise(outline, selected, debates)

    out_path = _write_review(review_text, selected, sig, outline_stem)
    ui.ok(f"saved to {out_path}")
    ui.rule()
    print(review_text)


# ---- Selection (map-driven, interactive) ----

def _select(outline, auto, works):
    from index.store import retrieve

    if not auto:
        menu = ui.menu("Work selection", [
            ("Map-guided",        "group relevant works into themes, refine by feedback"),
            ("Search by keyword", "filter by author surname or title keyword, then pick"),
            ("Import list",       "load stems exported from pepa-reader"),
        ])
        if menu == 1:
            return _keyword_select(works)
        if menu == 2:
            path = ui.ask("Path to literature list file")
            if not path:
                raise SystemExit("No list file given.")
            return _list_select(works, path)

    query = outline
    sp = progress.StepSpinner("retrieving candidates")
    sp.start()
    try:
        candidates = retrieve(query, k=config.REVIEW_CANDIDATE_K)
        sp.done(f"{len(candidates)} candidates")
    except SystemExit:
        sp.done("error")
        raise
    sp = progress.StepSpinner("grouping")
    sp.start()
    groups = _group_candidates(candidates)
    sp.done(f"{len(groups)} themes")

    if auto:
        return _dedupe(_flatten_groups(groups))

    while True:
        _show_groups(groups)
        fb = ui.ask("Refine selection (free text to steer, blank to accept)")
        if not fb:
            break
        query = f"{query}\n{fb}"
        sp = progress.StepSpinner("re-querying")
        sp.start()
        candidates = retrieve(query, k=config.REVIEW_CANDIDATE_K)
        sp.done(f"{len(candidates)} candidates")
        sp = progress.StepSpinner("grouping")
        sp.start()
        groups = _group_candidates(candidates)
        sp.done(f"{len(groups)} themes")

    return _dedupe(_flatten_groups(groups))


def _flatten_groups(groups):
    records = []
    for g in groups:
        for r in g["records"]:
            records.append(r)
    return records


def _group_candidates(candidates):
    """Group candidates into themes: reuse the latest corpus map, else cluster live."""
    groups = _groups_from_map(candidates)
    if groups:
        return groups
    return _groups_targeted(candidates)


def _groups_from_map(candidates):
    maps = sorted(config.OUTPUT_DIR.glob("corpus_map_*.md"))
    if not maps:
        return None
    threads = _parse_map_threads(maps[-1])
    if not threads:
        return None
    by_key = {_work_key(r["authors"], r["title"]): r for r in candidates}
    score = {r["base"]: r.get("score", 0.0) for r in candidates}

    groups = []
    claimed = set()
    for name, keys in threads:
        recs = [by_key[k] for k in keys if k in by_key and by_key[k]["base"] not in claimed]
        if recs:
            claimed.update(r["base"] for r in recs)
            groups.append({"name": name, "records": recs})
    if not groups:
        return None
    groups.sort(key=lambda g: -sum(score.get(r["base"], 0.0) for r in g["records"]))
    return groups


def _groups_targeted(candidates):
    if len(candidates) < 8:
        return [{"name": "Relevant works", "records": list(candidates)}]
    try:
        from index import cluster
        base_to_vec = _base_vectors()
        recs = [c for c in candidates if c["base"] in base_to_vec]
        vecs = [base_to_vec[c["base"]] for c in recs]
        res = cluster.cluster_records(recs, vecs)
        primary, terms = res["primary"], res["terms"]
        members = {}
        for i, t in primary.items():
            members.setdefault(t, []).append(recs[i])
        groups = [{"name": ", ".join(terms.get(t, [])[:3]) or "Theme", "records": m}
                  for t, m in members.items()]
        if groups:
            groups.sort(key=lambda g: -len(g["records"]))
            return groups
    except Exception:
        pass
    return [{"name": "Relevant works", "records": list(candidates)}]


def _show_groups(groups):
    ui.step("Proposed selection (themes):")
    for g in groups:
        ui.info(f"▸ {g['name']}  ({len(g['records'])})")
        for r in g["records"]:
            print(f"      - {display_label(r)}")


def _keyword_select(works):
    selected, selected_bases = [], set()
    while True:
        term = ui.ask("Search (author surname or title keyword, blank to finish)")
        if not term:
            break
        term_low = term.lower()
        matches = [w for w in works
                   if term_low in w["authors"].lower() or term_low in w["title"].lower()]
        if not matches:
            ui.warn(f"No works match '{term}'")
            continue
        print()
        for i, w in enumerate(matches, 1):
            mark = "✓" if w["base"] in selected_bases else " "
            print(f"  [{i}] {mark} {display_label(w)}")
        raw = ui.ask("Add numbers (comma-separated, blank to skip)")
        if not raw:
            continue
        _add_matches_by_number(raw, matches, selected, selected_bases)
    if not selected:
        ui.warn("No works selected: falling back to map-guided")
        from index.store import retrieve
        fallback_groups = _group_candidates(retrieve("academic research", k=15))
        return _dedupe(_flatten_groups(fallback_groups))
    return _attach_briefs(selected)


def _add_matches_by_number(raw, matches, selected, selected_bases):
    for part in raw.split(","):
        p = part.strip()
        if not p.isdigit():
            continue
        idx = int(p) - 1
        if not (0 <= idx < len(matches)):
            continue
        if matches[idx]["base"] in selected_bases:
            continue
        selected.append(matches[idx])
        selected_bases.add(matches[idx]["base"])
        ui.ok(f"Added: {matches[idx]['authors']}")


def _list_select(works, list_file):
    """Load a plain-text stem list (one `base` per line, as exported by pepa-reader)."""
    path = Path(list_file)
    if not path.exists():
        raise SystemExit(f"File not found: {list_file}")
    stems = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    stems = [s for s in stems if s and not s.startswith("#")]
    if not stems:
        raise SystemExit(f"No stems found in {list_file}")

    by_base = {w["base"]: w for w in works}
    selected = []
    for s in stems:
        w = by_base.get(s)
        if w is None:
            ui.warn(f"No work matches stem '{s}', skipping")
            continue
        selected.append(w)
    if not selected:
        raise SystemExit("None of the listed stems matched a work in the corpus.")
    ui.ok(f"matched {len(selected)}/{len(stems)} stems")
    return _attach_briefs(selected)


# ---- Structure mode ----

def _ask_mode():
    choice = ui.menu("Review structure", [
        ("Follow my outline",   "draft section-by-section along the outline's points"),
        ("Synthesise structure", "build 3–4 sections from key terms and tensions"),
    ])
    return "follow" if choice == 0 else "synthesise"


def _draft_follow(outline, selected, debate_block):
    briefs = _format_briefs(selected)
    if debate_block:
        briefs = debate_block + briefs
    sp = progress.StepSpinner("drafting review (following outline)")
    sp.start()
    try:
        text = llm.complete(prompts.review_system(),
                            prompts.review_prompt(outline, briefs),
                            max_tokens=6000, quality=True)
        sp.done("done")
        return text
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))


def _draft_synthesise(outline, selected, debates):
    ui.step("Synthesising review")
    ui.info("  · 1/2  Plan structure")
    ui.info("  · 2/2  Draft sections in parallel")

    terms = _candidate_terms(selected)
    sp = progress.StepSpinner("planning structure")
    sp.start()
    try:
        plan = llm.complete(
            prompts.review_plan_system(),
            prompts.review_plan_prompt(outline, _format_briefs(selected), terms,
                                       config.REVIEW_SECTIONS_MIN, config.REVIEW_SECTIONS_MAX),
            max_tokens=1500, quality=True)
        sp.done("planned")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    sections = _parse_plan(plan)
    if not sections:
        ui.warn("could not parse a structure: drafting in one pass")
        return _draft_follow(outline, selected, _debate_block_global(debates))

    for s in sections:
        s["records"] = _works_for_section(s, selected)

    total = len(sections)
    counter = count(1)

    sp = progress.StepSpinner(f"drafting [0/{total}]")
    sp.start()
    try:
        draft_one = partial(_draft_section_with_progress, debates=debates,
                            sp=sp, counter=counter, total=total)
        with ThreadPoolExecutor(max_workers=min(config.LLM_MAX_WORKERS, total)) as pool:
            drafts = list(pool.map(draft_one, sections))
        sp.done(f"{total} sections")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))
    return "\n\n".join(drafts)


def _draft_section_with_progress(section, debates, sp, counter, total):
    result = _draft_one_section(section, debates)
    done = next(counter)
    sp._label = f"drafting [{done}/{total}]"
    return result


def _draft_one_section(section, debates):
    return llm.complete(
        prompts.review_section_system(),
        prompts.review_section_prompt(section["title"], section.get("covers", ""),
                                      _format_briefs(section["records"]),
                                      _debate_block(section["records"], debates)),
        max_tokens=2200, quality=True)


def _parse_plan(text):
    sections = []
    for block in re.split(r"\*\*Section:\*\*", text)[1:]:
        first = block.strip().splitlines()[0] if block.strip() else ""
        title = first.strip().lstrip(":").strip().strip("*").strip()
        if not title:
            continue
        sections.append({"title": title,
                         "covers": _field(block, "Covers"),
                         "works": _field(block, "Works")})
    return sections


def _field(block, name):
    m = re.search(rf"{name}:\s*(.+)", block)
    return m.group(1).strip() if m else ""


def _works_for_section(section, selected):
    works_line = section.get("works", "").lower()
    matched = [r for r in selected
               if any(len(s) > 3 and s.lower() in works_line for s in r["authors"].split())]
    return matched if len(matched) >= 2 else list(selected)


# ---- Biblio anchoring ----

def _biblio_debates(selected):
    from biblio import store
    sig = store.work_signals()
    rows = [(r, sig[r["base"]]) for r in selected
            if r["base"] in sig and sig[r["base"]].get("year")]
    if len(rows) < 4:
        return {"sig": sig, "anchor_recs": [], "pairs": {}}

    cites = [s["cited_by_count"] for _, s in rows]
    years = [s["year"] for _, s in rows]
    cite_thresh = _pctl(cites, config.BIBLIO_ANCHOR_CITE_PCTL)
    year_split = _pctl(years, 0.5)

    anchors = [r for r, s in rows if s["cited_by_count"] >= cite_thresh and s["year"] <= year_split]
    newer = [r for r, s in rows if s["year"] > year_split]
    base_to_vec = _base_vectors()

    pairs = {}
    for a in anchors:
        av = base_to_vec.get(a["base"])
        if av is None or not newer:
            continue
        ranked = sorted(newer, key=lambda r: -_cos(av, base_to_vec.get(r["base"])))
        pairs[a["base"]] = ranked[:config.BIBLIO_INTERLOCUTOR_TOPN]
    return {"sig": sig, "anchor_recs": anchors, "pairs": pairs}


def _debate_block(section_records, debates):
    if not debates or not debates["anchor_recs"]:
        return ""
    bases = {r["base"] for r in section_records}
    lines = _debate_lines(debates, only=bases)
    return _wrap_debate(lines)


def _debate_block_global(debates):
    if not debates or not debates["anchor_recs"]:
        return ""
    return _wrap_debate(_debate_lines(debates, only=None))


def _debate_lines(debates, only):
    lines = []
    for a in debates["anchor_recs"]:
        if only is not None and a["base"] not in only:
            continue
        inter = debates["pairs"].get(a["base"], [])
        if not inter:
            continue
        names = "; ".join(r["authors"] for r in inter)
        lines.append(f"- {a['authors']} (foundational, highly cited) ↔ {names} (more recent): "
                     f"stage how the recent work extends or contests it.")
    return lines


def _wrap_debate(lines):
    if not lines:
        return ""
    return "CITATION SIGNALS: work these debates into the writing:\n" + "\n".join(lines) + "\n\n"


def _pctl(values, p):
    return float(np.percentile(np.array(values, dtype=float), p * 100))


def _cos(a, b):
    if a is None or b is None:
        return -1.0
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


# ---- Briefs and terms ----

def _candidate_terms(selected):
    try:
        from index import cluster
        texts = [cluster.pool_text(r) for r in selected]
        return cluster.ctfidf({0: list(range(len(texts)))}, texts, top_n=12).get(0, [])
    except Exception:
        return []


def _format_briefs(hits):
    parts = []
    for h in hits:
        parts.append(
            f"### {h.get('authors', '')}: {h.get('title', '')}\n"
            f"**Question:** {h.get('question', '')}\n\n"
            f"**Arguments:** {h.get('arguments_text', '')}\n\n"
            f"**Conclusions:** {h.get('conclusions', '')}\n\n"
            f"**Literature drawn on:** {h.get('literature', '')}"
        )
    return "\n\n---\n\n".join(parts)


# ---- Outline input ----

def _get_outline(outline_file):
    """Read the outline text to draft the review from.

    Returns:
        dict with keys "text" (the outline text, or None if the user
        cancelled) and "stem" (a filename stem to base the output on).
    """
    if outline_file:
        p = Path(outline_file)
        if not p.exists():
            raise SystemExit(f"File not found: {outline_file}")
        return {"text": p.read_text(encoding="utf-8").strip(), "stem": p.stem}

    input_files = sorted(config.INPUT_DIR.glob("*.md")) + sorted(config.INPUT_DIR.glob("*.txt"))
    options = [("Open in editor", "write outline in $EDITOR / notepad")]
    options += [(f.name, str(f)) for f in input_files]

    choice = ui.menu("Outline source", options)
    if choice is None:
        return {"text": None, "stem": "draft"}
    if choice == 0:
        return {"text": _editor_input(), "stem": "draft"}
    f = input_files[choice - 1]
    return {"text": f.read_text(encoding="utf-8").strip(), "stem": f.stem}


def _editor_input():
    placeholder = "# Outline\n\nEnter your outline and arguments here.\n"
    editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "nano")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                     encoding="utf-8") as f:
        f.write(placeholder)
        tmp = f.name
    ui.info("Save and close the editor window to continue…")
    subprocess.call(_editor_cmd(editor, tmp))
    text = Path(tmp).read_text(encoding="utf-8").strip()
    Path(tmp).unlink(missing_ok=True)
    return text if text != placeholder.strip() else ""


def _editor_cmd(editor, path):
    base = os.path.basename(editor).lower().replace(".cmd", "").replace(".exe", "")
    if base == "code":
        return [editor, "--wait", path]
    return [editor, path]


# ---- Index helpers ----

_INDEX_CACHE = None


def _load_index():
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        if not config.INDEX_FILE.exists():
            raise SystemExit(f"No index found. Run: {config.COMMAND} index")
        _INDEX_CACHE = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
    return _INDEX_CACHE


def _base_vectors():
    idx = _load_index()
    return {r["base"]: v for r, v in zip(idx["records"], idx["vectors"])}


def _attach_briefs(selected):
    by_base = {r["base"]: r for r in _load_index()["records"]}
    return [dict(by_base.get(w["base"], {}), **w) for w in selected]


def _dedupe(records):
    seen, out = set(), []
    for r in records:
        if r["base"] not in seen:
            seen.add(r["base"])
            out.append(r)
    return out


def _work_key(authors, title):
    return f"{(authors or '').strip().lower()} - {(title or '').strip().lower()}"


def _parse_map_threads(path):
    """Parse (thread_name, [work_key,...]) tuples from a corpus_map_*.md file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    threads = []
    cur_name, cur_keys, in_works = None, [], False
    for line in text.splitlines():
        h = re.match(r"^##\s+\d+\.\s+(.*)", line)
        if h:
            if cur_name:
                threads.append((cur_name, cur_keys))
            cur_name, cur_keys, in_works = h.group(1).strip(), [], False
            continue
        if line.startswith("## "):     # outliers / non-numbered section ends threads
            if cur_name:
                threads.append((cur_name, cur_keys))
            cur_name, cur_keys, in_works = None, [], False
            continue
        if cur_name and line.startswith("**Works"):
            in_works = True
            continue
        if cur_name and line.startswith("**"):
            in_works = False
        if cur_name and in_works:
            m = re.match(r"^-\s+(.*?)\s+[-\u2014]\s+(.*)$", line)
            if m:
                cur_keys.append(_work_key(m.group(1), m.group(2)))
    if cur_name:
        threads.append((cur_name, cur_keys))
    return [(n, k) for n, k in threads if k]


# ---- Output ----

def _write_review(text, selected, sig=None, outline_stem="review"):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = config.OUTPUT_DIR / f"review_{outline_stem}_{ts}.md"
    rows = []
    for w in selected:
        line = f"- {w['authors']} - {w['title']}"
        if sig and w["base"] in sig and sig[w["base"]].get("year"):
            s = sig[w["base"]]
            line += f" ({s['year']} · {s['cited_by_count']} cites)"
        rows.append(line)
    footer = "\n\n---\n\n## Works drawn on\n\n" + "\n".join(rows) + "\n"
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(text + footer, encoding="utf-8")
    return out
