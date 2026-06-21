"""Read/write per-paper biblio JSON files (biblio_{stem}.json)."""
import json
from pathlib import Path


def out_path(output_dir: Path | str, stem: str) -> Path:
    return Path(output_dir) / f"biblio_{stem}.json"


def exists(output_dir: Path | str, stem: str) -> bool:
    return out_path(output_dir, stem).exists()


def save(output_dir: Path | str, stem: str, data: dict) -> Path:
    p = out_path(output_dir, stem)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load(output_dir: Path | str, stem: str) -> dict | None:
    p = out_path(output_dir, stem)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def apa_string(title: str, authors: list[dict], year: int | None, journal: str) -> str:
    """Build an APA-style citation string from normalised biblio fields."""
    if not authors:
        author_str = "Unknown"
    else:
        def _fmt(a: dict) -> str:
            given = a.get("given", "")
            initials = "".join(f"{p[0]}." for p in given.split() if p) if given else ""
            return f"{a.get('family', '')}, {initials}".rstrip(", ")

        parts = [_fmt(a) for a in authors[:6]]
        if len(authors) > 6:
            parts.append("et al.")
        author_str = ", ".join(parts[:-1]) + f", & {parts[-1]}" if len(parts) > 1 else parts[0]

    y = f"({year})" if year else "(n.d.)"
    j = f" {journal}." if journal else ""
    return f"{author_str} {y}. {title}.{j}"
