"""Build the per-task prompts, with no IO and no ANSI.
"""
import json


def moves_system():
    return (
        "You are a scholarly research analyst trained to identify rhetorical moves in "
        "academic paragraph summaries. For each paragraph given, output exactly one move "
        "label from the controlled vocabulary. Be concise and precise."
    )


def moves_prompt(sentences):
    vocab = (
        "HOOK_PROBLEM, BACKGROUND, GAP, THESIS_AIM, CONTRIBUTION_PREVIEW, ROADMAP, "
        "LIT_POSITIONING, THEORY_CONCEPT, METHOD, DATA_SETTING, ANALYSIS_FINDING, "
        "INTERPRETATION, COUNTERPOINT_LIMITATION, IMPLICATION, FUTURE_WORK, CONCLUSION"
    )
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, 1))
    return (
        f"Vocabulary (use exactly as written): {vocab}\n\n"
        f"Paragraphs:\n{numbered}\n\n"
        "For each paragraph, output one line: '<number>. <MOVE_LABEL>'. "
        "Use only labels from the vocabulary. Output nothing else."
    )


def skeleton_system():
    return (
        "You are a research methodology analyst. You will receive move-sequence data from "
        "a corpus of academic papers. Identify a small set (3–6) of canonical structural "
        "templates that recur across papers. Output strict JSON only: no commentary, no "
        "code fences, no extra text."
    )


def skeleton_prompt(sequences, n_total=None):
    """`sequences` is the (possibly sampled) compact list actually shown to the
    model; `n_total` is the full corpus size it was drawn from, so the model knows
    it is generalising from a representative sample, not the whole corpus."""
    data = json.dumps(sequences, ensure_ascii=False)
    shown = len(sequences)
    header = (
        f"Move sequences from a representative sample of {shown} papers "
        f"(drawn from {n_total} total):"
        if n_total and n_total != shown
        else f"Move sequences from {shown} papers:"
    )
    return (
        f"{header}\n{data}\n\n"
        "Return a JSON array of skeleton objects. Each object must have these exact keys:\n"
        '  "id": string (short slug),\n'
        '  "name": string (3–6 word descriptive name),\n'
        '  "paper_type": string (e.g. empirical, conceptual, review, methods),\n'
        '  "description": string (one sentence),\n'
        '  "stages": array of {"move": string, "intent": string, "typical_share": number}\n'
        "Output the JSON array and nothing else. Do not include example papers. Those are "
        "attached deterministically from the corpus afterwards."
    )


def blueprint_system():
    return (
        "You are a research methodology analyst. You will receive real example sections "
        "from academic papers of one structural type: each section is a run of consecutive "
        "paragraph summaries that all perform the same rhetorical move. Identify the typical "
        "internal progression: the ordered sub-moves a writer steps through within such a "
        "section. Output strict JSON only: no commentary, no code fences."
    )


def blueprint_prompt(skeleton, move, intent, sections):
    blocks = []
    for i, sec in enumerate(sections, 1):
        para = "\n".join(f"  {j}. {t}" for j, t in enumerate(sec, 1))
        blocks.append(f"Section {i} ({len(sec)} paragraph(s)):\n{para}")
    body = "\n\n".join(blocks)
    return (
        f"STRUCTURAL TEMPLATE: {skeleton.get('name', '')} ({skeleton.get('paper_type', '')})\n"
        f"MOVE: {move}, {intent}\n\n"
        f"Real example sections performing this move:\n\n{body}\n\n"
        "Identify how such a section typically unfolds across its paragraphs. Return a JSON "
        "object with exactly these keys:\n"
        '  "progression": array of 2-6 objects, each {"sub_move": a SHORT_UPPER_SNAKE label, '
        '"intent": one short phrase for what that paragraph does, "typical_position": one of '
        '"first" | "early" | "mid" | "late" | "last"},\n'
        '  "reads_like": one sentence describing the section\'s overall arc.\n'
        "Order progression as the paragraphs typically occur. Output the JSON object only."
    )


def outline_system():
    return (
        "You are a scholarly writing coach helping a researcher plan an academic paper. "
        "You produce detailed, forward-looking paragraph plans: each paragraph entry "
        "specifies the rhetorical move it performs and the specific intellectual point it "
        "will make. Be concrete, substantive, and faithful to the chosen structural template."
    )


