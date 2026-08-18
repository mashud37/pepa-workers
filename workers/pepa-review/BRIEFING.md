# BRIEFING: build the `pepa-review` repo

You (a Sonnet agent) are scaffolding a new personal-scale Python CLI package, **`pepa-review`**, at
`C:\Users\andreas\OneDrive\Development\pepa-review` (this folder). It is a **downstream consumer of
`pepa-sum`**: `pepa-sum` already turns academic PDFs into three Markdown documents per paper, and
**~426 papers are already processed** in `../pepa-sum/output/`. `pepa-review` turns that corpus into
a research tool.

## Context & goal

`pepa-review` supports four research workstreams over the `pepa-sum` outputs:

1. **Literature review assembly**: user gives a rough outline + arguments and selects works/authors;
   the tool assembles a literature review, drawing primarily on the `sum_` briefs.
2. **Draft gap-check**: user gives a draft (finished or WIP); via embeddings the tool finds
   `sum_`/`para_` overlaps and suggests works that are missed or underused.
3. **Discovery**: user is new to a literature and wants an intelligent way to explore and interrogate
   the information in the `sum_` briefs.
4. **Knowledge graph**: cluster works by `sum_`-level similarity, support adding/updating works, and
   let the graph evolve to surface recurring topics, themes, arguments, and literatures.

**Locked design decisions:**
- **Name:** `pepa-review` (sibling to `pepa-sum`).
- **Interface:** CLI only: `manage.py` menu + scriptable subcommands, fully policy-conformant.
- **Scope:** scaffold all four workstreams now (breadth-first), on one shared core.
- **Embeddings:** reuse `cli-chat`'s `embeddings.py` (Gemini + Ollama), **default Gemini**;
  provider stamped into the index.
- **Corpus source:** `config.py` holds `CORPUS_DIR` defaulting to `../pepa-sum/output`; read in
  place and build `pepa-review`'s own index. No copying.

---

## 0. Read these first (authoritative, not suggestions)

Read every policy in `../00_policies/` before scaffolding and match each to a real repo as you go:
`README.md` (the new-package checklist), `coding-style.md`, `architecture.md`, `dependencies.md`,
`security.md`, `cli.md`, `cli-style.md`, `models.md`, `readme-structure.md`. Non-negotiables you
will be checked against:
- **Windows-first, no `bash`** in any normal path; glue in Python; PowerShell 5.1-safe if a script
  is justified (`coding-style.md` §6).
- **Function-named folders, flat root, one `manage.py` entrypoint**; no `src/`/`lib/`/`utils.py`
  (`architecture.md`).
- **Stdlib-first**; heavy deps lazy + optional (`dependencies.md`).
- **Secrets in gitignored YAML + `*.example` template + env override**; canonical `.gitignore`
  (`security.md`).
- **`manage.py`: bare = menu, args = subcommands, menu mirrors subcommands 1:1; enumerate, don't
  interrogate; result→stdout, logs→stderr; `SystemExit("msg")` for user errors** (`cli.md`).
- **Centralize model IDs/prices in config; default to latest in tier; Anthropic has no embeddings
  API** (`models.md`).

## 1. The data contract you consume (study `../pepa-sum/output/` directly)

Each paper yields three files named `<prefix>_<base>.md`, sharing one `<base>`:

- **`sum_<base>.md`**: the structured brief. **Fixed shape**, every file identical, so they parse
  deterministically:
  - **Line 1:** the source filename, e.g. `Alaimo Kallinikos_Objects metrics and practices….pdf`.
    The convention is `<AuthorLastnames>_<Title>.pdf`: **authors are the substring before the
    first `_`; title is after it.**
  - **`## <one-line title>`**: H2 heading.
  - Bold-labelled fields, always in this order: **`- **Question & context:**`**,
    **`Empirical context:`**, **`Literature drawn on:`**, **`Methods:`**, **`Arguments:`** (a
    numbered sub-list, each item often `**bold lead.** explanation`), **`Key conclusions:`**,
    **`Discussion items:`**. Parse on these labels.
- **`para_<base>.md`**: line 1 = source filename; then a numbered list, one sentence per source
  paragraph, in document order.
