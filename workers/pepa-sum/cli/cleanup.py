"""Remove failed summaries from output/: any sum_*.md whose body never received
the structured template (a plain-text model error rather than a real brief),
together with its paired para_/quote_ files. A cleaned paper has no sum_ left, so
the next summarise run retries it. This clears the backlog that write-time
validation now prevents from ever being written.
"""
import config
from cli import ui
from documents import has_template


def _failed(out_dir):
    """[(base, [paths]), ...] for every sum_ file missing the template, paired
    with the para_/quote_ files that share its base name."""
    groups = []
    for sum_path in sorted(out_dir.glob("sum_*.md")):
        try:
            text = sum_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if has_template(text):
            continue
        base = sum_path.name[4:]
        paths = [p for p in (sum_path, out_dir / f"para_{base}", out_dir / f"quote_{base}")
                 if p.exists()]
        groups.append((base[:-3], paths))  # strip the .md for a clean paper label
    return groups


def run(output_dir=None, dry_run=False, force=False):
    out_dir = output_dir or config.OUTPUT_DIR
    ui.header("pepa-sum — clean failed outputs")
    if not out_dir.is_dir():
        raise SystemExit(f"Output folder not found: {out_dir}")

    ui.step(f"Scanning {out_dir}")
    failed = _failed(out_dir)
    if not failed:
        ui.ok("no failed outputs — every sum_ has the template")
        return 0

    total = len(failed)
    n_files = sum(len(paths) for _, paths in failed)
    ui.warn(f"{total} failed summary(ies) — {n_files} file(s) to remove")

    if dry_run:
        for i, (base, paths) in enumerate(failed, 1):
            ui.info(f"[{i}/{total}] {base}  ({', '.join(p.name for p in paths)})")
        ui.ok(f"dry run — {total} paper(s) would be cleaned, nothing deleted")
        return 0

    if not force and not ui.confirm(
            f"Delete {n_files} file(s) for {total} failed paper(s)?", default_yes=False):
        raise SystemExit("Aborted.")

    ui.step(f"Removing {total} failed paper(s)")
    removed = errors = 0
    for i, (base, paths) in enumerate(failed, 1):
        ui.info(f"[{i}/{total}] {base}")
        for p in paths:
            try:
                p.unlink()
            except OSError as e:
                errors += 1
                ui.error(f"  could not delete {p.name}: {e}")
        removed += 1

    ui.step("Done")
    ui.ok(f"cleaned {removed} paper(s)" + (f", {errors} file(s) failed to delete" if errors else ""))
    return 1 if errors else 0
