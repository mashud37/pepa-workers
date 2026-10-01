# pepa-workers 0.1.0 (unreleased)

The first release: seven standalone workers in one package.

* One command per worker: `pepa-prep`, `pepa-sum`, `pepa-read`, `pepa-review`, `pepa-plan`,
  `pepa-draft`, and `pepa-console`. Each opens that worker's own menu, and every menu action is
  also a subcommand.
* Each worker installs its own dependencies through an extra of the same name (`prep`, `sum`,
  `read`, `review`, `plan`, `draft`, `console`), or all of them through `all`.
* Workers run on their own. Where one can build on another's output, it reads those files from
  disk; none imports another.
* `pepa-console web` drives every worker from one local web page.
* Developed and tested on Windows; macOS and Linux are untested.
