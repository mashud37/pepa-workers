"""Manual chapter splitting for single-block book files.

Workflow:
1. find_single_blocks(out_dir) — returns stems that have exactly one numbered file.
2. prepare_editor_file(path, tmp_path) — writes the book content with a header comment
   explaining the marker syntax, then opens it in $EDITOR / notepad.
3. apply_markers(source_path, out_dir) — reads the (now-edited) source, splits on
   <!-- chapter --> markers, and writes numbered output files, replacing the original.
"""
import os
import re
import subprocess
from pathlib import Path

_CHAPTER_FILE_RE = re.compile(r"^text_(.+)_(\d+)\.md$")
_MARKER = "<!-- chapter -->"
_MARKER_RE = re.compile(r"^\s*<!--\s*chapter\s*-->\s*$", re.IGNORECASE)

_HEADER = """\
<!-- ================================================================
  CHAPTER SPLIT EDITOR
  Add a line containing exactly:  <!-- chapter -->
  at each point where a new chapter should begin.
  Save the file and close the editor when done.
  Do NOT edit the book text — only add or remove marker lines.
================================================================ -->
"""


def find_single_blocks(out_dir: Path) -> dict[str, Path]:
    """Return {stem: path} for books with exactly one numbered output file."""
    groups: dict[str, list] = {}
    for p in sorted(out_dir.glob("text_*_*.md")):
        m = _CHAPTER_FILE_RE.match(p.name)
        if m:
            groups.setdefault(m.group(1), []).append(p)
    return {stem: files[0] for stem, files in groups.items() if len(files) == 1}


def prepare_editor_file(source: Path, tmp_path: Path) -> None:
    """Write source content prefixed with editor instructions to tmp_path."""
    content = source.read_text(encoding="utf-8")
    tmp_path.write_text(_HEADER + "\n" + content, encoding="utf-8")


def open_editor(path: Path) -> None:
    """Open path in $EDITOR, falling back to notepad on Windows or nano on POSIX."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        editor = "notepad" if os.name == "nt" else "nano"
    subprocess.run([editor, str(path)], check=True)


def apply_markers(tmp_path: Path, stem: str, out_dir: Path) -> tuple[int, list[str]]:
    """Parse marker lines from tmp_path, split, write numbered files; return (count, warnings).

    Replaces the existing single-block file.  Original is removed only if
    splitting succeeds and produces at least 2 chapters.
    """
    raw = tmp_path.read_text(encoding="utf-8")

    # Strip the header comment block we prepended
    if raw.startswith("<!--"):
        end = raw.find("-->\n")
        if end != -1:
            raw = raw[end + 4:]

    lines = raw.splitlines(keepends=True)

    # Split into chunks at each marker line
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _MARKER_RE.match(line):
            if current:
                chunks.append(current)
            current = []
        else:
            current.append(line)
    if current:
        chunks.append(current)

    # Drop leading/trailing whitespace-only chunks
    chunks = [c for c in chunks if "".join(c).strip()]

    warnings: list[str] = []
    if len(chunks) < 2:
        warnings.append(
            "no <!-- chapter --> markers found — file unchanged"
        )
        return 0, warnings

    # Remove all existing numbered files for this stem before writing new ones
    for existing in sorted(out_dir.glob(f"text_{stem}_*.md")):
        existing.unlink()

    width = max(2, len(str(len(chunks))))
    for i, chunk in enumerate(chunks, 1):
        text = "".join(chunk).strip() + "\n"
        (out_dir / f"text_{stem}_{i:0{width}d}.md").write_text(text, encoding="utf-8")

    return len(chunks), warnings
