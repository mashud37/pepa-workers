"""Find ruled tables on a page, render them as markdown, and report the boxes they
occupy so the paragraph pass can skip the lines inside them."""
import pdfplumber

from . import pdf

_MIN_ROWS = 2
_MIN_COLS = 2
_MAX_PAGE_SHARE = 0.8
_MIN_RULES = 3
_MAX_DRAWN = 5000
_CELL_GAP = 1


def _big_enough(rows: list) -> bool:
    columns = max((len(row) for row in rows), default=0)
    return len(rows) >= _MIN_ROWS and columns >= _MIN_COLS


def _covers_page(bbox: tuple, page_area: float) -> bool:
    x0, y0, x1, y1 = bbox
    area = max(x1 - x0, 0.0) * max(y1 - y0, 0.0)
    return area >= _MAX_PAGE_SHARE * page_area


def to_markdown(rows: list) -> str:
    """A table's rows as a markdown table, the first row as its header."""
    width = max(len(row) for row in rows)
    lines = []
    for number, row in enumerate(rows):
        cells = [" ".join((text or "").split()).replace("|", "/") for text in row]
        cells += [""] * (width - len(row))
        lines.append("| " + " | ".join(cells) + " |")
        if number == 0:
            lines.append("|" + "---|" * width)
    return "\n".join(lines)


def page_tables(page) -> list:
    """Ruled tables on one page.

    Args:
        page: a pdfplumber page.

    Returns:
        A list of {"bbox": (x0, y0, x1, y1), "markdown": str}. A table smaller than
        two rows by two columns, or one covering most of the page, is dropped: both
        are how the finder reports ordinary ruled prose rather than a real table.
    """
    page_area = page.width * page.height
    found = []
    for table in page.find_tables():
        rows = table.extract(x_tolerance=_CELL_GAP)
        if not _big_enough(rows) or _covers_page(table.bbox, page_area):
            continue
        found.append({"bbox": tuple(table.bbox), "markdown": to_markdown(rows)})
    return found


def _may_hold_table(rules: dict) -> bool:
    """A ruled table needs a few rules across or down the page; thousands of drawn shapes are a figure."""
    if rules["drawn"] > _MAX_DRAWN:
        return False
    return rules["across"] >= _MIN_RULES or rules["down"] >= _MIN_RULES


def doc_tables(path, doc, page_range) -> list:
    """Tables page by page. pdfplumber is slow, so it reads only the pages whose drawn rules
    could form a table."""
    wanted = [pno for pno in page_range if _may_hold_table(pdf.drawn_rules(doc, pno))]
    found = {}
    if wanted:
        with pdfplumber.open(str(path)) as plumber:
            for pno in wanted:
                found[pno] = page_tables(plumber.pages[pno])
    return [found.get(pno, []) for pno in page_range]


def covering(line: dict, tables: list) -> dict | None:
    """The table whose box contains this line's midpoint, or None."""
    x = (line["x0"] + line["x1"]) / 2
    y = (line["y0"] + line["y1"]) / 2
    for table in tables:
        x0, y0, x1, y1 = table["bbox"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return table
    return None
