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
* Developed and tested on Windows; macOS and Linux are untested.
