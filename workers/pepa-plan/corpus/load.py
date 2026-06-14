import config


def para_files():
    d = config.corpus_dir()
    if not d.exists():
        raise SystemExit(
            f"CORPUS_DIR not found: {d}\n"
            "Set corpus_dir in secrets.yaml or the PEPAPLAN_CORPUS_DIR env var."
        )
    entries = [{"base": f.stem[5:], "path": f} for f in d.glob("para_*.md")]
    return sorted(entries, key=lambda x: x["base"])


def paper_count():
    d = config.corpus_dir()
    if not d.exists():
        return 0
    return sum(1 for _ in d.glob("para_*.md"))
