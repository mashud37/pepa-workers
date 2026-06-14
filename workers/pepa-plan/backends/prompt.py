"""Per-task prompt builders — no IO, no ANSI."""
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
        "templates that recur across papers. Output strict JSON only — no commentary, no "
        "code fences, no extra text."
    )


def skeleton_prompt(sequences):
    data = json.dumps(sequences, ensure_ascii=False)
    return (
        f"Move sequences from {len(sequences)} papers:\n{data}\n\n"
        "Return a JSON array of skeleton objects. Each object must have these exact keys:\n"
        '  "id": string (short slug),\n'
        '  "name": string (3–6 word descriptive name),\n'
        '  "paper_type": string (e.g. empirical, conceptual, review, methods),\n'
        '  "description": string (one sentence),\n'
        '  "stages": array of {"move": string, "intent": string, "typical_share": number},\n'
        '  "example_bases": array of strings (base names of representative papers)\n'
        "Output the JSON array and nothing else."
    )


def outline_system():
    return (
        "You are a scholarly writing coach helping a researcher plan an academic paper. "
        "You produce detailed, forward-looking paragraph plans — each paragraph entry "
        "specifies the rhetorical move it performs and the specific intellectual point it "
        "will make. Be concrete, substantive, and faithful to the chosen structural template."
    )


def outline_prompt(idea, literature, skeleton):
    lit_block = f"\nLITERATURE NOTES:\n{literature}\n" if literature else ""
    skel_block = (
        f"\nSTRUCTURAL TEMPLATE: {skeleton.get('name', '')} "
        f"({skeleton.get('paper_type', '')})\n"
        f"{skeleton.get('description', '')}\n"
        f"Stages: " + ", ".join(
            s.get("move", "") for s in skeleton.get("stages", [])
        )
    ) if skeleton else ""
    return (
        f"PAPER IDEA:\n{idea}\n"
        f"{lit_block}"
        f"{skel_block}\n\n"
        "Write a numbered paragraph-by-paragraph plan. For each paragraph:\n"
        "  <N>. [MOVE] — <the specific point this paragraph makes>\n"
        "Follow the template's stage sequence. "
        + ("Where literature is provided, note which sources or claims each paragraph draws on. " if literature else "")
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
        "'<N>. [MOVE] — <point>'. Output the revised outline only."
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
