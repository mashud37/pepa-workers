# pepa-review

Downstream research tool for a `pepa-sum` corpus. Point it at the folder of
`sum_`/`para_`/`quote_` documents that `pepa-sum` produces and get four research
workstreams: literature review assembly, draft gap-checking, interactive literature
discovery, and an evolving knowledge graph. Single-user, local index.

## Layout

```
manage.py              entrypoint (no args = menu; subcommands also available)
config.py              CORPUS_DIR, model IDs, paths, env-var overrides
corpus/                load.py  parse_sum.py  metadata.py  — read pepa-sum outputs
index/                 embeddings.py  store.py  — build and query the vector index
backends/              anthropic_client.py  llm.py  prompt.py  — generation layer
cli/                   ui.py  progress.py  menu.py  install.py  show_config.py
                       index_cmd.py  review.py  gaps.py  explore.py  graph.py
data/                  index.json  graph.json  (gitignored, kept via .gitkeep)
input/                 drop draft files and outlines here (gitignored)
output/                generated reviews, gap reports, graph exports (gitignored)
secrets.example.yaml   committed template; secrets.yaml is gitignored
```

## Setup

```
pip install -r requirements.txt
python manage.py install      # creates secrets.yaml, checks deps, reports paper count
python manage.py              # launch menu
```

Add your API keys to `secrets.yaml`:

```yaml
anthropic_api_key: "sk-ant-..."
gemini_api_key: "AIza..."
```

If `pepa-sum` lives somewhere other than `../pepa-sum`:
```yaml
corpus_dir: "C:/path/to/pepa-sum/output"
```

Then build the index:
```
python manage.py index
```

## Menu

```
1) Literature review    2) Gap-check a draft    3) Explore literature
4) Knowledge graph      5) Build / refresh index   6) Show config   7) Install / setup
```

## Direct subcommands (scriptable)

```
python manage.py review  [--input <outline.md>] [--auto]
python manage.py gaps    --input <draft.md>
python manage.py explore [--query "<question>"]
python manage.py graph   [--force] [--export {graphml|html}] [--update]
python manage.py index   [--force]
python manage.py config
python manage.py install
```

## Literature review

Drop an outline (or write one in your editor) and optionally pick which works to
draw on. The tool retrieves the matching `sum_` briefs and asks Claude Sonnet to
draft a thematically organised review with inline citations.

```
python manage.py review --input input/my-outline.md
python manage.py review --auto        # auto-selects top-10 works by similarity
```

Works can be selected by typing author surnames or title keywords — the tool
filters the list, shows numbered results, and lets you pick by number. Repeat
until you have the right set.

## Gap-check a draft

Drop a draft `.md` or `.txt` into `input/` (or pass `--input`). The tool chunks
the draft, computes BM25+dense similarity against the corpus (via RRF), identifies
works that are semantically close but absent from the draft's citations, and asks
Claude to explain why each is relevant.

```
python manage.py gaps --input input/my-draft.md
```

Output is saved to `output/gaps_<timestamp>.md`.

## Explore the literature

Interactive query loop over the `sum_` index. Ask anything — themes, methods,
arguments, specific authors. The tool retrieves the top-8 briefs via hybrid
retrieval and asks Claude to synthesise and respond with follow-up suggestions.

```
python manage.py explore
python manage.py explore --query "how do scholars theorise algorithmic power?"
```

## Knowledge graph

Embeds all `sum_` briefs (reusing the index), clusters works into themes (HDBSCAN
if available, k-means fallback), and builds a kNN similarity graph (cosine ≥ 0.70).
Exports GraphML for Gephi/Cytoscape or standalone HTML (pyvis).

```
python manage.py graph                    # build and export graphml
python manage.py graph --export html      # standalone HTML with pyvis
python manage.py graph --update           # add new works without full rebuild
```

Install optional deps for richer output:
```
pip install scikit-learn hdbscan networkx pyvis
```

## Cost estimates

| Operation | Model | Approx. cost |
|---|---|---|
| Index papers (once) | Gemini text-embedding-004 | ~$0.002 per 100 papers |
| Gap-check a 5 000-word draft | Claude Haiku | ~$0.005 |
| Literature review (10 works) | Claude Sonnet | ~$0.09 |
| Discovery query | Claude Haiku | ~$0.002 |

> Estimates only — verify current pricing in the vendor console before relying on them.
> Embedding costs are negligible; generation costs dominate.
