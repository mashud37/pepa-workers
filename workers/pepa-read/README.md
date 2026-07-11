# pepa-reader

Fast keyword search over the pepa-prep extracted-text and pepa-sum summary markdown files, with
one-click open in the file's default Windows app. Read-only: it never writes to pepa-prep or
pepa-sum output, makes no LLM or network calls, and runs entirely on `127.0.0.1` — nothing leaves
the machine. Solves the "Explorer search over thousands of markdown files is too slow" problem
with a SQLite FTS5 (BM25) index and a small local Flask UI.

## Layout

```
manage.py              entrypoint - bare invocation serves the web UI
config.py               source dirs, db path, port - env-var overridable
cli/
  ui.py                  styled terminal output (step/ok/warn/info/error)
index/
  scan.py                 resolve pepa-prep/pepa-sum filenames to a (stem, chapter) identity
  build.py                 scan + incremental upsert into SQLite, with progress
  schema.py                 documents table + documents_fts (FTS5) virtual table
search/
  query.py                  BM25 query, shared by `manage.py search` and /api/search
web/
  app.py                     Flask app factory + dev-server runner
  routes.py                   /, /api/search, /view/<id>, /open/<id>
  templates/search.html        search bar + results table shell
  static/search.js              debounced fetch, renders results, no framework
  static/style.css               minimal light/dark styling
data/                    reader.db lives here (gitignored)
```

## Setup

```
pip install -r requirements.txt
python manage.py install
```

Add `pip install markdown` for nicer rendering of the `/view/<id>` page (optional — falls back to
plain text if not installed). `install` checks dependencies and that the pepa-prep/pepa-sum source
directories are reachable.

By default pepa-reader looks for source files at `../pepa-prep/output/text` and `../pepa-sum/output`
relative to its own folder (i.e. as a sibling of those repos). Override with environment variables
if your corpus lives elsewhere:

```
PEPA_READER_TEXT_DIR=D:\corpus\text
PEPA_READER_SUM_DIR=D:\corpus\sum
PEPA_READER_DB_PATH=D:\corpus\reader.db
PEPA_READER_PORT=5151
```

Build the index once before searching:

```
python manage.py index
```

## Usage

Running `python manage.py` with no arguments builds the index if it doesn't exist yet, starts the
local web UI, and opens it in your browser. Ctrl-C stops the server. In a non-interactive shell
(piped/scripted), it instead prints a pointer to the commands below and exits.

| Command | Behavior |
|---|---|
| `python manage.py` | (TTY) ensure index exists, serve, open browser, block until Ctrl-C |
| `python manage.py index [--force]` | scan pepa-prep + pepa-sum and (re)build the index |
| `python manage.py search "query" [--author X] [--limit N] [--json]` | one-shot search to stdout |
| `python manage.py serve [--port N] [--no-browser]` | explicit, scriptable form of the bare action |
| `python manage.py open <id>` | open a document's file in its default Windows app |
| `python manage.py install` | check dependencies and that source directories are reachable |

A query can filter by author inline, e.g. `python manage.py search "author:aaker brand"`, or via
`--author aaker`.

## Notes

- Chapter-split books (`text_<stem>_01.md`, `_02.md`, ...) are indexed as independent rows, one
  per chapter — not rolled up into a single parent work.
- The search index stores the curated pepa-sum sections as the searchable body when a summary
  exists; a pepa-prep-only document (no summary yet) is still discoverable by its title.
- Indexing is incremental: a file is only re-parsed when its modified time changes, or `--force`
  is passed.
