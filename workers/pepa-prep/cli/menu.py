from extract import config as cfg_mod

from . import (
    biblio_cmd,
    config_cmd,
    extract_cmd,
    install,
    refine_cmd,
    split_cmd,
    ui,
    validate_cmd,
)


def _actions() -> list:
    actions = [
        ("Extract PDFs", "categorise and convert PDFs to markdown", extract_cmd.run),
        ("Validate output", "grade book chapters, quarantine junk, renumber",
         validate_cmd.run),
        ("Split chapters", "manually correct chapter boundaries in any book",
         split_cmd.run),
        ("Refine chapters", "repair over-/under-split chapter files from text signals",
         _run_refine),
        ("Fetch bibliography", "match Zotero + OpenAlex metadata for pepa-sum papers",
         lambda cfg: _run_biblio(cfg, cite=False)),
        ("Fetch bibliography + citations",
         "also download citation networks from OpenCitations",
         lambda cfg: _run_biblio(cfg, cite=True)),
        ("Configure", "set input/output paths and options", config_cmd.main),
        ("Install / check deps", "verify pypdfium2, pdfplumber, pytesseract, Pillow",
         lambda cfg: install.run()),
    ]
    if cfg_mod.EVALUATION_SHIPPED:
        actions.extend(_evaluation_actions())
    return actions


def _evaluation_actions() -> list:
    from . import eval_cmd
    return [
        ("Label for evaluation", "create correctable segmentation tag files",
         eval_cmd.label),
        ("Score evaluation", "grade segmentation against corrected tag files",
         eval_cmd.score),
        ("Label chapter gold", "create correctable chapter-boundary files for books",
         eval_cmd.label_chapters),
        ("Score chapter detection", "grade chapter boundaries against corrected gold",
         eval_cmd.score_chapters),
        ("Label refine gold", "create correctable unit gold files from chapter files",
         eval_cmd.label_refine),
        ("Score refinement", "grade markdown refinement against corrected gold",
         eval_cmd.score_refine),
    ]


def main() -> int:
    while True:
        cfg = cfg_mod.load()
        ui.header("pepa-prep: PDF → Markdown")
        ui.info(f"Input:  {cfg['input_folder']}   Output: {cfg['output_folder']}")
        actions = _actions()
        choice = ui.menu("Action", [(title, desc) for title, desc, _ in actions])
        if choice is None:
            return 0
        ui.run_action(actions[choice][2], cfg)


def _run_refine(cfg: dict) -> None:
    refine_cmd.run(cfg)
    if ui.confirm("Apply these repairs now?", default_yes=False):
        refine_cmd.run(cfg, apply=True)


def _run_biblio(cfg: dict, cite: bool) -> None:
    zotero = ui.ask("Zotero CSL-JSON file (blank = auto-detect in input/)", None)
    force = ui.confirm("Overwrite existing biblio files?", default_yes=False)
    biblio_cmd.run(cfg, zotero=zotero or None, cite=cite, force=force)
