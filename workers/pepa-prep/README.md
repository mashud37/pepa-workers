# pepa-prep

Local pipeline that converts a folder of PDFs to clean markdown files. Handles born-digital papers, multi-chapter books (via PDF outline or heading detection), and scanned PDFs (OCR). All processing is local and deterministic — no API calls.

## Layout

```
manage.py              entrypoint — no args = interactive menu
config.yaml            input/output paths and extraction options
requirements.txt       runtime dependencies

cli/                   menu, install check, config and command UI
extract/               extraction engine (categorise, text, chapter, ocr, workers, validate)
evaluate/              segmentation accuracy harness (lines, predict, metrics, review, harness)
input/                 drop PDFs here (gitignored)
output/text/           extracted markdown written here (gitignored)
```

## Setup

```
pip install -r requirements.txt
python manage.py install
```

Drop your PDFs into `input/`, then run the menu or call subcommands directly.

## Menu

```
python manage.py
```

1. Extract PDFs — categorise and convert to markdown
2. Validate output — grade book chapters, quarantine junk, renumber
3. Split chapters — manually mark chapter boundaries in single-block books
4. Fetch bibliography — match Zotero + Crossref metadata for pepa-sum papers
5. Fetch bibliography + citations — also download citation networks from OpenCitations
6. Label for evaluation — create correctable segmentation tag files
7. Score evaluation — grade segmentation against corrected tag files
8. Configure — set input/output paths, workers, OCR options
9. Install / check deps — verify PyMuPDF, pytesseract, Pillow

## Direct subcommands

```
python manage.py extract
python manage.py validate
python manage.py validate --dry-run
python manage.py split
python manage.py split --file "van Dijck_The Culture of Connectivity"
python manage.py label
python manage.py label --input ./gold_pdfs
python manage.py score
python manage.py install
```

## How extraction works

Each PDF is categorised on first pass:

| Route | Condition | Output |
|---|---|---|
| straight | born-digital, ≤ threshold pages | `text_<name>.md` |
| book | born-digital, > threshold pages | `text_<name>_01.md`, `_02.md`, … |
| ocr | no text layer (scanned) | same as above, via Tesseract |

Paragraphs are recovered by geometry (bounding-box gaps and indentation), not by trusting the PDF's raw text blocks. Running headers/footers, page numbers, and reference lists are stripped. Hyphenated line breaks and cross-column sentence splits are stitched.

Books split on the PDF's own outline; if none is present, `Chapter`/`Part` headings — numbered, roman, or spelled-out (`Chapter 7`, `Part IV`, `Chapter One`) — are used. Consecutive headings without enough body text (contents pages, endnotes) are not treated as chapter boundaries. If no boundaries are found at all, the whole book is written as a single file and a warning is shown.

## Validate

After extraction, `validate` grades each book's chapter files against each other by character count, paragraph density, and citation-line share. Files that look like reference lists, orphan fragments, or are nearly empty are moved to `output/_review/` and the survivors are renumbered. A chapter file that still contains two or more `Chapter`/`Part` headings is flagged `multiple-chapters` (a likely missed split) but kept in place. A `report.md` is written to the output folder.

Use `--dry-run` to preview verdicts without moving any files.

## Split

When a book can't be chapter-split automatically (no embedded outline, no recognisable `Chapter`/`Part` headings), extraction writes it as a single file named `text_<stem>_01.md`. The `split` command lets you set the boundaries manually:

```
python manage.py split
```

The command lists every single-block book file. Pick one, confirm, and your editor opens (`$EDITOR` on POSIX, Notepad on Windows). At the top of the file you'll see a short instruction block. Scroll through the text and insert a line containing exactly:

```
<!-- chapter -->
```

at each point where a new chapter should begin. Save the file and close the editor. The command splits on those markers and writes numbered output files — `text_<stem>_01.md`, `_02.md`, and so on — using the same zero-padded numbering scheme as automatic extraction. The original single-block file is replaced.

To split a specific book without going through the interactive list:

```
python manage.py split --file "Baudrillard_Simulations"
```

`--file` accepts the book stem (everything between `text_` and `_01.md` in the filename), or the full path to the file.

## Evaluate segmentation accuracy

`label` and `score` measure how well paragraph, heading, and list boundaries are recovered, so changes to the extractor can be A/B tested instead of eyeballed.

1. **Select** — list the gold-set documents in `data/eval/selection.tsv`, one per line as `filename<TAB>page-spec`. The page-spec is 1-based (`1-4`, `1-3,9`, or `*`/blank for the whole document), so a long book contributes a bounded page window instead of thousands of lines. Header/footer detection still runs over the whole document; only the output is sliced. (Without a manifest, pass `--input FOLDER` to label every PDF in a folder whole.)
2. **Label** — `label` writes a correction file per document to `data/eval/review/<name>.tags.md`: one source line per row, prefixed with the extractor's guess (`⟦HEAD⟧` / `⟦PARA⟧` / `⟦CONT⟧` / `⟦LIST⟧`).
3. **Correct** — open each tag file and fix only the wrong tags. Use `⟦DROP⟧` for any line that should not be in the output at all (a running header/footer that slipped through, page noise, OCR garbage). Do not add, delete, reorder, or edit the line text; correcting is retagging, not retyping. Existing correction files are never overwritten on re-`label`.
4. **Score** — `score` re-runs the predictor and compares it to your corrections, writing `data/eval/report.md` with per-file boundary precision/recall/F1, over- vs under-segmentation counts, dropped-junk-line counts, heading/paragraph/list type accuracy, and the standard Pk and WindowDiff segmentation scores.

The report shows each file twice: the raw geometry/OCR baseline and the same predictor *after* the production continuation merge, so the merge's effect is measured rather than assumed. The selection manifest, streams, and correction files live under `data/eval/` (gitignored).

## Configuration

Edit `config.yaml` or use the Configure menu:

| Key | Default | Description |
|---|---|---|
| `input_folder` | `./input` | Folder of source PDFs |
| `output_folder` | `./output` | Parent output folder; extracted markdown lands in `<output_folder>/text/` |
| `workers` | `4` | Parallel extraction threads |
| `book_page_threshold` | `100` | Pages above this → book route |
| `ocr_dpi` | `300` | Rasterisation DPI for scanned pages |
| `tesseract_cmd` | `""` | Full path to tesseract binary, or blank to use PATH |

Already-extracted files are skipped automatically on re-run.

## OCR dependencies

OCR is optional. To enable it:

```
pip install pytesseract Pillow
```

Install the Tesseract binary separately (see <https://tesseract-ocr.github.io/>). Set `tesseract_cmd` in config if the binary is not on PATH.
