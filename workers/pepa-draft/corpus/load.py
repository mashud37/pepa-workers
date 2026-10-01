"""Discover review and plan files in input/ or at a given path."""
from pathlib import Path

import config


def find_files(pattern: str, input_dir: Path = None) -> list[Path]:
    """Return files matching pattern in input_dir, newest first."""
    d = input_dir or config.INPUT_DIR
    return sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)


def pick_review(path: str = None) -> Path:
    """Return a review file path. Prompt user to pick if path is None."""
    if path:
        p = Path(path)
        if not p.exists():
            raise SystemExit(f"Review file not found: {p}")
        return p
    seen = set()
    candidates = [p for p in find_files("review_*.md") + find_files("*.review.md") + find_files("review*.md")
                  if p not in seen and not seen.add(p)]
    if not candidates:
        raise SystemExit("No review file found in input/. Drop a pepa-review output there or pass --review.")
    if len(candidates) == 1:
        return candidates[0]
    from cli import ui
    choice = ui.menu("Select review file", [c.name for c in candidates])
    if choice is None:
        raise SystemExit("Cancelled.")
    return candidates[choice]


def sections_path_for_plan(plan_path: Path) -> Path:
    """Return the sections JSON path that corresponds to a given plan file."""
    return config.DATA_DIR / f"sections_{plan_path.stem}.json"


def pick_plan(path: str = None) -> Path:
    """Return a plan file path. Prompt user to pick if path is None."""
    if path:
        p = Path(path)
        if not p.exists():
            raise SystemExit(f"Plan file not found: {p}")
        return p
    seen = set()
    candidates = [p for p in find_files("outline_*.md") + find_files("*.plan.md") + find_files("outline*.md")
                  if p not in seen and not seen.add(p)]
    if not candidates:
        raise SystemExit("No plan file found in input/. Drop a pepa-plan outline there or pass --plan.")
    if len(candidates) == 1:
        return candidates[0]
    from cli import ui
    choice = ui.menu("Select plan file", [c.name for c in candidates])
    if choice is None:
        raise SystemExit("Cancelled.")
    return candidates[choice]
