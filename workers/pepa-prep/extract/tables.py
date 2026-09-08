"""Find ruled tables on a page, render them as markdown, and report the boxes they
occupy so the paragraph pass can skip the lines inside them."""
_MIN_ROWS = 2
_MIN_COLS = 2
_MAX_PAGE_SHARE = 0.8


def _big_enough(table) -> bool:
    return table.row_count >= _MIN_ROWS and table.col_count >= _MIN_COLS


def _covers_page(table, page_area: float) -> bool:
    x0, y0, x1, y1 = table.bbox
    area = max(x1 - x0, 0.0) * max(y1 - y0, 0.0)
    return area >= _MAX_PAGE_SHARE * page_area


def page_tables(page) -> list:
    """Ruled tables on one page.

    Args:
        page: an open PyMuPDF page.

    Returns:
        A list of {"bbox": (x0, y0, x1, y1), "markdown": str}. A table smaller than
        two rows by two columns, or one covering most of the page, is dropped: both
        are how the finder reports ordinary ruled prose rather than a real table.
    """
    page_area = page.rect.width * page.rect.height
    found = []
    for table in page.find_tables().tables:
        if not _big_enough(table) or _covers_page(table, page_area):
            continue
        markdown = table.to_markdown().strip()
        if markdown:
            found.append({"bbox": tuple(table.bbox), "markdown": markdown})
    return found


def doc_tables(doc, page_range) -> list:
    return [page_tables(doc[pno]) for pno in page_range]


def covering(line: dict, tables: list) -> dict | None:
    """The table whose box contains this line's midpoint, or None."""
    x = (line["x0"] + line["x1"]) / 2
    y = (line["y0"] + line["y1"]) / 2
    for table in tables:
        x0, y0, x1, y1 = table["bbox"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return table
    return None
