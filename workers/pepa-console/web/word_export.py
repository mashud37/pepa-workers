"""Turn a Markdown text into a Word document: headings, paragraphs, lists, bold and italics.
Reviews, outlines and drafts download through it, ready to edit in Word.
"""
import io
import re

HEADING_LEVELS = {
    "# ": 1,
    "## ": 2,
    "### ": 3,
    "#### ": 4,
}
BULLET_MARKS = ("- ", "* ")
NUMBERED_LINE = re.compile(r"^\d+[.)]\s+")
EMPHASIS = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")


def add_runs(paragraph, text):
    """Add the text to the paragraph, setting **bold** and *italic* spans in their style."""
    for piece in EMPHASIS.split(text):
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            paragraph.add_run(piece[2:-2]).bold = True
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            paragraph.add_run(piece[1:-1]).italic = True
        elif piece:
            paragraph.add_run(piece)


def add_line(document, line):
    """Add one Markdown line as a heading, list item or paragraph."""
    for mark, level in HEADING_LEVELS.items():
        if line.startswith(mark):
            document.add_heading(line[len(mark):].strip(), level=level)
            return
    if line.startswith(BULLET_MARKS):
        add_runs(document.add_paragraph(style="List Bullet"), line[2:].strip())
        return
    if NUMBERED_LINE.match(line):
        add_runs(document.add_paragraph(style="List Number"), NUMBERED_LINE.sub("", line).strip())
        return
    add_runs(document.add_paragraph(), line.strip())


def word_bytes(title, markdown_text):
    """The text as a .docx file's bytes, with the title in its document properties."""
    import docx
    document = docx.Document()
    document.core_properties.title = title
    paragraph_lines = []
    for line in markdown_text.splitlines():
        if line.strip() in ["", "---"]:
            if paragraph_lines:
                add_line(document, " ".join(paragraph_lines))
                paragraph_lines = []
            continue
        if line.startswith("#") or line.startswith(BULLET_MARKS) or NUMBERED_LINE.match(line):
            if paragraph_lines:
                add_line(document, " ".join(paragraph_lines))
                paragraph_lines = []
            add_line(document, line)
            continue
        paragraph_lines.append(line.strip())
    if paragraph_lines:
        add_line(document, " ".join(paragraph_lines))
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
