from datetime import datetime

import config
from cli import ui
from cli.progress import StepSpinner
from corpus.load import paper_count
from skeleton import build as skeleton_build


def run(limit=None, sample=None, mode=None):
    ui.header("Build skeleton library")

    ui.step("Scanning corpus")
    ui.info("  · 1/4  Scan corpus")
    ui.info("  · 2/4  Label moves")
    ui.info("  · 3/4  Synthesise skeletons")
    ui.info("  · 4/4  Save library and report")

    sp = StepSpinner("Scanning corpus")
    sp.start()
    try:
        count = paper_count()
    finally:
        sp.done()
    if count == 0:
        raise SystemExit(
            "No para_*.md files found in corpus.\n"
            "Check corpus_dir in secrets.yaml or run python manage.py config."
        )
    ui.info(f"corpus: {count} para files in {config.corpus_dir().name}/")
    if limit:
        ui.info(f"limit: {limit} papers")
    if sample:
        ui.info(f"sample: {sample} papers (random)")

    library = skeleton_build.build(limit=limit, sample=sample, mode=mode)
    skeleton_build.save(library)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = config.OUTPUT_DIR / f"skeletons_{ts}.md"
    _write_report(library, report_path)

    n_skel = len(library.get("skeletons", []))
    ui.ok(f"library saved: {n_skel} skeletons from {library['n_papers']} papers")
    ui.ok(f"report:  {report_path}")
    return 0


def _write_report(library, path):
    lines = [
        "# Skeleton library\n",
        f"Generated: {library['generated']}  |  Papers analysed: {library['n_papers']}\n",
    ]
    for sk in library.get("skeletons", []):
        lines.append(f"\n## {sk.get('name', sk.get('id', ''))}")
        lines.append(f"**Type:** {sk.get('paper_type', '')}  |  **ID:** `{sk.get('id', '')}`")
        lines.append(f"\n{sk.get('description', '')}\n")
        lines.append("**Stages:**")
        for stage in sk.get("stages", []):
            share = stage.get("typical_share", "")
            share_str = f" ({share:.0%})" if isinstance(share, float) else ""
            lines.append(f"- **{stage.get('move', '')}**{share_str} — {stage.get('intent', '')}")
        examples = sk.get("example_bases", [])
        if examples:
            lines.append(f"\n**Example papers:** {', '.join(examples[:20])}")
    path.write_text("\n".join(lines), encoding="utf-8")
