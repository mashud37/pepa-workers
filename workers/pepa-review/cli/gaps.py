"""WS2 — Draft gap-check, section by section.

Splits a draft into sections, maps semantically similar but uncited corpus works
to the section that surfaced them, derives distinctive terms for each, and asks
Claude (per section, in parallel) for the works to add, arguments to engage, and
terms to incorporate. The report mirrors a kopi-editor section-by-section worksheet.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import config
from cli import ui, progress
from backends import llm, prompt as prompts

_MIN_PARA_CHARS = 40        # paragraphs shorter than this are treated as headings/noise
_FALLBACK_GROUP = 4         # paragraphs per section when a draft has no headings
_PER_SECTION = 8            # candidate works carried into each section's prompt


def run(input_file=None):
    ui.header("Gap-check a draft")

    draft_path = _get_draft(input_file)
    if not draft_path:
        return
    draft_text = Path(draft_path).read_text(encoding="utf-8", errors="replace")
    ui.ok(f"draft: {Path(draft_path).name} ({len(draft_text)} chars)")

    from corpus.metadata import work_list
    all_works = work_list()
    cited_bases = _detect_cited(draft_text, all_works)
    ui.info(f"already cited: ~{len(cited_bases)} works detected in text")

    sections = _split_sections(draft_text)
    ui.info(f"{len(sections)} sections to check")

    from index.store import retrieve_hybrid
    n_para = sum(len([p for p in s["paragraphs"] if len(p) >= _MIN_PARA_CHARS]) for s in sections)
    ui.info(f"mapping {n_para} paragraphs against the corpus…")

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
                for h in retrieve_hybrid(para, k=config.GAPS_PARA_K):
                    base = h["base"]
                    if base in cited_bases:
                        continue
                    if base not in cands or cands[base]["score"] < h["score"]:
                        cands[base] = h
            s["candidates"] = sorted(cands.values(), key=lambda h: h["score"], reverse=True)[:_PER_SECTION]
            s["terms"] = _section_terms(s)
        sp.done(f"{done} paragraphs mapped")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    active = [s for s in sections if s["candidates"]]
    if not active:
        ui.ok("No gaps found — the draft engages well with the corpus.")
        return

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

    out = _write_gaps(sections, Path(draft_path).name)
    ui.ok(f"gap report saved to {out}")
    ui.rule()
    for i, s in enumerate(sections, 1):
        label = s["heading"] or f"Section {i}"
        n = len(s.get("suggestions", {}).get("works", [])) if s["candidates"] else 0
        ui.info(f"  {label[:50]} — {n} works to add" if n else f"  {label[:50]} — engages the corpus well")


def _suggest(section):
    context = (f"{section['heading']}\n\n" if section["heading"] else "") + section["text"]
    response = llm.complete(
        prompts.gaps_section_system(),
        prompts.gaps_section_prompt(context[:3000], _briefs(section["candidates"]), section["terms"]),
        max_tokens=1200,
    )
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
        f"[{h['authors']} — {h['title']}]\n{h.get('question', '')[:300]}"
        for h in cands
    )


def _parse_suggestions(response):
    def bullets(label, stops):
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

    return {
        "works":     bullets("Works to add", ["Arguments to engage", "Terms to incorporate"]),
        "arguments": bullets("Arguments to engage", ["Terms to incorporate"]),
        "terms":     bullets("Terms to incorporate", []),
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
    return candidates[choice] if choice is not None else None


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


def _write_gaps(sections, draft_name):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = config.OUTPUT_DIR / f"gaps_{ts}.md"

    lines = [f"# Gap Report for {draft_name}", ""]
    seen = {}
    for i, s in enumerate(sections, 1):
        label = s["heading"] or f"Section {i}"
        lines += [f"## {label}", ""]
        if not s["candidates"]:
            lines += ["_Engages the corpus well — no notable gaps._", "", "---", ""]
            continue
        sug = s.get("suggestions", {})
        if sug.get("works"):
            lines += ["**Works to add:**"] + [f"- {w}" for w in sug["works"]] + [""]
        if sug.get("arguments"):
            lines += ["**Arguments to engage:**"] + [f"- {a}" for a in sug["arguments"]] + [""]
        if sug.get("terms"):
            lines += ["**Terms to incorporate:**"] + [f"- {t}" for t in sug["terms"]] + [""]
        if not any(sug.get(k) for k in ("works", "arguments", "terms")):
            lines += ["_Candidate works were surfaced but none judged a genuine gap._", ""]
        lines += ["---", ""]
        for h in s["candidates"]:
            if h["base"] not in seen or seen[h["base"]]["score"] < h["score"]:
                seen[h["base"]] = h

    ranked = sorted(seen.values(), key=lambda h: h["score"], reverse=True)[:15]
    lines += ["## Raw ranked candidates", ""]
    lines += [f"- **{h['authors']}** — {h['title']} (score: {h['score']:.3f})" for h in ranked]

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
