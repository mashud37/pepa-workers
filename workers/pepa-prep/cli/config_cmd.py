from extract import config as cfg_mod

from . import ui


def _show(cfg: dict) -> None:
    ui.info(f"Input folder:       {cfg['input_folder']}")
    ui.info(f"Output folder:      {cfg['output_folder']}")
    ui.info(f"Workers:            {cfg['workers']}")
    ui.info(f"Book page threshold:{cfg['book_page_threshold']}")
    ui.info(f"Max chapters:       {cfg['max_chapters']}")
    ui.info(f"OCR DPI:            {cfg['ocr_dpi']}")
    tesseract = cfg.get("tesseract_cmd") or "(from PATH)"
    ui.info(f"Tesseract path:     {tesseract}")


def main(cfg: dict) -> None:
    while True:
        ui.header("Configure")
        _show(cfg)
        choice = ui.menu("Configure", [
            ("Input folder", f"current: {cfg['input_folder']}"),
            ("Output folder", f"current: {cfg['output_folder']}"),
            ("Workers", f"current: {cfg['workers']}"),
            ("Advanced", "book threshold, OCR DPI, Tesseract path"),
        ])
        if choice is None:
            return

        if choice == 0:
            v = ui.ask("Input folder", cfg["input_folder"])
            if v:
                cfg = {**cfg, "input_folder": v}
                cfg_mod.save(cfg)
                ui.ok("Saved")

        elif choice == 1:
            v = ui.ask("Output folder", cfg["output_folder"])
            if v:
                cfg = {**cfg, "output_folder": v}
                cfg_mod.save(cfg)
                ui.ok("Saved")

        elif choice == 2:
            v = ui.ask("Workers (parallel threads)", str(cfg["workers"]))
            if v and v.isdigit() and int(v) >= 1:
                cfg = {**cfg, "workers": int(v)}
                cfg_mod.save(cfg)
                ui.ok("Saved")
            elif v:
                ui.warn("Must be a positive integer")

        elif choice == 3:
            cfg = _advanced(cfg)


def _ask_int(cfg: dict, key: str, prompt: str, minimum: int, err: str) -> dict:
    v = ui.ask(prompt, str(cfg[key]))
    if v and v.isdigit() and int(v) >= minimum:
        cfg = {**cfg, key: int(v)}
        cfg_mod.save(cfg)
        ui.ok("Saved")
    elif v:
        ui.warn(err)
    return cfg


def _advanced(cfg: dict) -> dict:
    while True:
        ui.header("Advanced")
        choice = ui.menu("Advanced options", [
            ("Book page threshold", f"current: {cfg['book_page_threshold']}  (PDFs over this → book route)"),
            ("Max chapters", f"current: {cfg['max_chapters']}  (more than this → wrote one file, flagged)"),
            ("OCR DPI", f"current: {cfg['ocr_dpi']}  (higher = slower but better)"),
            ("Tesseract path", f"current: {cfg.get('tesseract_cmd') or '(from PATH)'}"),
        ])
        if choice is None:
            return cfg
        if choice == 0:
            cfg = _ask_int(cfg, "book_page_threshold", "Book page threshold", 1, "Must be a positive integer")
        elif choice == 1:
            cfg = _ask_int(cfg, "max_chapters", "Max chapters before a book becomes one file", 2,
                     "Must be an integer ≥ 2")
        elif choice == 2:
            cfg = _ask_int(cfg, "ocr_dpi", "OCR DPI", 72, "Must be ≥ 72")
        elif choice == 3:
            v = ui.ask("Tesseract executable path (blank = use PATH)", cfg.get("tesseract_cmd", ""))
            cfg = {**cfg, "tesseract_cmd": v or ""}
            cfg_mod.save(cfg)
            ui.ok("Saved")
