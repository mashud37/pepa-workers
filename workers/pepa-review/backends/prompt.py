"""Per-workstream prompt builders."""

MAX_CLUSTER_WORKS = 20


def review_system():
    return (
        "You are a scholarly research assistant assembling an academic literature review. "
        "Write in a formal, analytical style. Synthesise arguments across sources rather than "
        "summarising them one by one. Cite works inline as (AuthorLastname Year-or-keyword). "
        "Be substantive: show where works agree, diverge, and complement each other."
    )


def review_prompt(outline, briefs_text):
    return (
        f"USER OUTLINE AND ARGUMENTS:\n{outline}\n\n"
        f"SELECTED WORKS (sum_ briefs):\n{briefs_text}\n\n"
        "Follow the outline's structure: treat each numbered point, heading, or paragraph "
        "marker in the outline as its own section with its own `##` heading. Do not collapse "
        "them into a single section. Under each, synthesise the works that bear on that point, "
        "showing agreements, divergences, and gaps, and cite every claim inline. End with a "
        "short synthesis paragraph tying the sections together."
    )


def review_plan_system():
    return (
        "You are a scholarly research assistant planning the structure of a literature review. "
        "You identify the key terms and the genuine tensions running through a body of work, "
        "then organise them into a small number of overarching sections. Be specific and draw "
        "directly on the works provided."
    )


def review_plan_prompt(outline, briefs_text, terms, n_min, n_max):
    terms_block = f"DISTINCTIVE TERMS ACROSS THE WORKS (c-TF-IDF): {', '.join(terms)}\n\n" if terms else ""
    return (
        f"USER PROMPT / ROUGH OUTLINE:\n{outline}\n\n"
        f"SELECTED WORKS (sum_ briefs):\n{briefs_text}\n\n"
        f"{terms_block}"
        f"First name the key terms and the central tensions in this literature. Then map them "
        f"into {n_min} to {n_max} overarching sections that together structure a review answering "
        f"the prompt. Use exactly this format:\n\n"
        f"**Key terms and tensions:**\n"
        f"- [term or tension, one line each, 4 to 7 items]\n\n"
        f"**Section:** [section title]\n"
        f"- Covers: [the terms/tensions this section develops]\n"
        f"- Works: [Author surnames of the works that belong here]\n\n"
        f"(repeat the **Section:** block for each section, in reading order)"
    )


def review_section_system():
    return (
        "You are a scholarly research assistant drafting one section of an academic literature "
        "review. Write in a formal, analytical style. Synthesise the works rather than "
        "summarising them one by one; show where they agree, diverge, and complement each other. "
        "Cite works inline as (AuthorLastname Year-or-keyword)."
    )


def review_section_prompt(title, covers, briefs_text, debate_block=""):
    covers_block = f"This section develops: {covers}\n\n" if covers else ""
    return (
        f"SECTION TITLE: {title}\n\n"
        f"{covers_block}"
        f"WORKS FOR THIS SECTION (sum_ briefs):\n{briefs_text}\n\n"
        f"{debate_block}"
        f"Draft this section as 1 to 3 connected paragraphs under a `## {title}` heading. "
        f"Advance an argument; do not list works. Cite every claim inline."
    )


def gaps_section_system():
    return (
        "You are a research assistant reviewing one section of a scholarly draft against a corpus "
        "of works it has not yet cited. For that section only, you recommend the most relevant "
        "missed works, the arguments the section should engage, and the terms it should "
        "incorporate. Be specific and skip anything not genuinely relevant to this section."
    )


