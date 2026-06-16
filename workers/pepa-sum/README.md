# pepa-sum

Turn a folder of academic PDFs into a **structured, comparable knowledge base**.
Drop papers into `input/`, run one command, and get **three Markdown documents
per paper** in `output/`:

| File | What it is |
|---|---|
| `sum_<name>.md` | the structured brief — question & context, **empirical context**, literature, methods, numbered arguments, conclusions, discussion |
| `para_<name>.md` | a paragraph-by-paragraph rundown, one sentence per paragraph, in document order |
| `quote_<name>.md` | the most expressive **verbatim** quotes (model-selected, then checked against the source) |

Splitting the output this way is deliberate: a downstream agent can read the
`sum_` briefs to pick relevant papers, then draw on the `para_` rundowns and
`quote_` files for detail — the raw material for generating literature reviews.

All the expensive *reading* (OCR, spaCy signals, BM25 retrieval, reference
stripping) happens locally; only a compact, signal-enriched prompt goes to the
LLM.

## Backends

| Backend | When | Notes |
|---|---|---|
| **`anthropic`** (default) | normal use | Claude Haiku — ~$0.03–0.05 per paper. |
| `cloudrun` | self-hosted | Qwen-3B on Cloud Run (scale-to-zero). Needs a deploy. |

Switch with **`python manage.py settings`** (saved to `env.yaml`, applied to
every run).

## Layout
```
manage.py              entrypoint (no args = menu; subcommands also available)
config.py              effective config: backend, settings, paths, budget
cli/                   command modules (summarize, settings, install, config, deploy) + ui/progress
extract/               local preprocessing: read_pdf (OCR + reference strip), signals, passages, paragraphs
documents/             builds the three output documents (summary, rundown, quotes)
backends/              LLM routing (anthropic / cloudrun) + prompts
render/                writes <prefix>_<name>.md
serve/ Dockerfile gcloud_app.yaml deploy.ps1 deploy.sh   the self-hosted cloudrun backend (optional)
env.yaml.example       template, safe to commit (env.yaml is gitignored)
input/ output/ data/   runtime folders (gitignored, kept via .gitkeep)
```

## Setup
```
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python manage.py install      # creates env.yaml, checks deps
python manage.py              # launch menu
```
Set `anthropic_api_key` in `env.yaml` (or `ANTHROPIC_API_KEY` env var) for the default backend.

> **Self-hosted backend (optional):** `python manage.py settings` → `cloudrun`,
> then `python manage.py deploy`. Windows-first: `deploy` runs `deploy.ps1`
> (PowerShell, no `bash` needed); POSIX runs the `deploy.sh` mirror.

> **Scanned PDFs (optional OCR):** image-only pages need
> `pip install pytesseract pdf2image` plus the system tools **tesseract** and
> **poppler**. Without them, born-digital PDFs still work; scanned pages are
> skipped with a warning.

## Menu
```
1) Summarise papers   2) Settings   3) Show config   4) Install / setup   5) Deploy service
```

