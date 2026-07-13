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
| `python manage.py open <id> [--which text\|sum]` | open a document's file in its default Windows app |
| `python manage.py install` | check dependencies and that source directories are reachable |

A query can filter by field inline: `author:`, `title:`, `context:` (question & context),
`empirical:`, `lit:` (literature drawn on), `methods:`, `arguments:`, `conclusions:` (key
conclusions), `discussion:` (discussion items) — combinable with free text and each other, e.g.
`python manage.py search "lit:foucault author:aaker brand"`. `author:` is also available as an
explicit `--author aaker` flag.

`open <id>` picks the summary file if one exists, else the raw text; pass `--which text` or
`--which sum` to pick explicitly when a document has both. The web UI's Text/Summary columns do
the same via dedicated buttons, since a document can have either or both files.

## Notes

- Chapter-split books (`text_<stem>_01.md`, `_02.md`, ...) are indexed as independent rows, one
  per chapter — not rolled up into a single parent work.
- The search index stores each pepa-sum section (question & context, empirical context, literature
  drawn on, methods, arguments, key conclusions, discussion items) as its own searchable field, so a
  query can target one specifically (see the field-token list above). A pepa-prep-only document (no
  summary yet) is still discoverable by its title.
- Upgrading pepa-reader to a newer index schema clears the existing index automatically (it's fully
  rebuildable from the source files) and reindexes from scratch on the next `index` run — expect
  that to take as long as the original build.
- Indexing is incremental: a file is only re-parsed when its modified time changes, or `--force`
  is passed.
