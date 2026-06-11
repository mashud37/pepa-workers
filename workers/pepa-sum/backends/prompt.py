"""Build the system + user prompt sent to the instruction-tuned model.

The user prompt always leads with the deterministic signals (keywords, named
entities, argument triplets). For the body it keeps the prompt small so CPU
generation stays fast: if the reference-stripped paper fits the character
budget it sends the full text; if not, it sends the opening plus the retrieved
information-rich passages instead of the whole thing. The system prompt pins
the exact markdown template so every summary is structured identically and
therefore comparable across papers.
"""
import config

# The fixed output contract. The model fills the bracketed fields and returns
# only this block — the renderer prepends the original filename as line one.
TEMPLATE = """## <one-line title of the paper>

- **Question & context:** <the problem the paper addresses and why it matters>
- **Literature drawn on:** <the bodies of work / key prior authors it builds on>
- **Methods:** <data, design, and techniques used — or "N/A (conceptual)">
- **Arguments:**
  1. <first argument, stated in detail>
  2. <second argument, stated in detail>
  3. <further arguments as needed>
- **Key conclusions:** <what the paper establishes>
- **Discussion items:** <open questions, limitations, implications it raises>
"""

SYSTEM = (
    "You are a precise academic summariser. You read one paper and return a "
    "structured Markdown brief, filling the template EXACTLY — same headings, "
    "same bullet order, every field present. Be faithful to the text and never "
    "invent results, citations, or methods. Number the arguments (1, 2, 3, ...) "
    "and state each in enough detail to compare it against other papers. Output "
    "ONLY the filled template, no preamble.\n\nTemplate:\n" + TEMPLATE
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


def build_prompt(text, signals, passages, budget=config.TEXT_BUDGET):
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
        "entities, and argument triplets — use them to locate the spine of the "
        "paper, but rely on the text for the wording):\n\n"
        f"{signal_block}\n\n"
        f"{body}\n\n"
        "Now produce the filled Markdown template for this paper."
    )