## Direct subcommands (scriptable)
```
python manage.py summarize [--input <dir>] [--output <dir>] [--force] [--mode auto|serial|parallel|batch]
python manage.py settings
python manage.py config
python manage.py install
python manage.py deploy
```
- `--input <dir>` / `--output <dir>` — override the default `input/` / `output/`.
- `--force` — reprocess papers already done (otherwise resumable: a paper with a
  `sum_` file is skipped, or — interactively — you're asked before overwriting).
- `--mode` — force an execution mode; default `auto` (see below).

A paper that keeps failing is logged and skipped, not fatal — just re-run to pick
it up (its documents are absent, so it is retried). This is true in every mode.

## Execution modes

The run picks how to execute by **estimated wall-clock time** for the number of
papers that actually need work (`--mode auto`, the default):

| Mode | What it does | Best for |
|---|---|---|
| **serial** | one paper at a time, live per-step spinner | a single paper; the `cloudrun` backend |
| **parallel** | a **pipeline**: local reading runs across **processes** (escapes the GIL) a bounded look-ahead *ahead* of the LLM thread pool, so the next papers' spaCy/BM25 work runs on the CPU while the current papers' LLM calls wait on the network. Memory stays flat (`LOCAL_BATCH` window), LLM calls bounded by `MAX_CONCURRENCY` | tens to a couple hundred papers |
| **batch** | the same prompts go to the **Anthropic Message Batches API** — ~50% cheaper, far higher throughput, asynchronous (usually within ~1h, max 24h). The local stage **spools each paper's artifacts to a temp folder**, so the parent process never holds every paper's text at once | large volumes (hundreds–thousands) |

The crossover is time-based: parallel is bounded by your account's sustained rate
(more workers won't beat the tier limit), while batch has a latency floor but very
high throughput, so it overtakes parallel once the volume is large. `auto` prints
the estimate for each mode and marks the one it chose before starting.

> **All three modes produce the same documents** — identical model, system
> prompts, prompt builders, temperature, and post-processing. Only the transport
> differs (live request vs. batch endpoint), so batch is a cost/throughput choice,
> not a quality one. (Model output is still stochastic; "same" means same model
> and configuration, not byte-identical text.)

Force a mode for a one-off run, or persist it via `settings` / `env.yaml`:

```powershell
$env:PEPA_MODE = "batch"; python manage.py summarize
python manage.py summarize --mode parallel
```

`cloudrun` is always serial (a single scale-to-zero instance); batch requires the
`anthropic` backend.

## Tuning throughput

The simplest dial is the **speed tier** (`python manage.py settings` → *Parallel
speed*, or `PEPA_SPEED`), which moves the API *and* local throughput together:

| Tier | Papers at once | Live LLM calls | Read processes | Est. throughput | Use when |
|---|---|---|---|---|---|
| `eco` | 3 | 8 | ≤4 | ~380/h | gentle on the API tier / a busy machine |
| `balanced` *(default)* | 6 | 16 | ≤8 | ~750/h | normal runs |
| `turbo` | 12 | 28 | ≤6 cores → ≤8 | ~1200/h | you have rate-limit headroom and want maximum speed |

The tier also feeds **auto** mode selection: a faster tier raises the estimated
parallel throughput, so `auto` keeps `parallel` over `batch` for larger volumes
(at `turbo`, parallel stays the auto choice up to ~1100 papers; at `balanced`,
batch takes over around ~700). Picking a tier in `settings` hands the individual
knobs below to the tier (clearing any saved overrides).

For fine control, each knob can still be set directly (as a per-run `PEPA_*` env
var, which overrides the tier). Local reading (PDF + spaCy signals + BM25) is
CPU-bound, so in `parallel`/`batch` it runs across **processes** — `LOCAL_WORKERS`
(each process loads its own spaCy model, so lower it if RAM-bound). The LLM stage
has two knobs that move **together** — `PAPER_WORKERS` decides how many papers
fill the pipe, `MAX_CONCURRENCY` decides how wide the pipe is. `LOCAL_BATCH`
bounds how far the reading pipeline runs ahead of the LLM stage, which is what
keeps memory flat on a large run.

| Knob | Default (balanced tier) | What it does | Adjust when… |
|---|---|---|---|
| `LOCAL_WORKERS` | CPU count (≤8; ≤4 on eco) | processes for the local reading stage | many cores idle, or RAM-bound (lower it) |
| `LOCAL_BATCH` | `PAPER_WORKERS`×4 (≥24) | parallel look-ahead window: max papers read **ahead** of the LLM stage (caps peak memory) | memory climbs on huge runs (lower it); cores idle waiting for the LLM (raise it) |
| `PAPER_WORKERS` | 6 | papers running concurrently (parallel mode) | papers sit idle waiting for a free slot |
| `MAX_CONCURRENCY` | 16 | hard cap on total live LLM calls in flight | you have rate-limit headroom and want more papers active |
| `MAX_WORKERS` | 4 | per-paper rundown fan-out (counts against `MAX_CONCURRENCY`) | individual long papers dominate the run |

Set them per-run as environment variables (no `env.yaml` edit needed):

```powershell
$env:PEPA_PAPER_WORKERS = 10; $env:PEPA_MAX_CONCURRENCY = 28; python manage.py summarize
```

Or persist them via **`python manage.py settings`** / `env.yaml`.

> **In `parallel` the real ceiling is your Anthropic tier**, not these numbers —
> sustained throughput is bounded by the account's requests- and tokens-per-minute
> limits. Push `MAX_CONCURRENCY` up until you see repeated 429s, then back off one
> step. 429s are absorbed automatically (the client honours `Retry-After`), so a
> too-high value costs wasted wall-clock, not failed papers. **For large volumes,
> `batch` sidesteps this ceiling entirely** (and halves the bill). `python manage.py
> config` prints the effective values before a run.

## How a paper is processed

1. **Read** — `pypdf` pulls the text layer; image-only pages fall back to local
   OCR (tesseract). The reference list is stripped (it adds tokens, not summary).
2. **Signals** (deterministic, local) — a single spaCy pass yields the recurring
   **noun phrases**, **named entities**, and **subject-verb-object triplets**
   (the raw material of the paper's claims).
3. **Passages** (TREC-style retrieval) — the text is split and scored with
   **BM25** against its own salient terms plus academic cue phrases; the top
   passages and labelled sections (abstract/methods/conclusion) are kept.
4. **Build three documents** —
   - `sum_`: signals + body → the structured brief (long papers send opening +
     retrieved passages instead of the whole text, to stay fast and in-budget).
   - `para_`: paragraph rundown — `llm` (model condenses each paragraph) or
     `extractive` (most central sentence per paragraph, no model call), per the
     `PARA_METHOD` setting. On the `anthropic` backend the `llm` method runs its
     paragraph batches concurrently; tune with `MAX_WORKERS` (1–8, default 4).
   - `quote_`: BM25 candidate passages → model picks the best quotes → a
     deterministic verbatim check drops anything not present in the source.

Steps 1–3 are CPU-bound and identical in every mode; in `parallel`/`batch` they
run across worker **processes** (`LOCAL_WORKERS`) so they parallelise across
cores instead of contending on the GIL. Step 4 is the LLM stage that differs by
mode (live calls vs. the Batches API). To keep memory flat on a large run,
neither mode holds every paper's extracted text at once: `parallel` reads at most
a `LOCAL_BATCH` window of papers ahead of the LLM stage, and `batch` spools each
paper's artifacts to a temp folder and reloads them one at a time while building
the request set (the temp folder is removed when the run ends).

## `sum_` template

Every brief follows the same structure, so papers line up side by side:

```
my-paper.pdf

## <one-line title>

- **Question & context:** ...
- **Empirical context:** country/region, period, people & societies studied, sites, data
- **Literature drawn on:** ...
- **Methods:** ...
- **Arguments:**
  1. ...
  2. ...
- **Key conclusions:** ...
- **Discussion items:** ...
```

## Cost estimates

| | Claude Haiku — live (serial/parallel) | Claude Haiku — batch | Self-hosted Qwen-3B (cloudrun) |
|---|---|---|---|
| Per paper (all 3 docs) | ~$0.03–0.05 | **~50% of live** (Batches API discount) | ~$0.05–0.15 (Cloud Run vCPU-seconds) |
| Speed per paper | ~30–40 s (of which ~87% is the LLM) | asynchronous — usually within ~1h for the whole run (max 24h) | ~3–15 min (CPU) |
| Throughput | papers overlap; ceiling is your Anthropic tier's rate limit | very high once running; no per-call rate fight | serial (single instance) |
| Idle cost | $0 (pay-per-use) | $0 (pay-per-use) | $0 (scales to zero) + image storage |
| Quality | high | high (same model + prompts as live) | modest (3B) |

> Haiku pricing is approximate — verify current rates. Local work (OCR, spaCy,
> BM25) is free. Per-paper time is wall-clock for one paper; `parallel` is faster
> because papers run concurrently, and `batch` trades turnaround latency for ~50%
> cost and the highest throughput on large volumes (see
> [Execution modes](#execution-modes)). Estimates only.
