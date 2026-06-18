# pepa-plan

Takes a researcher from a paper idea to a paragraph-by-paragraph outline. Learns
structural templates from a pepa-sum corpus, then uses those templates to guide
outline generation and argumentation review. Single-user, local — only generation
calls leave the machine.

## Layout

```
manage.py              entrypoint (no args = menu; subcommands also available)
config.py              corpus dir, model IDs, paths, env-var overrides
backends/              anthropic_client.py  llm.py  prompt.py  — generation layer
corpus/                load.py  parse_para.py  join.py  — read pepa-sum para_ files
skeleton/              moves.py  build.py  examples.py  blueprint.py  — label, synthesise, blueprint
plan/                  outline.py  refine.py  — generate and iterate outlines
cli/                   ui.py  progress.py  menu.py  install.py  show_config.py
                       abstract.py  blueprint.py  outline.py  review.py  templates.py
templates/             example.plan.md  + your own *.plan.md structures
data/                  skeletons.json  blueprints.json  (gitignored, kept via .gitkeep)
input/                 drop idea files and literature notes here (gitignored)
output/                outlines, feedback, skeleton reports (gitignored)
secrets.example.yaml   committed template; secrets.yaml is gitignored
```

## Setup

```
pip install -r requirements.txt
python manage.py install      # creates secrets.yaml, checks deps, reports para file count
python manage.py              # launch menu
```

Add your API key to `secrets.yaml`:

```yaml
anthropic_api_key: "sk-ant-..."
```

If `pepa-sum` lives somewhere other than `../pepa-sum`:

```yaml
corpus_dir: "C:/path/to/pepa-sum/output"
```

Then build the skeleton library:

```
python manage.py abstract
```

## Menu

```
1) Build skeletons      2) Build blueprints    3) Outline a paper
4) Plan templates       5) Review argumentation
6) Show config          7) Install / setup
```

## Direct subcommands

```
python manage.py abstract  [--limit N] [--sample N] [--mode auto|serial|parallel|batch]
python manage.py blueprint
python manage.py outline   [--input FILE] [--literature FILE] [--template FILE]
                           [--skeleton-id ID] [--feedback TEXT] [--no-input]
python manage.py template  [--new NAME] [--list]
python manage.py review    [--input FILE]
python manage.py config
python manage.py install
```

## Building the skeleton library

`abstract` reads every `para_*.md` file in the corpus, labels each paragraph with
a rhetorical move (via Claude Haiku), then asks Claude Sonnet to cluster the
move-sequences into 3–6 canonical structural templates. The library is saved to
`data/skeletons.json` and a human-readable report to `output/skeletons_<ts>.md`.

The labelled sequences are checkpointed to `data/sequences.json` before the
clustering step, so a failure during clustering never discards the paid labelling
work. Move sequences are long and near-unique per paper, so for very large corpora
the clustering call runs on a representative sample that fits the model context
(the full set is still saved to `data/sequences.json`).

```
python manage.py abstract
python manage.py abstract --sample 50   # random sample of 50 papers
python manage.py abstract --limit 100   # first 100 files only
```

Labelling is one fast LLM call per paper, so for large corpora it runs in one of
three modes (default `--mode auto`, picked by estimated wall-clock):

| Mode | What it does | Best for |
|---|---|---|
| `serial` | one paper at a time | a single paper or a tiny corpus |
| `parallel` | a bounded thread pool of live calls | up to a few thousand papers |
| `batch` | the Anthropic Message Batches API — ~50% cheaper, asynchronous (up to ~1h) | thousands of papers |

`auto` switches to `batch` around a few thousand papers. The final clustering call
is always live. A per-run token/cost estimate prints when the build finishes.

In `batch` mode the batch id is printed when the batch is submitted. A completed
batch's results stay retrievable from the API for 29 days, so if the run is
interrupted after the batch finishes you can rebuild the library from its saved
results file without re-billing the labelling:

```
python -m skeleton.recover path/to/batch_results.jsonl
```

## Within-section blueprints

A skeleton stage such as `ANALYSIS_FINDING` is usually a *run* of several
paragraphs, not one. `blueprint` adds the level below the skeleton: for each
skeleton and each of its major moves (those over a share threshold), it describes
how that section typically unfolds, paragraph by paragraph — an ordered list of
sub-moves with a typical paragraph count.

It needs no re-labelling. The `para_` summary text is re-read from the corpus and
joined back to the move labels already in `data/sequences.json` (their numbering
aligns), so only the synthesis calls are new. Each major move's real sections are
gathered from its skeleton's example papers and one Sonnet call returns the
progression. The result is a standalone add-on, `data/blueprints.json`, plus a
report in `output/`; the skeleton library itself is untouched.

```
python manage.py blueprint
```

When you outline with a learned skeleton, any blueprints that exist are injected
automatically, so the generated plan expands each multi-paragraph stage through its
sub-move progression.

Example papers are also selected deterministically — each skeleton lists the 20
corpus papers whose move distribution most closely matches it (real, verifiable
bases rather than model-named ones).

## Outlining a paper

Drop your idea as a `.md` or `.txt` in `input/` (or paste it when prompted).
Optionally pass a literature notes file. Then choose how the plan is structured —
either a **plan template** you authored (see below) or a learned **skeleton**. Get
a first outline, then enter feedback in an iterative loop until the plan is ready.
The final outline is saved to `output/outline_<ts>.md`.

```
python manage.py outline --input input/my-idea.md
python manage.py outline --input input/idea.md --literature input/lit.md
python manage.py outline --input input/idea.md --template templates/my-plan.plan.md
python manage.py outline --no-input   # first shot only, no feedback loop
```

## Plan templates

A plan template is a markdown file describing the exact section and paragraph
progression you want an outline to follow — for example *Introduction, four
paragraphs: (1) real-world context, (2) problems and gaps, (3) approach and
findings, (4) arguments and conclusions*. When a template is selected, the
generator reproduces that structure verbatim instead of relying on a learned
skeleton (so you can outline without first building the skeleton library).

Copy the shipped `templates/example.plan.md`, edit it to your structure, then pick
it when outlining. Templates live in `templates/`; your own copies are gitignored.

```
python manage.py template --new "empirical paper"   # copies the example
python manage.py template --list
python manage.py outline --template templates/empirical-paper.plan.md
```

## Reviewing argumentation

Pass any idea or draft text. The tool checks it against the argumentation-flow
template and returns structured feedback: overall flow, stage-by-stage walkthrough,
and concrete fixes. Output saved to `output/feedback_<ts>.md`.

```
python manage.py review --input input/my-draft.md
```

## Cost estimates

| Operation | Model | Approx. cost |
|---|---|---|
| Label one paper's moves | Claude Haiku | ~$0.001 |
| Build skeleton library (100 papers) | Haiku + Sonnet | ~$0.15 |
| Build within-section blueprints | Claude Sonnet | ~$0.40 (one call per major move) |
| Generate outline | Claude Sonnet | ~$0.03 |
| Refine outline (one pass) | Claude Sonnet | ~$0.04 |
| Review argumentation | Claude Sonnet | ~$0.02 |

> Estimates only — verify current pricing in the Anthropic console before relying on them.
> Building in `batch` mode bills the per-paper labelling at ~50%.
