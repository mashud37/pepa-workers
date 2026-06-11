# pepa-sum

Summarise academic PDFs into **structured, comparable Markdown**. Drop papers
into `input/`, run one command, and get one `output/<name>.md` per paper with a
fixed template — question & context, literature, methods, numbered arguments,
conclusions, and discussion. Single-user and local-first: all the expensive
*reading* (OCR, NLP, passage retrieval) happens on your machine; only a compact,
enriched prompt is sent to a cheap CPU model running on Cloud Run.

## Why this shape

| Concern | Choice | Notes |
|---|---|---|
| Cost | Cloud Run service, scale-to-zero | You pay only for the CPU-seconds spent generating a summary. |
| Where the work happens | Deterministically, locally | OCR, spaCy signals, and TREC-style retrieval run on your machine — no per-token cost. |
| What the model gets | Full text **plus** extracted signals | Noun phrases, named entities, SVO argument-triplets, and the most information-rich passages are handed over to sharpen extraction. |
| Output | One Markdown file per paper, fixed template | Same headings in the same order so papers line up side by side. |

> The task brief said "run on gcloud as a job." A Cloud Run *job* is batch and
> can't answer a laptop synchronously, so this uses a Cloud Run **service** with
> `min-instances=0` — the equivalent near-zero-cost shape that a CLI can call.

## Layout
```
manage.py              entrypoint (no args = menu; subcommands also available)
config.py              effective config: paths, endpoint, text budget
cli/                   command modules (summarize, install, deploy, config, menu) + ui/progress
extract/               local preprocessing: read_pdf (OCR fallback), signals, passages
backends/              prompt builder + Cloud Run summariser client
render/                writes output/<name>.md
serve/                 the Cloud Run service that runs the instruction-tuned model
Dockerfile             service image (model baked in)
gcloud_app.yaml        deployment manifest (resource names, service config)
deploy.sh              two-pass deploy (build, deploy, write BASE_URL)
env.yaml.example       template, safe to commit (env.yaml is gitignored)
input/ output/ data/   runtime folders (gitignored, kept via .gitkeep)
```

## Setup
```
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python manage.py install     # creates env.yaml, generates JOB_TOKEN, checks deps
python manage.py deploy      # builds + deploys the service, writes BASE_URL
python manage.py             # launch menu
```

> Windows-first: `deploy` runs `deploy.ps1` (PowerShell) — no `bash` needed.
> On POSIX machines it runs the `deploy.sh` mirror instead.

> **Scanned PDFs (optional OCR):** image-only pages need
> `pip install pytesseract pdf2image` plus the system tools **tesseract** and
> **poppler**. Without them, born-digital PDFs still work; scanned pages are
> skipped with a warning.

## Menu
```
1) Summarise papers   2) Show config   3) Deploy service   4) Install / setup
```

## Direct subcommands (scriptable)
```
python manage.py summarize [--input <dir>] [--output <dir>] [--force]
python manage.py config
python manage.py deploy
python manage.py install
```
- `--input <dir>` / `--output <dir>` — override the default `input/` / `output/`.
- `--force` — re-summarise papers that already have an output file (the run is
  otherwise resumable: existing summaries are skipped).

## How a paper is processed

1. **Read** — `pypdf` pulls the text layer; image-only pages fall back to local
   OCR (tesseract). The reference list is stripped (it adds tokens, not summary).
2. **Signals** (deterministic, local) — a single spaCy pass yields the recurring
   **noun phrases**, **named entities**, and **subject-verb-object triplets**
   traced through the body (the raw material of the paper's claims).
3. **Passages** (TREC-style retrieval) — the text is split into passages and
   scored with **BM25** against the document's own salient terms plus academic
   cue phrases ("we argue", "our contribution", "results show"); the top
   passages and any labelled sections (abstract/methods/conclusion) are kept.
4. **Summarise** — signals plus the body go to the Cloud Run model. A paper that
   fits the character budget is sent whole; a longer one is sent as its opening
   plus the retrieved passages, so the prompt stays small and CPU stays fast.
5. **Write** — `output/<name>.md`, first line the original filename.

A paper that already has a summary is left alone — interactively you're asked
before overwriting; `--force` overwrites without prompting.

## Output template

Every summary follows the same structure, so papers are directly comparable:

```
my-paper.pdf

## <one-line title>

- **Question & context:** ...
- **Literature drawn on:** ...
- **Methods:** ...
- **Arguments:**
  1. ...
  2. ...
- **Key conclusions:** ...
- **Discussion items:** ...
```

## Cost estimates

- **Cloud Run service** — `min-instances=0`, so it costs nothing while idle; you
  pay CPU/memory-seconds only during generation (CPU inference of a small ~3B
  model takes on the order of a minute per paper, billed at Cloud Run's
  per-second rate). The first call after idle pays a cold start.
- **Artifact Registry** — storage for the (multi-GB) image with the model baked
  in; a few cents per month.
- **Local work** — OCR, spaCy, and BM25 retrieval run on your machine at no cost.

> Estimates only; verify current pricing for your region.
