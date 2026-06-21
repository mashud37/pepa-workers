from extract import config as cfg_mod

from . import biblio_cmd, config_cmd, eval_cmd, extract_cmd, install, split_cmd, ui, validate_cmd


def main() -> int:
    cfg = cfg_mod.load()
    while True:
        ui.header("pepa-prep  —  PDF → Markdown")
        ui.info(f"Input:  {cfg['input_folder']}   Output: {cfg['output_folder']}")
        choice = ui.menu("Action", [
            ("Extract PDFs", "categorise and convert PDFs to markdown"),
            ("Validate output", "grade book chapters, quarantine junk, renumber"),
            ("Split chapters", "manually mark chapter boundaries in single-block books"),
            ("Fetch bibliography", "match Zotero + Crossref metadata for pepa-sum papers"),
            ("Fetch bibliography + citations", "also download citation networks from OpenCitations"),
            ("Label for evaluation", "create correctable segmentation tag files"),
            ("Score evaluation", "grade segmentation against corrected tag files"),
            ("Configure", "set input/output paths and options"),
            ("Install / check deps", "verify PyMuPDF, pytesseract, Pillow"),
        ])
        if choice is None:
            return 0
        if choice == 0:
            extract_cmd.run(cfg)
        elif choice == 1:
            validate_cmd.run(cfg)
        elif choice == 2:
            split_cmd.run(cfg)
        elif choice == 3:
            _run_biblio(cfg, cite=False)
        elif choice == 4:
            _run_biblio(cfg, cite=True)
        elif choice == 5:
            eval_cmd.label(cfg)
        elif choice == 6:
            eval_cmd.score(cfg)
        elif choice == 7:
            config_cmd.main(cfg)
            cfg = cfg_mod.load()
        elif choice == 8:
            install.run()
    return 0


def _run_biblio(cfg: dict, cite: bool) -> None:
    zotero = ui.ask("Zotero CSL-JSON file (blank = auto-detect in input/)", None)
    force = ui.confirm("Overwrite existing biblio files?", default_yes=False)
    biblio_cmd.run(cfg, zotero=zotero or None, cite=cite, force=force)
