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
python manage.py summarize [--input <dir>] [--output <dir>] [--force]
python manage.py settings
python manage.py config
python manage.py install
python manage.py deploy
```
- `--input <dir>` / `--output <dir>` — override the default `input/` / `output/`.
- `--force` — reprocess papers already done (otherwise resumable: a paper with a
  `sum_` file is skipped, or — interactively — you're asked before overwriting).

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
     `PARA_METHOD` setting.
   - `quote_`: BM25 candidate passages → model picks the best quotes → a
     deterministic verbatim check drops anything not present in the source.

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

| | Claude Haiku (default) | Self-hosted Qwen-3B (cloudrun) |
|---|---|---|
| Per paper (all 3 docs) | ~$0.03–0.05 | ~$0.05–0.15 (Cloud Run vCPU-seconds) |
| Speed per paper | ~10–30 s | ~3–15 min (CPU) |
| Idle cost | $0 (pay-per-use) | $0 (scales to zero) + image storage |
| Quality | high | modest (3B) |

> Haiku pricing is approximate — verify current rates. Local work (OCR, spaCy,
> BM25) is free. Estimates only.
