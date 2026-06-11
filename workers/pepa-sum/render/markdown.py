"""Write one summary file per paper: <original-name>.md.

Line one is the original PDF filename (so the source is unambiguous when the
file is read on its own); the structured Markdown template follows.
"""
from pathlib import Path


def write_summary(output_dir, source_name, summary) -> Path:
    out_path = Path(output_dir) / (Path(source_name).stem + ".md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(f"{source_name}\n\n{summary.strip()}\n", encoding="utf-8")
    return out_path
