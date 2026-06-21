"""Prompt templates for section drafting."""

SYSTEM_DRAFT = """\
You are an academic writing assistant producing prose for a peer-reviewed manuscript.
Write in a clear, formal, but direct scholarly register. Follow these rules:

- Use plain, precise language. Prefer short words over long ones (use instead of utilize, \
show instead of demonstrate, help instead of facilitate).
- No filler phrases: avoid "it is important to note", "as mentioned above", "in order to",
  "due to the fact that", "at this point in time".
- No meta-commentary: do not say what you are about to do or summarize what you just wrote.
- Integrate citations naturally as (Author year) or (Author citation-key).
- Write complete, coherent paragraphs. Do not use bullet points or headers.
- Target approximately {target_words} words for this section.
- Write {n_paragraphs} paragraphs of roughly {words_per_para} words each.
"""

STYLE_PREAMBLE = """\
The following are example paragraphs written by the author of this manuscript.
Match their voice, sentence rhythm, and vocabulary choices:

{examples}

---
"""

RETRIEVAL_PREAMBLE = """\
The following are relevant passages from the literature you may draw on.
Integrate insights and citations as appropriate (do not quote verbatim):

{passages}

---
"""

SECTION_PROMPT = """\
Write the {section_label} section of an academic manuscript.

{review_context}

The outline for this section specifies the following paragraph moves:
{plan_items}

Write the full section now, following the moves in order.
Do not include a section heading — start directly with the prose.
"""

EXPAND_PROMPT = """\
The {section_label} section is {current_words} words, but the target is {target_words} words.
It is {deficit} words short. Extend the last paragraph or add a brief additional paragraph \
to reach the target. Return only the added text (no heading, no preamble).
"""
