# pepa-review

Downstream research tool for a `pepa-sum` corpus. Point it at the folder of
`sum_`/`para_`/`quote_` documents that `pepa-sum` produces and get four research
workstreams: literature review assembly, draft gap-checking, interactive literature
discovery, and a thematic corpus map. Single-user, local index.

## Layout

```
manage.py              entrypoint (no args = menu; subcommands also available)
config.py              CORPUS_DIR, model IDs, paths, env-var overrides
corpus/                load.py  parse_sum.py  metadata.py  — read pepa-sum outputs
index/                 embeddings.py  store.py  — build and query the vector index
backends/              anthropic_client.py  llm.py  prompt.py  — generation layer
cli/                   ui.py  progress.py  menu.py  install.py  show_config.py
                       index_cmd.py  review.py  gaps.py  explore.py  map.py  thread_map.py
data/                  index.json  (gitignored, kept via .gitkeep)
input/                 drop draft files and outlines here (gitignored)
output/                generated reviews, gap reports, corpus maps (gitignored)
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
1) Literature review    2) Gap-check a draft       3) Explore literature
4) Corpus map           5) Thread-level map        6) Build / refresh index
7) Bibliographic data   8) Show config             9) Install / setup
```

## Direct subcommands (scriptable)

```
python manage.py review  [--input <outline.md>] [--auto]
python manage.py gaps    --input <draft.md>
python manage.py explore [--query "<question>"]
python manage.py map     [--threads N]
python manage.py threadmap [--map <file>] [--thread N|NAME|all]
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

## Corpus map

Clusters every indexed work into thematic threads and writes a Markdown report —
per thread a discussion, key arguments, key concepts, dominant methods, and empirical
contexts, with the works listed below. The clustering follows the embedding-text recipe:
an ensemble of dense embeddings + title and literature TF-IDF, reduced with **UMAP**, then
**consensus clustering** (HDBSCAN + spherical k-means + Ward fused through a co-association
matrix). Granularity is chosen by silhouette score; **c-TF-IDF** grounds the thread names and
merges near-duplicate threads. Each work is assigned by its consensus strength: a bridging
work appears under a second thread, and a work that fits nothing well lands in a final
"Cross-cutting / outliers" section rather than being forced in.

```
python manage.py map               # auto-select thread count
python manage.py map --threads 12  # force a target thread count
```

Output is saved to `output/corpus_map_<timestamp>.md`, alongside a `corpus_map_<timestamp>.json`
sidecar that records each thread's works by index id. Install optional deps for the full
pipeline (without them the tool degrades to a plain k-means map):
```
pip install scikit-learn umap-learn hdbscan
```

## Thread-level map

The corpus map's thread count is capped relative to corpus size, so a large thread can stay
coarse. Rather than forcing the whole map finer (which thins every thread), drill into one
thread: the same pipeline re-runs over just that thread's works at a finer granularity band.
Pick a saved map, then one thread or all of them.

```
python manage.py threadmap                          # pick map + thread interactively
python manage.py threadmap --thread all             # detail every thread of the newest map
python manage.py threadmap --map corpus_map_<ts>.md --thread 3
```

Works are recovered from the map's `.json` sidecar; maps generated before the sidecar existed
fall back to matching the rendered work list against the index. Output is saved to
`output/thread_map_<thread>_<timestamp>.md`.

## Cost estimates

| Operation | Model | Approx. cost |
|---|---|---|
| Index papers (once) | Gemini gemini-embedding-001 | ~$0.002 per 100 papers |
| Gap-check a 5 000-word draft | Claude Haiku | ~$0.005 |
| Literature review (10 works) | Claude Sonnet | ~$0.09 |
| Discovery query | Claude Haiku | ~$0.002 |
| Corpus map (per thread) | Claude Sonnet | ~$0.01 |
| Thread-level map (per sub-thread) | Claude Sonnet | ~$0.01 |

> Estimates only — verify current pricing in the vendor console before relying on them.
> Embedding costs are negligible; generation costs dominate.
