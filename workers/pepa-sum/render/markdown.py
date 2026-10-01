"""Write an output document named <prefix>_<paper-stem>.md, with the
original source filename as line one so the file is unambiguous read on
its own.
"""
from pathlib import Path

# pepa-prep emits its extracted markdown as text_<stem>.md (and text_<stem>_NN.md
# per chapter). Stripping that prefix off a text input makes a preprocessed paper
# produce sum_<stem>.md (identical to summarising the PDF directly) instead of
# sum_text_<stem>.md.
_PREP_PREFIX = "text_"
_PREP_SUFFIXES = (".md", ".markdown", ".txt")


def paper_stem(source_name) -> str:
    """The paper's identity for output names and dedup: the file stem, with
    pepa-prep's `text_` prefix removed for a markdown/text source so both input
    formats of one paper map to the same sum_/para_/quote_ names."""
    p = Path(source_name)
    stem = p.stem
    if p.suffix.lower() in _PREP_SUFFIXES and stem.startswith(_PREP_PREFIX):
        return stem[len(_PREP_PREFIX):]
    return stem


def write_doc(output_dir, prefix, source_name, body) -> Path:
    out_path = Path(output_dir) / f"{prefix}_{paper_stem(source_name)}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(f"{source_name}\n\n{body.strip()}\n", encoding="utf-8")
    return out_path
