"""WS1 — Literature review assembly.

User provides a rough outline and selects works. The tool retrieves the matching
sum_ briefs and asks Claude Sonnet to draft a thematically organised review.
"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import config
from cli import ui, progress
from corpus.metadata import work_list, display_label
from backends import llm, prompt as prompts


def run(outline_file=None, auto=False):
    ui.header("Literature review")

    works = work_list()
    if not works:
        raise SystemExit("No papers found in corpus. Check CORPUS_DIR configuration.")

    outline = _get_outline(outline_file)
    if not outline:
        raise SystemExit("No outline provided.")
    ui.ok(f"outline: {len(outline)} chars")

    selected = _auto_select(works, outline) if auto else _select_works(works, outline)
    if not selected:
        raise SystemExit("No works selected.")
    ui.ok(f"selected: {len(selected)} works")

    ui.step("Retrieving briefs…")
    from index.store import retrieve
    restrict = {w["base"] for w in selected}
    hits = retrieve(outline, k=len(selected), restrict_bases=restrict)

    sp = progress.StepSpinner("generating review")
    sp.start()
    try:
        review_text = llm.complete(
            prompts.review_system(),
            prompts.review_prompt(outline, _format_briefs(hits)),
            max_tokens=6000,
            quality=True,
        )
        sp.done("done")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    out_path = _write_review(review_text, selected)
    ui.ok(f"saved to {out_path}")
    ui.rule()
    print(review_text)


def _get_outline(outline_file):
    if outline_file:
        p = Path(outline_file)
        if not p.exists():
            raise SystemExit(f"File not found: {outline_file}")
        return p.read_text(encoding="utf-8").strip()

    input_files = sorted(config.INPUT_DIR.glob("*.md")) + sorted(config.INPUT_DIR.glob("*.txt"))
    options = [("Open in editor", "write outline in $EDITOR / notepad")]
    options += [(f.name, str(f)) for f in input_files]

    choice = ui.menu("Outline source", options)
    if choice is None:
        return None
    if choice == 0:
        return _editor_input()
    return input_files[choice - 1].read_text(encoding="utf-8").strip()


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


def _select_works(works, outline):
    choice = ui.menu("Work selection", [
        ("Auto-select",       "embed outline → retrieve 10 most relevant works"),
        ("Search by keyword", "filter by author surname or title keyword, then pick"),
    ])
    if choice is None:
        return []
    if choice == 0:
        return _auto_select(works, outline)
    return _keyword_select(works)


def _auto_select(works, outline):
    from index.store import retrieve
    sp = progress.StepSpinner("auto-selecting")
    sp.start()
    try:
        hits = retrieve(outline, k=10)
        sp.done(f"{len(hits)} works")
    except SystemExit:
        sp.done("error")
        raise
    by_base = {w["base"]: w for w in works}
    selected = [by_base[h["base"]] for h in hits if h["base"] in by_base]
    ui.step("Auto-selected:")
    for w in selected:
        ui.info(display_label(w))
    if not ui.confirm("Use these works?", default_yes=True):
        return _keyword_select(works)
    return selected


def _keyword_select(works):
    selected = []
    selected_bases = set()

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
            mark = _c_ok("✓") if w["base"] in selected_bases else " "
            print(f"  [{i}] {mark} {display_label(w)}")

        raw = ui.ask("Add numbers (comma-separated, blank to skip)")
        if not raw:
            continue
        for part in raw.split(","):
            p = part.strip()
            if p.isdigit():
                idx = int(p) - 1
                if 0 <= idx < len(matches):
                    w = matches[idx]
                    if w["base"] not in selected_bases:
                        selected.append(w)
                        selected_bases.add(w["base"])
                        ui.ok(f"Added: {w['authors']}")

    if not selected:
        ui.warn("No works selected — falling back to auto-select")
        from index.store import retrieve
        hits = retrieve("academic research", k=5)
        by_base = {w["base"]: w for w in works}
        selected = [by_base[h["base"]] for h in hits if h["base"] in by_base]

    return selected


def _c_ok(text):
    try:
        from cli.ui import _COLOR, GREEN, RESET
        return f"{GREEN}{text}{RESET}" if _COLOR else text
    except Exception:
        return text


def _format_briefs(hits):
    parts = []
    for h in hits:
        parts.append(
            f"### {h.get('authors', '')} — {h.get('title', '')}\n"
            f"**Question:** {h.get('question', '')}\n\n"
            f"**Arguments:** {h.get('arguments_text', '')}\n\n"
            f"**Conclusions:** {h.get('conclusions', '')}\n\n"
            f"**Literature drawn on:** {h.get('literature', '')}"
        )
    return "\n\n---\n\n".join(parts)


def _write_review(text, selected):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = config.OUTPUT_DIR / f"review_{ts}.md"
    works_list = "\n".join(f"- {w['authors']} — {w['title']}" for w in selected)
    footer = f"\n\n---\n\n## Works drawn on\n\n{works_list}\n"
    out.write_text(text + footer, encoding="utf-8")
    return out
