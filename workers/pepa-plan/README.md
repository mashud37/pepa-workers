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
corpus/                load.py  parse_para.py  — read pepa-sum para_ files
skeleton/              moves.py  build.py  — label moves and synthesise templates
plan/                  outline.py  refine.py  — generate and iterate outlines
cli/                   ui.py  progress.py  menu.py  install.py  show_config.py
                       abstract.py  outline.py  review.py
data/                  skeletons.json  (gitignored, kept via .gitkeep)
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
1) Build skeletons     2) Outline a paper     3) Review argumentation
4) Show config         5) Install / setup
```

## Direct subcommands

```
python manage.py abstract  [--limit N] [--sample N]
python manage.py outline   [--input FILE] [--literature FILE] [--skeleton-id ID]
                           [--feedback TEXT] [--no-input]
python manage.py review    [--input FILE]
python manage.py config
python manage.py install
```

## Building the skeleton library

`abstract` reads every `para_*.md` file in the corpus, labels each paragraph with
a rhetorical move (via Claude Haiku), then asks Claude Sonnet to cluster the
move-sequences into 3–6 canonical structural templates. The library is saved to
`data/skeletons.json` and a human-readable report to `output/skeletons_<ts>.md`.

```
python manage.py abstract
python manage.py abstract --sample 50   # random sample of 50 papers
python manage.py abstract --limit 100   # first 100 files only
```

## Outlining a paper

Drop your idea as a `.md` or `.txt` in `input/` (or paste it when prompted).
Optionally pass a literature notes file. Choose a skeleton, get a first outline,
then enter feedback in an iterative loop until the plan is ready. The final
outline is saved to `output/outline_<ts>.md`.

```
python manage.py outline --input input/my-idea.md
python manage.py outline --input input/idea.md --literature input/lit.md
python manage.py outline --no-input   # first shot only, no feedback loop
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
| Generate outline | Claude Sonnet | ~$0.03 |
| Refine outline (one pass) | Claude Sonnet | ~$0.04 |
| Review argumentation | Claude Sonnet | ~$0.02 |

> Estimates only — verify current pricing in the Anthropic console before relying on them.
