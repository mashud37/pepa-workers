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

**Two structural levels: skeleton and blueprint.** The skeleton is section-to-section flow
(a stage like `ANALYSIS_FINDING`). The blueprint is the level below: how a multi-paragraph
run of one move unfolds internally. Blueprints reuse the labelling already done: the `para_`
text is re-joined to the stored move labels (`corpus/join.py`), so only synthesis is new, not
re-labelling. They live in a separate `data/blueprints.json` add-on so the skeleton library
stays stable. The within-move sub-structure is produced by LLM synthesis (the readable
artifact); a standalone, gitignored embedding track (`benchmark/submoves.py`) clusters the
move's paragraphs and writes an `agreement` note back, as a deterministic sanity check on the
granularity, not rhetorical ground truth, since text embeddings group by topic.

**Examples are deterministic.** A skeleton's example papers are the 20 corpus papers nearest
its move distribution under the Hellinger metric (`skeleton/examples.py`), not model-named:
the synthesis model only ever sees a sample and would otherwise invent base names.

## Roadmap

### Mid-term: argumentation routes from pepa-review

pepa-review builds a `map_*.md` cluster report that characterises each thematic thread's
key arguments and concepts. A future `pepa-plan route` command could read those cluster
reports and suggest which literature threads the paper should engage with at each stage
of the outline, grounding the plan in the actual field structure.

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
