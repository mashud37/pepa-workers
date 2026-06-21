# pepa-draft

Converts a pepa-review literature review and a pepa-plan paragraph outline into a full academic manuscript draft. The tool assigns plan moves to manuscript sections, retrieves relevant literature passages by embedding similarity, optionally injects author style examples, and calls an LLM to draft each section to a configurable word count target.

## Layout

```
pepa-draft/
  manage.py               Entry point — menu or subcommands
  config.py               Config loader (env → secrets.yaml → defaults)
  secrets.example.yaml    Secrets template (copy to secrets.yaml)
  requirements.txt

  corpus/
    load.py               Discover review + plan files in input/
    parse_review.py       Parse pepa-review output markdown
    parse_plan.py         Parse pepa-plan outline markdown

  index/
    retrieve.py           Cosine retrieval against pepa-review index.json
    style.py              Author style embeddings (build + query)

  draft/
    template.py           Section definitions + word count targets
    sections.py           Plan-item-to-section assignment (load/save)
    section.py            Draft one section with word-count control
    assemble.py           Orchestrate full manuscript
    word_count.py         Accurate word counting
    prompt.py             Prompt templates

  edit/
    check.py              Post-draft filler + long-sentence checks

  backends/
    llm.py                Unified backend router
    anthropic_client.py   Claude via Anthropic API
    vllm_client.py        Cloud Run vLLM proxy client

  cloud/
    serve_vllm.py         Flask proxy in front of vLLM (Cloud Run)
    Dockerfile.vllm       Multi-stage image: vLLM + Flask proxy

  cli/
    menu.py               Interactive menu
    ui.py                 Styled terminal output
    progress.py           StepSpinner
    install.py            Idempotent setup
    draft_cmd.py          draft subcommand
    sections_cmd.py       sections subcommand
    style_cmd.py          style subcommand
    config_cmd.py         config subcommand

  data/                   Runtime data (gitignored): index files, section assignments
  input/                  User-supplied inputs (gitignored): review .md, plan .md, style samples
  output/                 Generated manuscripts (gitignored)
```

## Setup

```
pip install -r requirements.txt
python manage.py install
```

`install` creates `secrets.yaml` from the example template. Fill in your keys:

```yaml
anthropic_api_key: sk-ant-...
gemini_api_key: AIza...        # for embeddings; or set ollama_base_url instead
```

Drop a pepa-review output and a pepa-plan outline into `input/`:

```
input/review_my_topic.md
input/outline_my_topic.md
```

## Menu

```
python manage.py
```

```
  [1] Draft     Write a full manuscript draft
  [2] Sections  Assign plan paragraphs to sections
  [3] Style     Manage author writing samples
  [4] Config    Show effective configuration
  [5] Install   Set up files and check dependencies
  [0] Back
```

## Direct subcommands

```
# Draft a full manuscript (picks files from input/ automatically)
python manage.py draft

# Draft with explicit files and backend
python manage.py draft --review input/review.md --plan input/outline.md --backend anthropic

# Skip retrieval and style injection
python manage.py draft --no-retrieval --no-style

# Assign plan moves to sections interactively
python manage.py sections

# Reset section assignment from move-label defaults
python manage.py sections --reset

# Add an author writing sample for style matching
python manage.py style add --file input/my_paper.txt

# List indexed style samples
python manage.py style list

# Rebuild style index from all .txt/.md files in input/
python manage.py style build

# Show effective configuration
python manage.py config

# Idempotent setup
python manage.py install
```

## Section assignment

On first run, plan moves are assigned to manuscript sections by their move label (e.g. `[HOOK_PROBLEM]` → Introduction, `[FINDING]` → Findings). Run `python manage.py sections` to move items between sections before drafting. The assignment is saved to `data/sections.json` and reused on subsequent drafts.

## Author style matching

Index one or more of your own papers or writing samples. pepa-draft retrieves the most similar paragraphs to each section's content and injects them as few-shot style examples in the prompt. This preserves your voice across a machine-generated draft.

```
python manage.py style add --file input/my_previous_paper.txt
```

## vLLM backend

For bulk drafting without per-token API costs, deploy `cloud/Dockerfile.vllm` to Cloud Run with a GPU instance. Set `vllm_base_url` and `vllm_token` in `secrets.yaml`, then pass `--backend vllm`.

The proxy exposes `/healthz` immediately on startup so Cloud Run's readiness probe passes while the model loads. `/generate` returns 503 until vLLM is ready.

## Cost

Drafting a full manuscript (~8 250 words across six sections) makes approximately 6–12 Anthropic API calls depending on word-count expansion passes. At claude-opus-4-8 pricing, a single full draft costs roughly $0.50–$2.00 depending on context size (style examples, retrieved passages). Use `--backend vllm` to avoid per-call costs after the Cloud Run instance is warm.

*All cost figures are estimates only. Actual costs depend on prompt length, retrieved context, and current API pricing.*
