"""OCR path: rasterise PDF pages with PyMuPDF then run Tesseract."""
import os
from concurrent.futures import ThreadPoolExecutor


def _ocr_image(img):  # lint-style: ignore FN004
    import pytesseract
    raw = pytesseract.image_to_string(img)
    return raw.strip().encode("utf-8", "surrogatepass").decode("utf-8", "ignore")


def ocr_pages(path, fitz, cfg: dict, progress=None) -> list:
    """Rasterise to grayscale and OCR pages in parallel, bounded to worker count.

    Rendering stays on this thread (a fitz.Document is not thread-safe); only the
    Tesseract calls fan out. Memory is capped at one worker-sized batch of images.

    Args:
        progress: optional ``callable(done, total)`` invoked after each batch so a
            caller can show page-level progress on a long-running file.
    """
    import pytesseract
    from PIL import Image

    tesseract_cmd = cfg.get("tesseract_cmd", "")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")

    dpi = cfg.get("ocr_dpi", 300)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    n_workers = max(1, cfg.get("workers", 4))

    texts: list = []
    with fitz.open(str(path)) as doc, ThreadPoolExecutor(max_workers=n_workers) as pool:
        total = doc.page_count
        if progress:
            progress(0, total)
        for start in range(0, total, n_workers):
            batch = []
            for n in range(start, min(start + n_workers, total)):
                pix = doc[n].get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
                batch.append(Image.frombytes("L", [pix.width, pix.height], pix.samples))
            texts.extend(pool.map(_ocr_image, batch))
            if progress:
                progress(len(texts), total)
    return texts
