"""Define system prompts and prompt builders for the LLM-generated
documents: the structured summary brief and the one-sentence-per-paragraph
rundown. The quote document is built deterministically and needs no prompt.
"""
import config

# The fixed summary contract. The model fills the bracketed fields and returns
# only this block: the renderer prepends the original filename as line one.
SUMMARY_TEMPLATE = """## <one-line title of the paper>

- **Question & context:** <the problem the paper addresses and why it matters>
- **Empirical context:** <country/region, time period, the people and societies studied, sites, and data sources, or "N/A (conceptual/theoretical)">
- **Literature drawn on:** <the bodies of work and key prior authors it builds on, and what it takes from each>
- **Methods:** <data, design, and techniques used, or "N/A (conceptual)">
- **Arguments:**
  1. <first argument, explained in detail: what is claimed and on what basis>
  2. <second argument, explained in detail>
  3. <further arguments as needed>
- **Key conclusions:** <what the paper establishes>
- **Discussion items:** <open questions, limitations, implications it raises>
"""

SUMMARY_SYSTEM = (
    "You are a precise academic summariser. You read one paper and return a "
    "structured Markdown brief, filling the template EXACTLY: same headings, "
    "same bullet order, every field present. Be explanatory and specific: state "
    "WHAT is argued and on what grounds, not merely that an argument is made, and "
    "name the actual concepts, places, and findings rather than gesturing at them. "
    "Be faithful to the text; never invent results, citations, or methods. Number "
    "the arguments (1, 2, 3, ...) and state each in enough detail to compare it "
    "against other papers. Output ONLY the filled template, no preamble.\n\n"
    "Template:\n" + SUMMARY_TEMPLATE
)

RUNDOWN_SYSTEM = (
    "You compress an academic paper into a paragraph-by-paragraph rundown. For "
    "each numbered paragraph you are given, write exactly ONE concise sentence "
    "capturing its single main point, keeping the SAME order and the SAME number. "
    "Be faithful; do not merge, reorder, or skip paragraphs, and do not add "
    "commentary. Output only the numbered list, one line per paragraph."
)

def _format_signals(signals):
    lines = []
    if signals.get("noun_phrases"):
        lines.append("Recurring concepts: " + "; ".join(signals["noun_phrases"]))
    if signals.get("entities"):
        lines.append("Named entities: " + "; ".join(signals["entities"]))
    if signals.get("svo"):
        triplets = [" / ".join(t) for t in signals["svo"]]
        lines.append("Subject-verb-object claims:\n  - " + "\n  - ".join(triplets))
    return "\n".join(lines)


def build_summary_prompt(text, signals, passages, budget=None):
    if budget is None:
        budget = config.text_budget()
    signal_block = _format_signals(signals)

    if len(text) <= budget:
        body = "=== Full paper text (references removed) ===\n\n" + text
    else:
        head = text[: budget // 3]
        passage_block = "\n\n---\n\n".join(passages)
        body = (
            "The paper is long, so here is its opening followed by the passages "
            "retrieved as most information-rich:\n\n"
            "=== Opening ===\n\n" + head +
            "\n\n=== Information-rich passages ===\n\n" + passage_block
        )

    return (
        "Deterministic signals extracted locally to guide you (keywords, named "
        "entities, and argument triplets: use them to locate the spine of the "
        "paper, but rely on the text for the wording):\n\n"
        f"{signal_block}\n\n"
        f"{body}\n\n"
        "Now produce the filled Markdown template for this paper."
    )


def build_rundown_prompt(paragraphs):
    numbered = "\n\n".join(f"Paragraph {i}:\n{p}" for i, p in enumerate(paragraphs, 1))
    return (
        "Condense each of these paragraphs into one sentence, keeping the number "
        "and order:\n\n" + numbered
    )
