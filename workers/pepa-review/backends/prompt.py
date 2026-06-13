"""Per-workstream prompt builders."""


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
        "Write a thematically organised literature review that directly advances the "
        "arguments in the outline. For each theme, synthesise the works — showing agreements, "
        "divergences, and gaps. Cite every claim. End with a short synthesis paragraph "
        "tying the themes together."
    )


def gaps_system():
    return (
        "You are a research assistant helping a scholar identify missed or underutilised sources. "
        "Be concise and specific. For each relevant work, write one line: "
        "'[Authors — keyword]: <reason it is relevant to the draft>'."
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


def map_thread_prompt(records, total_in_cluster, max_works=20, top_terms=None):
    parts = []
    for r in records[:max_works]:
        entry = (
            f"**{r.get('authors', '')} — {r.get('title', '')}**\n"
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
        f"Provide all six sections below. Be specific — cite authors by surname.\n\n"
        f"**Theme:** [3–7 word thread name]\n"
        f"**Discussion:** [2–3 sentences on the thread's intellectual contribution and internal tensions]\n"
        f"**Key arguments:**\n"
        f"- [empirical or analytical claim that recurs across works — 5 to 7 items]\n"
        f"**Key concepts:**\n"
        f"- [Term: brief definition (Author/s) — 4 to 6 items]\n"
        f"**Methods:** [1–2 sentences on dominant research approaches used]\n"
        f"**Empirical contexts:** [brief description of countries, platforms, cultural settings studied]\n"
    )
