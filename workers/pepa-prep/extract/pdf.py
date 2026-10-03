"""Read PDFs through pypdfium2: page text, positioned lines with font size and weight, bookmarks, page labels and page images.
Every other extract module reads PDFs through here.
"""
import ctypes
import threading
from collections import Counter

import pypdfium2 as pdfium
import pypdfium2.raw as raw

# PDFium allows one call at a time in a process, even on different documents.
LOCK = threading.Lock()
NEW_LINE = ("\n", "\r")
LINE_END_HYPHEN = "\x02"
BOLD_WEIGHT = 600
BOLD_SHARE = 0.6
FONT_NAME_BYTES = 256
NEW_BLOCK_GAP = 1.0
NEW_COLUMN_SHIFT = 0.3
RULE_THICKNESS = 3
RULE_ACROSS_SHARE = 0.1
RULE_DOWN_SHARE = 0.02


# ---- Documents ----

def open_pdf(path):
    with LOCK:
        return pdfium.PdfDocument(str(path))


def close_pdf(doc):
    with LOCK:
        doc.close()


def page_count(doc):
    return len(doc)


def page_size(doc, index):
    with LOCK:
        return doc[index].get_size()


def page_text(doc, index):
    with LOCK:
        textpage = doc[index].get_textpage()
        text = textpage.get_text_range()
        textpage.close()
    return text


def drawn_rules(doc, index):
    """What is drawn on a page: every line and box, and how many are thin rules running across
    or down it, the strokes a ruled table is made of.

    Returns:
        {"drawn", "across", "down"}.
    """
    counts = {"drawn": 0, "across": 0, "down": 0}
    with LOCK:
        page = doc[index]
        width, height = page.get_size()
        for drawing in page.get_objects(filter=[raw.FPDF_PAGEOBJ_PATH], max_depth=2):
            left, bottom, right, top = drawing.get_bounds()
            counts["drawn"] += 1
            if top - bottom < RULE_THICKNESS and right - left > RULE_ACROSS_SHARE * width:
                counts["across"] += 1
            if right - left < RULE_THICKNESS and top - bottom > RULE_DOWN_SHARE * height:
                counts["down"] += 1
    return counts


def outline(doc):
    """The PDF's bookmarks as [level, title, page], with levels from 1 and pages from 1; -1 when a bookmark has no page."""
    entries = []
    with LOCK:
        for item in doc.get_toc():
            destination = item.get_dest()
            page = -1
            if destination is not None and destination.get_index() is not None:
                page = destination.get_index() + 1
            entries.append([item.level + 1, item.get_title(), page])
    return entries


def page_with_label(doc, label):
    """The 0-based page whose printed label is this, or None."""
    with LOCK:
        for index in range(len(doc)):
            if doc.get_page_label(index) == label:
                return index
    return None


def page_image(doc, index, dpi):
    """One page as a greyscale image for OCR."""
    with LOCK:
        bitmap = doc[index].render(scale=dpi / 72, grayscale=True)
        image = bitmap.to_pil()
    return image.convert("L")


# ---- Characters into lines ----

def font_name(handle, index, buffer):
    flags = ctypes.c_int()
    length = raw.FPDFText_GetFontInfo(handle, index, buffer, len(buffer), ctypes.byref(flags))
    if length <= 1:
        return ""
    return bytes(buffer[:length - 1]).decode("utf-8", "ignore")


def font_size(handle, index, matrix):
    """The size the character is drawn at: its font size scaled by its text matrix."""
    raw.FPDFText_GetMatrix(handle, index, ctypes.byref(matrix))
    scale = abs(matrix.a * matrix.d - matrix.b * matrix.c) ** 0.5
    return raw.FPDFText_GetFontSize(handle, index) * scale


def page_characters(doc, index):
    """Every character on a page in PDFium's reading order, with "breaks" marking where a line
    ends. A hyphen PDFium marks at a line's end also ends the line, so the paragraph pass
    decides whether to keep it."""
    chars = []
    with LOCK:
        page = doc[index]
        height = page.get_size()[1]
        textpage = page.get_textpage()
        handle = textpage.raw
        buffer = (ctypes.c_ubyte * FONT_NAME_BYTES)()
        matrix = raw.FS_MATRIX()
        for position in range(textpage.count_chars()):
            character = chr(raw.FPDFText_GetUnicode(handle, position))
            if character in NEW_LINE:
                chars.append({"breaks": True})
                continue
            left, bottom, right, top = textpage.get_charbox(position)
            font = font_name(handle, position, buffer)
            chars.append({
                "char": "-" if character == LINE_END_HYPHEN else character,
                "box": (left, height - top, right, height - bottom),
                "size": font_size(handle, position, matrix),
                "bold": raw.FPDFText_GetFontWeight(handle, position) >= BOLD_WEIGHT or "bold" in font.lower(),
                "breaks": character == LINE_END_HYPHEN,
            })
        textpage.close()
    return chars


def split_lines(chars):
    """The characters cut into lines at each break; a break that is itself a character stays at its line's end."""
    lines = []
    current = []
    for char in chars:
        if "char" in char:
            current.append(char)
        if char["breaks"] and current:
            lines.append(current)
            current = []
    if current:
        lines.append(current)
    return lines


def line_from(chars):
    """One line's text, box, most common size (to the half point), and whether most of it is bold."""
    text = "".join(char["char"] for char in chars)
    text = text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
    inked = [char for char in chars if char["char"].strip()]
    if not inked:
        return None
    sizes = Counter(round(char["size"] * 2) / 2 for char in inked)
    bold = sum(1 for char in inked if char["bold"])
    return {
        "text": text,
        "x0": min(char["box"][0] for char in inked),
        "y0": min(char["box"][1] for char in inked),
        "x1": max(char["box"][2] for char in inked),
        "y1": max(char["box"][3] for char in inked),
        "size": sizes.most_common(1)[0][0],
        "bold": bold / len(inked) > BOLD_SHARE,
    }


def starts_block(previous, line, page_width):
    """A new block starts after a gap taller than a line, or where the text jumps to another column."""
    height = max(previous["y1"] - previous["y0"], 1.0)
    gap = line["y0"] - previous["y1"]
    if gap > NEW_BLOCK_GAP * height or gap < -height:
        return True
    overlap = min(previous["x1"], line["x1"]) - max(previous["x0"], line["x0"])
    return overlap <= 0 and abs(line["x0"] - previous["x0"]) > NEW_COLUMN_SHIFT * page_width


def page_lines(doc, index):
    """A page's lines grouped into blocks, each line as {"text", "x0", "y0", "x1", "y1", "size", "bold"}."""
    page_width = page_size(doc, index)[0]
    blocks = []
    previous = None
    for chars in split_lines(page_characters(doc, index)):
        line = line_from(chars)
        if line is None or not line["text"].strip():
            continue
        if previous is None or starts_block(previous, line, page_width):
            blocks.append([])
        blocks[-1].append(line)
        previous = line
    return blocks
