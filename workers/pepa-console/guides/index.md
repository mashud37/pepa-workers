# Getting started

pepa is a set of workers for academic reading and writing. Each one does one job: prepare PDFs,
summarise papers, search what has been read, review a literature, outline an argument, or draft a
section to test an idea. Each works on its own, so use only the ones you need.

## Install

With Python 3.10 or newer installed, open PowerShell (a terminal on macOS or Linux) and run:

```
pip install pepa-workers
pepa-console
```

The console opens in your browser. Closing the PowerShell window stops it, and `pepa-console`
starts it again.

## Where your files live

Every worker keeps its files in one project folder, `pepa-workers` in your home folder. The
**Folders** page shows each worker's folders and changes any of them, including the project
folder itself. A folder of papers you already have can be linked there; pepa only ever reads it.

## Keys

Summaries, reviews, outlines and drafts call a language model and need an API key; preparing
PDFs and searching do not. Add a key once on the **Keys** page and every worker that needs it gets
it. Steps marked **API costs** are billed to that key and show their cost before they run.

## Models

Every worker writes with Anthropic's Claude unless the **Models** page names another model:
DeepSeek, Kimi, Qwen, or one running on this computer. [Models](models.md) explains the choices.

## A first run

1. On **Library**, drop some PDFs on the page, or press **Copy PDFs in** and choose them.
2. **Process papers** opens for the new papers. Press **Run**: they are prepared, summarised and
   indexed for search, and each paper shows its progress.
3. Press **Read** beside a finished paper to read its brief, its paragraph rundown and its quotes.
4. **Search** finds papers by author, title, or any word in their briefs.

## The workers

| Worker | What it does |
|---|---|
| [pepa-prep](pepa-prep.md) | Turns PDFs into clean text |
| [pepa-sum](pepa-sum.md) | Summarises each paper: a brief, a paragraph rundown and checked quotes |
| [pepa-read](pepa-read.md) | Searches everything prepared and summarised; keeps literature lists |
| [pepa-review](pepa-review.md) | Writes a literature review, finds gaps in a draft, maps a field |
| [pepa-plan](pepa-plan.md) | Outlines a paper idea paragraph by paragraph |
| [pepa-draft](pepa-draft.md) | Drafts sections from an outline and a review |
