# pepa-plan design briefing

## What this is

pepa-plan is the third tool in the pepa-* family after pepa-sum (summarise papers) and
pepa-review (retrieve and synthesise). It closes the loop: a researcher has read the
literature (via pepa-sum) and understands the field (via pepa-review); pepa-plan helps
them write.

The MVP is deliberately file-based and stateless. No vector index, no live pepa-review
calls. The two moving pieces are: (1) a skeleton library built once from the corpus, and
(2) outline generation/refinement driven by that library.

## Design choices

**Skeleton as the structural prior.** Academic writing has a small vocabulary of paragraph
moves (HOOK, GAP, METHOD, FINDING, ...). The skeleton library makes that vocabulary
explicit and corpus-grounded. Researchers pick a template that matches their paper type;
the LLM fills it with their specific arguments.

**Iterative outline, not one-shot.** The feedback loop in `cli/outline.py` is the core UX.
A first shot is rarely the final plan; the loop lets the researcher refine without leaving
the terminal.

**Move labelling at scale, synthesis with quality.** Haiku handles the bulk labelling of
hundreds of paragraph sentences cheaply. Sonnet is invoked once for the synthesis step
where reasoning quality matters. The same quality/default split applies throughout.

**No retrieval in MVP.** Literature is an optional plain-text file the researcher provides.
This avoids the embedding infrastructure cost and keeps the tool useful before pepa-sum
has been run.

## Roadmap

### Mid-term: argumentation routes from pepa-review

pepa-review builds a `map_*.md` cluster report that characterises each thematic thread's
key arguments and concepts. A future `pepa-plan route` command could read those cluster
reports and suggest which literature threads the paper should engage with at each stage
of the outline — grounding the plan in the actual field structure.

Implementation sketch:
- Parse `map_*.md` files from pepa-review's output.
- At outline generation time, match each skeleton stage to relevant cluster themes.
- Inject as a "literature anchoring" block in the outline prompt.

### Long-term: full-draft agent

Once an outline is accepted, a multi-step agent could draft each paragraph in sequence,
maintaining a context window of the previous paragraphs and the literature file. Each
paragraph would be a separate Sonnet call, preserving coherence through a rolling summary.

This requires:
- A `plan/draft.py` module with a paragraph-by-paragraph loop.
- A `cli/draft.py` command with progress output per paragraph.
- Possibly a checkpointing mechanism so interrupted drafts can resume.