def gaps_section_prompt(section_text, candidate_briefs, terms):
    terms_block = f"CANDIDATE DISTINCTIVE TERMS (from the missed works): {', '.join(terms)}\n\n" if terms else ""
    return (
        f"DRAFT SECTION:\n{section_text}\n\n"
        f"CANDIDATE WORKS NOT YET CITED (most similar to this section):\n{candidate_briefs}\n\n"
        f"{terms_block}"
        f"Use exactly this format; write 'none' under a heading if nothing applies:\n\n"
        f"**Works to add:**\n"
        f"- [Authors, keyword]: the specific argument or evidence it would contribute here\n"
        f"**Arguments to engage:**\n"
        f"- [an argument from these works this section should address]\n"
        f"**Terms to incorporate:**\n"
        f"- [a term or concept the section should name, with a 4-6 word gloss]"
    )


def gaps_system():
    return (
        "You are a research assistant helping a scholar identify missed or underutilised sources. "
        "Be concise and specific. For each relevant work, write one line: "
        "'[Authors, keyword]: <reason it is relevant to the draft>'."
    )


def gaps_prompt(draft_excerpt, candidate_briefs):
    return (
        f"DRAFT EXCERPT:\n{draft_excerpt}\n\n"
        f"CANDIDATE WORKS NOT YET CITED:\n{candidate_briefs}\n\n"
        "For each candidate work that is genuinely relevant to the draft excerpt, write one line "
        "explaining why. Skip works that are not relevant. Be specific about which aspect of the "
        "draft connects to which aspect of the work."
    )


def explore_system():
    return (
        "You are a knowledgeable research guide helping a scholar explore an academic literature. "
        "Answer questions about the literature, identify recurring themes and tensions, and point "
        "to relevant works. Be concise but substantive. Cite works as (Authors) when relevant. "
        "End each response with 2-3 suggested follow-up questions."
    )


def explore_prompt(query, briefs_text, history=""):
    hist_block = f"CONVERSATION SO FAR:\n{history}\n\n" if history else ""
    return (
        f"{hist_block}"
        f"USER QUERY:\n{query}\n\n"
        f"RELEVANT WORKS FROM THE CORPUS:\n{briefs_text}\n\n"
        "Answer the query drawing on the works above. Identify themes and tensions. "
        "Suggest follow-up questions."
    )


def map_system():
    return (
        "You are a research analyst characterising a thematic cluster of academic works. "
        "Be precise and substantive. Draw directly on what the works argue, not generic summaries. "
        "Name authors when attributing concepts or arguments."
    )


def map_thread_prompt(records, total_in_cluster, max_works=MAX_CLUSTER_WORKS, top_terms=None):
    parts = []
    for r in records[:max_works]:
        entry = (
            f"**{r.get('authors', '')}: {r.get('title', '')}**\n"
            f"Question: {r.get('question', '')}\n"
            f"Arguments: {r.get('arguments_text', '')[:350]}"
        )
        methods = r.get("methods", "")[:120]
        empirical = r.get("empirical", "")[:120]
        if methods:
            entry += f"\nMethods: {methods}"
        if empirical:
            entry += f"\nContext: {empirical}"
        parts.append(entry)

    shown = len(records[:max_works])
    note = f" (showing {shown} most central of {total_in_cluster})" if total_in_cluster > max_works else ""
    works_text = "\n\n".join(parts)
    terms_block = (
        f"Distinctive terms for this cluster (c-TF-IDF): {', '.join(top_terms)}\n\n"
        if top_terms else ""
    )

    return (
        f"The following {total_in_cluster} academic works form a thematic cluster{note}:\n\n"
        f"{works_text}\n\n"
        f"{terms_block}"
        f"---\n"
        f"Provide all six sections below. Be specific: cite authors by surname.\n\n"
        f"**Theme:** [3–7 word thread name]\n"
        f"**Discussion:** [2–3 sentences on the thread's intellectual contribution and internal tensions]\n"
        f"**Key arguments:**\n"
        f"- [empirical or analytical claim that recurs across works, 5 to 7 items]\n"
        f"**Key concepts:**\n"
        f"- [Term: brief definition (Author/s), 4 to 6 items]\n"
        f"**Methods:** [1–2 sentences on dominant research approaches used]\n"
        f"**Empirical contexts:** [brief description of countries, platforms, cultural settings studied]\n"
    )
