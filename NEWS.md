# pepa-workers 0.3.0 (unreleased)

* The console's Library page holds the papers and how far each stage has got. PDFs dropped on it
  are copied in and processed. Papers ticked in its list can be processed alone, skipped in a
  stage, or lose their PDF copy once prepared.
* Mark chapters shows every page of a PDF: tick where each chapter starts and leave out pages such
  as an index. pepa-prep follows the marks.
* pepa-sum's batch mode sends the batch and ends. `pepa-sum batches`, or the Library's Batches
  card, writes the summaries once Anthropic has answered, which can take up to a day.
* pepa-plan's `abstract` labels only papers it has not seen and shows its cost first.
* Every paid step shows its cost at list price before it runs, and stops if the run would cost more
  than was approved.
* pepa-sum reads pepa-prep's prepared text when its own input folder is empty.
* pepa-read indexes prepared text before any paper is summarised.
* Works with version 1 of the anthropic library.

# pepa-workers 0.2.0 (unreleased)

* New worker, `pepa-host`: deploys a model server of your own on Google Cloud Run or Azure
  Container Apps for any worker to use. The console's Models page lists the servers it deployed.
* pepa-prep and pepa-sum read PDFs with pypdfium2 and pdfplumber in place of PyMuPDF and pypdf.
* The console copies PDFs one at a time with progress, lists each file a run is working on, and
  starts no step that lacks a key.

# pepa-workers 0.1.0 (unreleased)

The first release: seven standalone workers in one package.

* The workers, until now separate repositories (`pepa-prep`, `pepa-sum`, `pepa-reader`,
  `pepa-review`, `pepa-plan`, `pepa-draft`, and the unpublished `pepa-console`), are merged into
  this one repository under `workers/`, each with its full history. The separate repositories are
  no longer developed.
* One command per worker: `pepa-prep`, `pepa-sum`, `pepa-read`, `pepa-review`, `pepa-plan`,
  `pepa-draft`, and `pepa-console`. Each opens that worker's own menu, and every menu action is
  also a subcommand.
* `pip install pepa-workers` installs every worker with everything it needs.
* Workers run on their own. Where one can build on another's output, it reads those files from
  disk; none imports another.
* `pepa-console` opens one local web page that drives every worker.
* Every worker keeps its files in one project folder, `pepa-workers` in the home folder unless
  `PEPA_PROJECT` names another. The console's Folders page changes it.
* Every worker takes `--no-input`, so a scripted run never stops to ask a question.
* pepa-sum, pepa-review, pepa-plan and pepa-draft write with Claude or with any service that
  accepts OpenAI's chat format, such as DeepSeek, Kimi, Qwen, or Ollama on the same machine. The
  console's Models page chooses one per worker.
* pepa-review and pepa-draft name their embedding provider in `embed_provider`: Gemini, Ollama, or
  any service that accepts OpenAI's embeddings format. An index or style profile built with one
  model refuses queries from another.
* Developed and tested on Windows; macOS and Linux are untested.
