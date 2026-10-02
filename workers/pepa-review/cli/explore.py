"""WS3: interactive discovery over the sum_ corpus, maintaining an active
body of works across turns that the user can follow up on, expand, or
replace with a new search.
"""
import config
from backends import llm
from backends import prompt as prompts
from cli import progress, ui
from index.store import retrieve_hybrid

_K = 40


def run(query=None):
    ui.header("Explore the literature")
    maps = sorted(config.OUTPUT_DIR.glob("corpus_map_*.md"))
    if maps:
        ui.info(f"corpus map available: {maps[-1].name}  (run 'python manage.py map' to refresh)")

    history = []
    active = _start_conversation(query, history)

    while True:
        if not active:
            q = ui.ask("Question (blank to exit)")
            if not q:
                break
            active = _fetch(q)
            if active:
                _reply(q, active, history)
                history.append(q)
            continue

        action = ui.menu("Next", [
            ("Ask a question",  f"{len(active)} works in context"),
            ("Expand corpus",   "add works matching new search terms"),
            ("New search",      "replace works, reset conversation"),
        ])
        if action is None:
            break

        if action == 0:
            q = ui.ask("Question")
            if not q:
                continue
            _reply(q, active, history)
            history.append(q)
            if len(history) > 12:
                history = history[-12:]

        elif action == 1:
            terms = ui.ask("Search terms to add")
            if not terms:
                continue
            new_hits = _fetch(terms)
            before = len(active)
            seen = {h["base"] for h in active}
            active = active + [h for h in new_hits if h["base"] not in seen]
            ui.ok(f"corpus: {before} → {len(active)} works")
            _print_corpus(active)

        elif action == 2:
            history = []
            active = _start_conversation(None, history)


def _start_conversation(query, history):
    """Fetch or select the first work set and fire an opening reply.

    Args:
        query: a query string to retrieve by, or None to prompt for a
            corpus source (query search or manual selection).
        history: the conversation history list, appended to in place.

    Returns:
        The list of active work-record dicts, possibly empty.
    """
    if query:
        active = _fetch(query)
        if active:
            _reply(query, active, history)
            history.append(query)
        return active

    corpus = _build_corpus()
    active = corpus["active"]
    if active and corpus["seed_query"]:
        _reply(corpus["seed_query"], active, history)
        history.append(corpus["seed_query"])
    return active


def _build_corpus():
    """Pick query-retrieval or manual preselection.

    Returns:
        dict with keys "active" (list of work-record dicts) and "seed_query"
        (the user's query string when method=Query, so the caller can fire
        an initial response, or None when method=Manual since the corpus
        is already shown and no auto-response is needed).
    """
    method = ui.menu("Corpus source", [
        ("Query",           f"retrieve top {_K} works by semantic similarity"),
        ("Select manually", "pick works by author/title keyword, fill remainder to threshold"),
    ])
    if method is None:
        return {"active": [], "seed_query": None}

    if method == 0:
        q = ui.ask("Query")
        if not q:
            return {"active": [], "seed_query": None}
        return {"active": _fetch(q), "seed_query": q}

    selected = _keyword_select()
    if not selected:
        return {"active": [], "seed_query": None}
    active = _fill_to_k(selected)
    ui.ok(f"corpus: {len(selected)} selected + {len(active) - len(selected)} auto-filled = {len(active)} works")
    _print_corpus(active)
    return {"active": active, "seed_query": None}


def _fetch(query):
    sp = progress.StepSpinner("retrieving")
    sp.start()
    try:
        hits = retrieve_hybrid(query, k=_K)
        sp.done(f"{len(hits)} works")
        return hits
    except SystemExit:
        sp.done("error")
        raise


def _fill_to_k(selected_records):
    """Backfill selected records up to _K via semantic similarity."""
    if len(selected_records) >= _K:
        return selected_records[:_K]

    extra_needed = _K - len(selected_records)
    selected_bases = {r["base"] for r in selected_records}
    query = " ".join(r.get("title", r["base"]) for r in selected_records[:6])

    sp = progress.StepSpinner("backfilling to threshold")
    sp.start()
    try:
        candidates = retrieve_hybrid(query, k=_K * 2)
        extra = [h for h in candidates if h["base"] not in selected_bases][:extra_needed]
        sp.done(f"+{len(extra)}")
        return selected_records + extra
    except SystemExit:
        sp.done("error")
        raise


def _keyword_select():
    """Keyword search over index records; returns list of full record dicts."""
    from index.store import _require_index
    try:
        idx = _require_index()
    except SystemExit:
        raise
    all_records = idx["records"]

    selected = []
    selected_bases = set()

    while True:
        term = ui.ask("Search (author surname or title keyword, blank to finish)")
        if not term:
            break
        term_low = term.lower()
        matches = [r for r in all_records
                   if term_low in r.get("authors", "").lower()
                   or term_low in r.get("title", "").lower()]
        if not matches:
            ui.warn(f"No works match '{term}'")
            continue

        print()
        visible = matches[:30]
        for i, r in enumerate(visible, 1):
            mark = "✓" if r["base"] in selected_bases else " "
            label = f"{r.get('authors', '')}: {r.get('title', '')[:55]}"
            print(f"  [{i:2}] {mark} {label}")
        if len(matches) > 30:
            ui.info(f"  … {len(matches) - 30} more: refine your search term")

        raw = ui.ask("Add by number (comma-separated, blank to skip)")
        if not raw:
            continue
        _add_by_number(raw, visible, selected, selected_bases)

    if selected:
        ui.info(f"{len(selected)} works selected")
    return selected


def _add_by_number(raw, visible, selected, selected_bases):
    """Add records named by 1-based index in a comma-separated string.

    Args:
        raw: comma-separated index string typed by the user.
        visible: the numbered records currently shown on screen.
        selected: list of chosen records, appended to in place.
        selected_bases: set of chosen record "base" ids, updated in place.
    """
    for part in raw.split(","):
        p = part.strip()
        if not p.isdigit():
            continue
        i = int(p) - 1
        if not (0 <= i < len(visible)):
            continue
        r = visible[i]
        if r["base"] in selected_bases:
            continue
        selected.append(r)
        selected_bases.add(r["base"])
        ui.ok(f"Added: {r.get('authors', '')}")


def _reply(query, active, history):
    briefs_text = _format_hits(active)
    hist_text = "\n".join(history[-6:])

    sp = progress.StepSpinner("responding")
    sp.start()
    try:
        response = llm.complete(
            prompts.explore_system(),
            prompts.explore_prompt(query, briefs_text, hist_text),
            max_tokens=2000,
        )
        sp.done("done")
    except Exception as e:
        sp.done("error")
        raise SystemExit(str(e))

    ui.rule()
    print(response)
    ui.rule()
    _print_corpus(active)


def _print_corpus(active):
    ui.info(f"Works in context ({len(active)}):")
    for h in active:
        ui.info(f"  {h.get('authors', '')}: {h.get('title', '')[:60]}")


def _format_hits(hits):
    parts = []
    for h in hits:
        parts.append(
            f"**{h.get('authors', '')}: {h.get('title', '')}**\n"
            f"Question: {h.get('question', '')}\n"
            f"Arguments: {h.get('arguments_text', '')[:500]}\n"
            f"Conclusions: {h.get('conclusions', '')[:300]}"
        )
    return "\n\n---\n\n".join(parts)


def _show_cluster_hint():
    maps = sorted(config.OUTPUT_DIR.glob("corpus_map_*.md"))
    if maps:
        ui.info(f"corpus map available: {maps[-1].name}  (run 'python manage.py map' to refresh)")
