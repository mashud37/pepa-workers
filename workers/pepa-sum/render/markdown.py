"""Write an output document: <prefix>_<original-name>.md.

Line one is the original PDF filename (so the source is unambiguous when the
file is read on its own); the document body follows.
"""
from pathlib import Path


def write_doc(output_dir, prefix, source_name, body) -> Path:
    out_path = Path(output_dir) / f"{prefix}_{Path(source_name).stem}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(f"{source_name}\n\n{body.strip()}\n", encoding="utf-8")
    return out_path