def _blueprint_block(blueprint):
    """Render the skeleton's within-section guides: for each blueprinted move, the
    ordered sub-move progression a multi-paragraph section of it should step through."""
    if not blueprint:
        return ""
    lines = ["\nWITHIN-SECTION GUIDES: when a stage below spans several paragraphs, "
             "progress through these sub-moves in order:"]
    for move, bp in blueprint.items():
        sub = " → ".join(s.get("sub_move", "") for s in bp.get("progression", []))
        if not sub:
            continue
        band = bp.get("typical_paragraphs") or []
        span = f" (~{band[0]}–{band[1]} paras)" if len(band) == 2 else ""
        lines.append(f"- {move}{span}: {sub}")
    return "\n".join(lines) + "\n" if len(lines) > 1 else ""


def outline_prompt(idea, literature, skeleton, structure=None, blueprint=None):
    lit_block = f"\nLITERATURE NOTES:\n{literature}\n" if literature else ""
    lit_note = (
        "Where literature is provided, note which sources or claims each paragraph draws on. "
        if literature else ""
    )
    skel_block = (
        f"\nSTRUCTURAL TEMPLATE: {skeleton.get('name', '')} "
        f"({skeleton.get('paper_type', '')})\n"
        f"{skeleton.get('description', '')}\n"
        f"Stages: " + ", ".join(
            s.get("move", "") for s in skeleton.get("stages", [])
        ) + _blueprint_block(blueprint)
    ) if skeleton else ""
    if structure:
        return (
            f"PAPER IDEA:\n{idea}\n"
            f"{lit_block}\n"
            "REQUIRED STRUCTURE, follow this exactly: reproduce every section below in "
            "order, with the number of paragraphs it specifies, and make each paragraph "
            "fulfil the intent given for it. Do not add, drop, merge, or reorder sections "
            "or paragraphs.\n"
            f"\n{structure}\n\n"
            "Write the plan grouped under the same section headings. Under each heading, "
            "number the paragraphs and for each write:\n"
            "  <N>. [MOVE]: <the specific point this paragraph makes>\n"
            + lit_note
            + "Be specific about arguments, not just topics. Output the structured plan only."
        )
    return (
        f"PAPER IDEA:\n{idea}\n"
        f"{lit_block}"
        f"{skel_block}\n\n"
        "Write a numbered paragraph-by-paragraph plan. For each paragraph:\n"
        "  <N>. [MOVE]: <the specific point this paragraph makes>\n"
        "Follow the template's stage sequence. "
        + lit_note
        + "Be specific about arguments, not just topics. Output the numbered list only."
    )


def refine_system():
    return (
        "You are a scholarly writing coach revising a paragraph plan in response to "
        "researcher feedback. Preserve sound structure; apply the feedback precisely. "
        "Return the complete revised outline in the same numbered format."
    )


def refine_prompt(outline, feedback):
    return (
        f"CURRENT OUTLINE:\n{outline}\n\n"
        f"FEEDBACK:\n{feedback}\n\n"
        "Apply the feedback and return the full revised outline. "
        "Keep every paragraph on its own numbered line in the format: "
        "'<N>. [MOVE]: <point>'. Output the revised outline only."
    )


def review_system():
    return (
        "You are a scholarly peer reviewer assessing the argumentation flow of an academic "
        "paper idea or draft. Be analytical and specific. Structure your response with clear "
        "sections. Reference the actual content, not generic advice."
    )


def review_prompt(text, skeleton=None):
    skel_block = ""
    if skeleton:
        skel_block = (
            f"\nREFERENCE STRUCTURE: {skeleton.get('name', '')} "
            f"({skeleton.get('paper_type', '')})\n"
            f"Expected progression: "
            + " → ".join(s.get("move", "") for s in skeleton.get("stages", []))
            + "\n"
        )
    return (
        f"TEXT TO REVIEW:\n{text}\n"
        f"{skel_block}\n"
        "Provide structured feedback in three sections:\n\n"
        "## Overall flow assessment\n"
        "[2–3 sentences on whether the argument builds coherently and reaches its conclusion]\n\n"
        "## Stage-by-stage walkthrough\n"
        "[For each major rhetorical move: is it present, appropriately weighted, and "
        "well-connected to what precedes and follows? Flag missing moves, thin transitions, "
        "and mis-ordered stages.]\n\n"
        "## Concrete fixes\n"
        "[Bulleted list of specific, actionable revisions]"
    )
