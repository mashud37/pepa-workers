"""Check a draft section by section for papers, arguments and terms it misses from the corpus.
The console's Draft page shows each report beside the papers it names.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import config
from backends import llm
from backends import prompt as prompts
from cli import costs, items, progress, similar, ui
from corpus.metadata import list_bases

_MIN_PARA_CHARS = 40        # paragraphs shorter than this are treated as headings/noise
SECTION_NAME_CHARS = 48
_FALLBACK_GROUP = 4         # paragraphs per section when a draft has no headings
_PER_SECTION = 8            # candidate works carried into each section's prompt
_SECTION_CHARS = 3000       # the most of a section's text one call sends
_BRIEF_CHARS = 400          # the most of one candidate's brief one call sends
_SUGGEST_TOKENS = 1200


def gaps_estimate(draft_text):
    """The most a gap check can cost: one call per section, plus embedding every paragraph."""
    sections = _split_sections(draft_text)
    calls = []
    for section in sections:
        input_chars = min(len(section["text"]), _SECTION_CHARS) + _PER_SECTION * _BRIEF_CHARS
        calls.append({"input_chars": input_chars, "output_tokens": _SUGGEST_TOKENS})
    result = costs.estimate(calls, quality=False)
    paragraphs = []
    for section in sections:
        for paragraph in section["paragraphs"]:
            if len(paragraph) >= _MIN_PARA_CHARS:
                paragraphs.append(paragraph)
    embedding = similar.estimate(paragraphs)
    if result["dollars"] is not None and embedding["dollars"] is not None:
        result["dollars"] += embedding["dollars"]
    result["sections"] = len(sections)
    result["upto"] = True
    return result


def run(options):
    """Check a draft for gaps against the corpus or one list's papers, and write the report to output/.

    Args:
        options: "input_file", "list_file", "only_estimate" and "output_name", as manage.py parses them.
    """
    draft_path = _get_draft(options["input_file"])
    if not draft_path:
        return
    draft_text = Path(draft_path).read_text(encoding="utf-8", errors="replace")
    if options["only_estimate"]:
        print(json.dumps(gaps_estimate(draft_text)))
        return
    ui.header("Gap-check a draft")
    ui.ok(f"draft: {Path(draft_path).name} ({len(draft_text)} chars)")

    sp = progress.StepSpinner("scanning corpus")
    sp.start()
    from corpus.metadata import work_list
    all_works = work_list()
    sp.done(f"{len(all_works)} works")
    cited_bases = _detect_cited(draft_text, all_works)
    ui.info(f"already cited: ~{len(cited_bases)} works detected in text")
    wanted = None
    if options["list_file"]:
        wanted = set(list_bases(options["list_file"]))
        ui.info(f"checking against the {len(wanted)} papers in {Path(options['list_file']).stem}")

    sections = _split_sections(draft_text)
    ui.info(f"{len(sections)} sections to check")

    _map_sections_to_candidates(sections, cited_bases, wanted)

    active = [s for s in sections if s["candidates"]]
    if active:
        _synthesise_all(active)
    else:
        ui.ok("No gaps found: the draft engages well with the corpus.")

    out = _write_gaps(sections, Path(draft_path).name, options["output_name"])
    ui.ok(f"gap report saved to {out}")
    print(out)
    ui.rule()
    for i, s in enumerate(sections, 1):
        label = s["heading"] or f"Section {i}"
        n = len(s.get("suggestions", {}).get("works", [])) if s["candidates"] else 0
        ui.info(f"  {label[:50]}: {n} works to add" if n else f"  {label[:50]}: engages the corpus well")


def _map_sections_to_candidates(sections, cited_bases, wanted):
    """Retrieve candidate works per paragraph, only among `wanted` when it is a set, and roll them up per section.

    Fills in "candidates" and "terms" on each section dict in place.
    """
    from index.store import retrieve_hybrid

    n_para = sum(len([p for p in s["paragraphs"] if len(p) >= _MIN_PARA_CHARS]) for s in sections)
    ui.info(f"mapping {n_para} paragraphs against the corpus…")
    items.stage("Matching your text to the papers")

    sp = progress.StepSpinner(f"mapping [{0}/{n_para}]")
    sp.start()
    done = 0
    try:
        for s in sections:
            cands = {}
            for para in s["paragraphs"]:
                if len(para) < _MIN_PARA_CHARS:
                    continue
                done += 1
                sp._label = f"mapping [{done}/{n_para}]"
                hits = _score_paragraph(para, cited_bases, wanted, retrieve_hybrid)
                cands = _merge_candidates(cands, hits)
            s["candidates"] = sorted(cands.values(), key=lambda h: h["score"], reverse=True)[:_PER_SECTION]
            s["terms"] = _section_terms(s)
        sp.done(f"{done} paragraphs mapped")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))


def _score_paragraph(para, cited_bases, wanted, retrieve_hybrid):
    """Return candidate work hits for one paragraph, keyed by work base id."""
    found = {}
    for h in retrieve_hybrid(para, k=config.GAPS_PARA_K, restrict_bases=wanted):
        base = h["base"]
        if base in cited_bases:
            continue
        if base not in found or found[base]["score"] < h["score"]:
            found[base] = h
    return found


def _merge_candidates(cands, hits):
    """Return cands with hits folded in, keeping the higher score per work."""
    merged = dict(cands)
    for base, hit in hits.items():
        if base not in merged or merged[base]["score"] < hit["score"]:
            merged[base] = hit
    return merged


def _synthesise_all(active):
    items.stage("Writing suggestions for each section")
    items.announce("total", len(active))
    sp = progress.StepSpinner(f"synthesising suggestions for {len(active)} sections")
    sp.start()
    try:
        with ThreadPoolExecutor(max_workers=min(config.LLM_MAX_WORKERS, len(active))) as pool:
            results = list(pool.map(_suggest, active))
        for s, r in zip(active, results):
            s["suggestions"] = r
        sp.done("done")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))


def _suggest(section):
    name = section["heading"] or section["text"][:SECTION_NAME_CHARS]
    items.announce("start", name)
    context = (f"{section['heading']}\n\n" if section["heading"] else "") + section["text"]
    response = llm.complete(
        prompts.gaps_section_system(),
        prompts.gaps_section_prompt(context[:3000], _briefs(section["candidates"]), section["terms"]),
        max_tokens=1200,
    )
    items.announce("ok", name)
    return _parse_suggestions(response)


def _section_terms(section):
    if not section["candidates"]:
        return []
    try:
        from index import cluster
        texts = [cluster.pool_text(h) for h in section["candidates"]]
        terms = cluster.ctfidf({0: list(range(len(texts)))}, texts, top_n=10).get(0, [])
    except Exception:
        return []
    body = section["text"].lower()
    return [t for t in terms if t.lower() not in body][:6]


def _briefs(cands):
    return "\n\n".join(
        f"[{h['authors']}: {h['title']}]\n{h.get('question', '')[:300]}"
        for h in cands
    )


def _bullets(response, label, stops):
    alts = "|".join(r"\*\*" + re.escape(s) for s in stops)
    lookahead = ("(?=" + alts + r"|\Z)") if alts else r"(?=\Z)"
    m = re.search(r"\*\*" + re.escape(label) + r":\*\*\s*(.+?)" + lookahead, response, re.DOTALL)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        line = line.lstrip("-•· ").strip().rstrip("*").strip()
        if line and line.lower() != "none":
            out.append(line)
    return out


def _parse_suggestions(response):
    return {
        "works":     _bullets(response, "Works to add", ["Arguments to engage", "Terms to incorporate"]),
        "arguments": _bullets(response, "Arguments to engage", ["Terms to incorporate"]),
        "terms":     _bullets(response, "Terms to incorporate", []),
    }


def _get_draft(input_file):
    if input_file:
        p = Path(input_file)
        if not p.exists():
            raise SystemExit(f"File not found: {input_file}")
        return p

    candidates = (
        sorted(config.INPUT_DIR.glob("*.md"))
        + sorted(config.INPUT_DIR.glob("*.txt"))
        + sorted(config.INPUT_DIR.glob("*.docx"))
    )
    if not candidates:
        raise SystemExit(
            f"No draft files found in {config.INPUT_DIR}.\n"
            "Drop a .md or .txt file there, or pass --input <path>."
        )
    choice = ui.menu("Select draft", [f.name for f in candidates])
    if choice is None:
        raise SystemExit("No draft chosen: pass --input FILE.")
    return candidates[choice]


def _detect_cited(text, works):
    """Return set of bases whose author surnames appear in the text."""
    text_lower = text.lower()
    cited = set()
    for w in works:
        for surname in w["authors"].split():
            if len(surname) > 3 and surname.lower() in text_lower:
                cited.add(w["base"])
                break
    return cited


def _split_sections(text):
    """Split a draft into sections on markdown headings; group paragraphs if none."""
    sections, cur = [], {"heading": None, "lines": []}
    for line in text.splitlines():
        if re.match(r"^#{1,6}\s+\S", line):
            if cur["heading"] is not None or cur["lines"]:
                sections.append(cur)
            cur = {"heading": line.lstrip("#").strip(), "lines": []}
        else:
            cur["lines"].append(line)
    if cur["heading"] is not None or cur["lines"]:
        sections.append(cur)

    result = []
    for s in sections:
        body = "\n".join(s["lines"]).strip()
        if not body and not s["heading"]:
            continue
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        result.append({"heading": s["heading"], "paragraphs": paras, "text": body})

    if len(result) == 1 and result[0]["heading"] is None:
        paras = result[0]["paragraphs"]
        if len(paras) > _FALLBACK_GROUP:
            result = [
                {"heading": None, "paragraphs": paras[i:i + _FALLBACK_GROUP],
                 "text": "\n\n".join(paras[i:i + _FALLBACK_GROUP])}
                for i in range(0, len(paras), _FALLBACK_GROUP)
            ]
    return result


def _write_gaps(sections, draft_name, output_name):
    """Write the gap report, and the papers it names in a .json of the same name."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(draft_name).stem
    out = config.OUTPUT_DIR / (output_name or f"gaps_{stem}_{ts}.md")

    lines = [f"# Gap Report for {draft_name}", ""]
    seen = {}
    for i, s in enumerate(sections, 1):
        label = s["heading"] or f"Section {i}"
        lines += [f"## {label}", ""]
        if not s["candidates"]:
            lines += ["_Engages the corpus well, no notable gaps._", "", "---", ""]
            continue
        sug = s.get("suggestions", {})
        if sug.get("works"):
            lines += ["**Works to add:**", ""] + [f"- {w}" for w in sug["works"]] + [""]
        if sug.get("arguments"):
            lines += ["**Arguments to engage:**", ""] + [f"- {a}" for a in sug["arguments"]] + [""]
        if sug.get("terms"):
            lines += ["**Terms to incorporate:**", ""] + [f"- {t}" for t in sug["terms"]] + [""]
        if not any(sug.get(k) for k in ("works", "arguments", "terms")):
            lines += ["_Candidate works were surfaced but none judged a genuine gap._", ""]
        lines += ["---", ""]
        for h in s["candidates"]:
            if h["base"] not in seen or seen[h["base"]]["score"] < h["score"]:
                seen[h["base"]] = h

    ranked = sorted(seen.values(), key=lambda h: h["score"], reverse=True)[:15]
    lines += ["## Raw ranked candidates", ""]
    lines += [f"- **{h['authors']}**: {h['title']} (score: {h['score']:.3f})" for h in ranked]

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    bases = [h["base"] for h in ranked]
    out.with_suffix(".json").write_text(json.dumps({"works": bases}, indent=2), encoding="utf-8")
    return out
