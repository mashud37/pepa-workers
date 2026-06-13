"""WS2 — Draft gap-check.

Chunks a draft, retrieves semantically similar corpus works, identifies which
are absent from the draft's citations, and asks Claude to explain why each
missed work is relevant.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

import config
from cli import ui, progress
from backends import llm, prompt as prompts


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

    from index.store import retrieve_hybrid
    chunks = _chunk(draft_text)
    ui.info(f"checking {len(chunks)} draft chunks against corpus…")

    candidates = {}
    for i, chunk in enumerate(chunks):
        print(f"  [{i + 1}/{len(chunks)}]", end="\r", file=sys.stderr)
        for h in retrieve_hybrid(chunk, k=5):
            base = h["base"]
            if base not in cited_bases:
                if base not in candidates or candidates[base]["score"] < h["score"]:
                    candidates[base] = h
    print(" " * 20, end="\r", file=sys.stderr)

    if not candidates:
        ui.ok("No gaps found — the draft engages well with the corpus.")
        return

    ranked = sorted(candidates.values(), key=lambda h: h["score"], reverse=True)[:15]
    ui.step(f"Top {len(ranked)} potentially missed works")

    sp = progress.StepSpinner("generating explanations")
    sp.start()
    try:
        candidate_text = "\n\n".join(
            f"[{h['authors']} — {h['title']}]\n{h.get('question', '')[:300]}"
            for h in ranked
        )
        explanation = llm.complete(
            prompts.gaps_system(),
            prompts.gaps_prompt(draft_text[:2000], candidate_text),
            max_tokens=2000,
        )
        sp.done("done")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    ui.rule()
    print(explanation)
    ui.rule()

    out = _write_gaps(explanation, ranked, Path(draft_path).name)
    ui.ok(f"gap report saved to {out}")


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


def _chunk(text, size=800, overlap=100):
    step = max(1, size - overlap)
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += step
    return chunks


def _write_gaps(explanation, ranked, draft_name):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = config.OUTPUT_DIR / f"gaps_{ts}.md"
    header = f"# Gap Report for {draft_name}\n\n"
    raw = "## Raw ranked candidates\n\n" + "\n".join(
        f"- **{h['authors']}** — {h['title']} (score: {h['score']:.3f})"
        for h in ranked
    )
    out.write_text(header + explanation + "\n\n---\n\n" + raw, encoding="utf-8")
    return out
