"""OCR path: rasterise PDF pages with pypdfium2 then run Tesseract."""
import os
from concurrent.futures import ThreadPoolExecutor

from . import pdf


def _ocr_image(img):  # lint-style: ignore FN004
    import pytesseract
    raw = pytesseract.image_to_string(img)
    return raw.strip().encode("utf-8", "surrogatepass").decode("utf-8", "ignore")


def ocr_pages(path, cfg: dict, progress=None) -> list:
    """Rasterise to grayscale and OCR pages in parallel, bounded to worker count.

    Rendering stays on this thread (PDFium is not thread-safe); only the
    Tesseract calls fan out. Memory is capped at one worker-sized batch of images.

    Args:
        progress: optional ``callable(done, total)`` invoked after each batch so a
            caller can show page-level progress on a long-running file.
    """
    import pytesseract

    from extract.config import tesseract_path
    found = tesseract_path(cfg)
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")

    dpi = cfg.get("ocr_dpi", 300)
    n_workers = max(1, cfg.get("workers", 4))

    texts: list = []
    doc = pdf.open_pdf(path)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        total = pdf.page_count(doc)
        if progress:
            progress(0, total)
        for start in range(0, total, n_workers):
            batch = []
            for n in range(start, min(start + n_workers, total)):
                batch.append(pdf.page_image(doc, n, dpi))
            texts.extend(pool.map(_ocr_image, batch))
            if progress:
                progress(len(texts), total)
    pdf.close_pdf(doc)
    return texts
