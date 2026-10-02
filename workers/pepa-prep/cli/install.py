from pathlib import Path

from extract import config

from . import ui


def run() -> None:
    ui.step("Setting up folders")
    cfg = config.load()
    for folder in (cfg["input_folder"], cfg["output_folder"], config.DATA_ROOT / "data"):
        Path(folder).mkdir(parents=True, exist_ok=True)
    ui.ok(f"Folders ready in {config.DATA_ROOT}")

    ui.step("Checking dependencies")

    ok = True

    try:
        import fitz  # noqa: F401
        ui.ok("PyMuPDF (fitz)")
    except ImportError:
        ui.error("PyMuPDF missing, run: pip install PyMuPDF")
        ok = False

    try:
        import yaml  # noqa: F401
        ui.ok("PyYAML")
    except ImportError:
        ui.error("PyYAML missing, run: pip install PyYAML")
        ok = False

    try:
        import PIL  # noqa: F401
        import pytesseract
        ui.ok("pytesseract + Pillow")
    except ImportError:
        ui.error("pytesseract / Pillow missing, run: pip install pytesseract Pillow")
        ok = False
    else:
        found = config.tesseract_path(cfg)
        if found:
            pytesseract.pytesseract.tesseract_cmd = found
        try:
            pytesseract.get_tesseract_version()
            ui.ok("Tesseract (scanned PDFs can be read)")
        except pytesseract.TesseractNotFoundError:
            ui.warn("Tesseract not found, so scanned PDFs are skipped")
            ui.info("Windows: winget install UB-Mannheim.TesseractOCR")
            ui.info("Other systems: https://tesseract-ocr.github.io/tessdoc/Installation.html")

    if ok:
        ui.ok("All required dependencies present")
    else:
        raise SystemExit("Install missing packages then re-run.")
