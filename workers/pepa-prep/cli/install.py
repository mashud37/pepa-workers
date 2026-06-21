from . import ui


def run() -> None:
    ui.step("Checking dependencies")

    ok = True

    try:
        import fitz  # noqa: F401
        ui.ok("PyMuPDF (fitz)")
    except ImportError:
        ui.error("PyMuPDF missing — run: pip install PyMuPDF")
        ok = False

    try:
        import yaml  # noqa: F401
        ui.ok("PyYAML")
    except ImportError:
        ui.error("PyYAML missing — run: pip install PyYAML")
        ok = False

    try:
        import PIL  # noqa: F401
        import pytesseract  # noqa: F401
        ui.ok("pytesseract + Pillow (OCR available)")
    except ImportError:
        ui.warn("pytesseract / Pillow not installed — OCR route unavailable")
        ui.info("To enable: pip install pytesseract Pillow")
        ui.info("Also install Tesseract: https://tesseract-ocr.github.io/")

    if ok:
        ui.ok("All required dependencies present")
    else:
        raise SystemExit("Install missing packages then re-run.")