- **`quote_<base>.md`**: line 1 = source filename; then a bullet list of verbatim quotes. **Note:
  these are noisy**, some bullets are extracted headers/footers/citation boilerplate (e.g. "LSE
  Research Online is the repository…"). Treat `quote_` as lower-trust detail, not primary signal.

Build the index and all reasoning primarily on **`sum_`** (clean, structured), use **`para_`** for
finer-grained overlap detection (WS2), and **`quote_`** only for illustrative pull-quotes.

## 2. Repo layout to create (function-named, flat root)

```
manage.py              entrypoint: no args = menu; subcommands also work
config.py              CORPUS_DIR (default ../pepa-sum/output), embeddings + model IDs, paths, env override
requirements.txt       pyyaml, numpy   (lazy/optional: scikit-learn, networkx, note in README, not core)
secrets.example.yaml   gemini_api_key, anthropic_api_key, gcp_project, gcp_region  (secrets.yaml gitignored)
README.md              per readme-structure.md
.gitignore             canonical (security.md §5)

corpus/                read + parse the pepa-sum outputs
  load.py              discover sum_/para_/quote_ files in CORPUS_DIR, pair by <base>
  parse_sum.py         sum_ file -> dict{file, authors, title, question, empirical, literature, methods, arguments[], conclusions, discussion}
  metadata.py          authors (filename prefix), title (H2); the work-list for selection menus

index/                 embeddings + similarity store (REUSE cli-chat)
  embeddings.py        adapt cli-chat/backends/embeddings.py (gemini + ollama, stdlib urllib; default gemini)
  store.py             adapt cli-chat/cli/projects.py: build_index/retrieve/cosine; provider-stamped JSON in data/

backends/              LLM generation (anthropic default) + prompts
  anthropic_client.py  copy pepa-sum/backends/anthropic_client.py
  llm.py prompt.py     routing + per-workstream prompt builders

cli/                   one module per workstream + shared UI
  ui.py                COPY pepa-sum/cli/ui.py verbatim (canonical Windows console handling)
  progress.py          COPY pepa-sum/cli/progress.py
  menu.py install.py show_config.py
  review.py            WS1
  gaps.py              WS2
  explore.py           WS3
  graph.py             WS4

data/                  index + graph caches (gitignored, .gitkeep)
input/                 user drafts/outlines dropped here (gitignored, .gitkeep)
output/                generated reviews + graph exports (gitignored, .gitkeep)
```

`config.py`: model the precedence + accessor pattern on `../pepa-sum/config.py` (env var → file →
default). **Centralize all model IDs here** (generation default `claude-haiku-4-5-20251001`, allow
Sonnet for synthesis-heavy WS1; embeddings default Gemini `text-embedding-004`). Use the default
`secrets.yaml`+`secrets.example.yaml` shape (this repo is not a Cloud Run app, so prefer
`secrets.yaml` over `env.yaml`).

## 3. Shared core: build and prove this BEFORE the four workstreams

All four sit on the same two pieces; get them solid first:
1. **`corpus/` parse**: `load.py` pairs files by `<base>`; `parse_sum.py` splits a `sum_` doc into
   its labelled fields; `metadata.py` yields the `{authors, title, base}` work-list used by every
   selection menu. A handful of unit-style checks against real files in `../pepa-sum/output`.
2. **`index/` embed + retrieve**: adapt `cli-chat`'s `embeddings.py` (stdlib HTTP, gemini default)
   and `projects.py`'s `build_index`/`retrieve`/cosine into `index/store.py`. **Index unit = one
   `sum_` brief** (optionally one record per Argument for finer recall); stamp `provider`/`model`/`dim`
   into the JSON cache in `data/`; on provider mismatch raise the same re-index `SystemExit` cli-chat
   uses. Reuse cli-chat's `verify_quotes` idea wherever the tool emits a quote.
   - **Retrieval quality (`cs_ir_stats_reference.md` §6).** Pure dense cosine is the baseline, but the
     reference's durable lesson is **hybrid retrieve-then-rerank**: dense embeddings (§6.8) catch
     paraphrase, BM25 (§6.2) catches exact terms, and they fuse cleanly with **Reciprocal Rank Fusion**
     (§6.6, ~6 lines, no score normalization). `pepa-sum` already computes BM25 locally, so a
     BM25⊕dense RRF blend is a cheap, high-recall upgrade for WS2/WS3: keep it **optional**, default
     to cosine. (TREC-style nDCG/MAP evaluation in §7 is overkill for a personal tool; skip unless you
     want to measure a ranking change.)

## 4. The four workstreams (scaffold all; each is a `cli/` module + menu entry + subcommand)

**WS1: Literature review assembly (`review.py`, `review`).**
User supplies a rough outline + arguments (free text via `$EDITOR` or a file in `input/`) and
**selects works/authors**. Per `cli.md` *enumerate, don't interrogate*: list the parsed work/author
set for numbered multi-select (`ui.menu`), with a free-text/path fallback: never a blind prompt.
Then: embed the outline → retrieve relevant `sum_` briefs (restricted to the selection when given),
feed their structured **Arguments/Key conclusions/Literature** fields + the outline to the LLM, and
draft a thematically-organised review that synthesises and cites the selected works, pulling `para_`
detail where needed. Write the review to `output/`.

**WS2: Draft gap-check (`gaps.py`, `gaps`).**
User supplies a draft (file in `input/` or a path). Chunk + embed the draft; for each chunk retrieve
nearest `sum_`/`para_` records. Detect which corpus works the draft **already engages** (match author
surnames / titles in the draft text), then surface works that are **semantically close but absent or
underused**, ranked by similarity, each with a one-line "why" naming the overlapping `sum_` field.

**WS3: Discovery (`explore.py`, `explore`).**
Interactive RAG over the `sum_` corpus: user asks about a topic → embed → retrieve top briefs →
present their titles + Question/Arguments → allow follow-ups. Same retrieval core as WS2/WS4,
specialised to the `sum_` structure; surface emergent themes/clusters from WS4 when available.

**WS4: Knowledge graph (`graph.py`, `graph`).**
Over the shared `sum_` embeddings (computed **once** and reused everywhere:
`cs_ir_stats_reference.md` golden rule #1). For "recurring topics, themes" the reference's headline
recipe is **embedding-based clustering, not classical LDA/NMF**: it recommends **UMAP → HDBSCAN**
(§2.6 / §5.4), exactly what **BERTopic** wraps (§3.5: embeddings → UMAP → HDBSCAN → c-TF-IDF), which
it calls the most interpretable option, auto-picks the topic count, supports **hierarchical topic
reduction** (good for the "evolving graph"), and **reuses the embeddings you already built**. Use
BERTopic to label themes (**lazy/optional** per `dependencies.md`); fall back to spherical/cosine
k-means on the raw vectors when the heavier stack (`bertopic`/`hdbscan`/`umap-learn`) isn't installed.
Validate cluster quality with silhouette (§2 validation). Build a kNN similarity graph (edges = cosine
≥ threshold); mine recurring arguments from the parsed Arguments fields + spaCy noun-phrase/SVO
triples (§4.5–4.7). Persist the graph as JSON in `data/` (nodes = works + metadata + cluster; edges =
similarity). **Incremental update:** when new `sum_` files appear in `CORPUS_DIR`, embed and assign
them to the nearest cluster and extend the graph rather than rebuilding; to track how the literature
**drifts** over corpus additions, compare cluster word-distributions with **Jensen-Shannon** (§1.11,
a true metric). Since the interface is CLI-only, **view the graph as an exported file**: GraphML or a
standalone HTML (`networkx`/`pyvis`, lazy-optional) written to `output/`.

## 5. Models, deps, CLI shape

- **Generation:** Claude via the copied `anthropic_client.py`; IDs centralised in `config.py`,
  default Haiku, Sonnet selectable for WS1. **Embeddings:** Gemini default (`models.md`: Anthropic
  has none), Ollama path preserved from the cli-chat code.
- **Dependencies:** core = `pyyaml`, `numpy`; everything heavy (`scikit-learn`, `networkx`/`pyvis`,
  any clustering extras) is **imported lazily and degrades gracefully**, noted in the README, kept
  out of `requirements.txt` core where the code runs without it.
- **`manage.py`:** thin parse+dispatch (`../cli-chat/manage.py` is the reference). Menu ordered by
  frequency, ending in setup/config:
  ```
  1) Literature review   2) Gap-check a draft   3) Explore the literature
  4) Knowledge graph     5) Build/refresh index 6) Show config   7) Install / setup
  ```
  Every entry has a subcommand twin: `review`, `gaps`, `explore`, `graph`, `index`, `config`,
  `install`. `install` is idempotent (creates `secrets.yaml` from template, checks deps, verifies
  `CORPUS_DIR` exists and reports the paper count). Long jobs (indexing ~426 papers) show `[i/N]`
  progress via `progress.py` and write incrementally / skip done work.

## 6. README (per readme-structure.md)

Title → one-paragraph purpose (consumes pepa-sum's `sum_`/`para_`/`quote_` outputs; single-user;
local) → optional trade-off table → Layout block → Setup (`pip install`, `python manage.py install`,
point `CORPUS_DIR` at `pepa-sum/output`) → Menu → Direct subcommands → one `##` per workstream with
a runnable example → Cost estimates with the "estimates only" disclaimer.

## 7. Verification (prove it works)

1. `python manage.py install`: creates `secrets.yaml`, reports the `CORPUS_DIR` paper count (~426).
2. `python manage.py index`: builds the embedding index over `sum_` briefs; provider stamped; re-run
   skips/refreshes incrementally.
3. `python manage.py explore` with a topic query returns relevant briefs by title: proves
   parse+embed+retrieve end to end.
4. `python manage.py gaps --input <a-draft.md>` lists plausibly-missed works with a why-line.
5. `python manage.py review` with a small outline + a 3-work selection produces a cited review in
   `output/`.
6. `python manage.py graph` writes a clustered graph export to `output/` and a JSON cache to `data/`.
7. Spot-check policy conformance: no `src/`/`utils.py`, no `bash` dependency, secrets gitignored,
   menu↔subcommand parity, errors via `SystemExit`.

## Reuse map (copy/adapt, don't reinvent)

| Need | Source |
|---|---|
| Embeddings (gemini+ollama, stdlib http) | `../cli-chat/backends/embeddings.py` |
| Index build / cosine retrieve / provider-stamped cache / quote verify | `../cli-chat/cli/projects.py` |
| Canonical Windows console UI + spinners/progress | `../pepa-sum/cli/ui.py`, `../pepa-sum/cli/progress.py` |
| Anthropic generation client | `../pepa-sum/backends/anthropic_client.py` |
| `config.py` precedence + accessors | `../pepa-sum/config.py` |
| Thin `manage.py` parse+dispatch | `../cli-chat/manage.py` |
| `sum_` field shape to parse | any `../pepa-sum/output/sum_*.md` |
