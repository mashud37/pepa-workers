# pepa-review

Works with the literature pepa-sum has summarised: assemble a literature review from an outline,
find works a draft is missing, ask questions of the literature, map how a field clusters into
themes, and look papers up on OpenAlex for their citations. Only the model, embedding and OpenAlex
calls leave the machine.

## How it works

Every summary is embedded into a local index. Each task retrieves the closest works by meaning and
by keyword, and Claude writes the review, explains each gap, or answers the question. The map
groups all works into thematic threads and names each one.

```mermaid
flowchart LR
    SUM[/"pepa-sum summaries"/] --> IDX[("index")]
    IN[/"outline or draft"/] --> TASK["review, gaps,<br/>ask, map"]
    IDX --> TASK
    TASK --> OUT[("output/ reports .md")]
```

## Setup

```powershell
pip install -r requirements.txt
python manage.py install
python manage.py index
```

Add the Anthropic and Gemini keys to `secrets.yaml` before building the index, or name other
providers there with `backend` and `embed_provider`.

## Commands

| Action | Command |
|---|---|
| Build or update the index | `python manage.py index` |
| Assemble a literature review from an outline | `python manage.py review` |
| Find works a draft is missing | `python manage.py gaps` |
| Find the indexed papers closest to a text | `python manage.py similar --input FILE` |
| Ask questions of the literature | `python manage.py explore` |
| Answer one question about the literature | `python manage.py ask --question TEXT` |
| Map the field into themes | `python manage.py map` |
| Map one theme in finer detail | `python manage.py threadmap` |
| Look papers up on OpenAlex for their citations | `python manage.py biblio fetch` |
| Import, export or graph citation data | `python manage.py biblio ingest` (or `export`, `stats`, `network`) |
| Show the configuration | `python manage.py config` |
| Check dependencies | `python manage.py install` |
