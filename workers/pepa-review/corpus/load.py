"""Discover and pair sum_/para_/quote_ files in CORPUS_DIR."""
import config


def load_corpus():
    """Return [{base, sum_path, para_path, quote_path}, ...] sorted by base.

    Only entries with a sum_ file are included; para_ and quote_ are optional.
    """
    d = config.corpus_dir()
    if not d.exists():
        raise SystemExit(
            f"CORPUS_DIR not found: {d}\n"
            "Set corpus_dir in secrets.yaml or the PEPAREVIEW_CORPUS_DIR env var."
        )

    sum_files = {}
    para_files = {}
    quote_files = {}
    for f in d.glob("*.md"):
        stem = f.stem
        if stem.startswith("sum_"):
            sum_files[stem[4:]] = f
        elif stem.startswith("para_"):
            para_files[stem[5:]] = f
        elif stem.startswith("quote_"):
            quote_files[stem[6:]] = f

    return [
        {
            "base": base,
            "sum_path": str(path),
            "para_path": str(para_files[base]) if base in para_files else None,
            "quote_path": str(quote_files[base]) if base in quote_files else None,
        }
        for base, path in sorted(sum_files.items())
        if _has_template(path)
    ]


def _has_template(path):
    """True when the sum_ file contains the filled-out markdown template.

    A successful run always produces a ## H2 title header; a plain-text LLM
    error message never does, so this distinguishes real summaries from stubs."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return "\n## " in text or text.startswith("## ")
    except OSError:
        return False


def paper_count():
    d = config.corpus_dir()
    if not d.exists():
        return 0
    return sum(1 for f in d.glob("sum_*.md") if _has_template(f))
