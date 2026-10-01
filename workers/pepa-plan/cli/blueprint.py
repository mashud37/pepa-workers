from datetime import datetime

import config
from cli import ui
from skeleton import blueprint as blueprint_build


def run():
    ui.header("Build within-section blueprints")
    if not config.SKELETONS_FILE.exists() or not config.SEQUENCES_FILE.exists():
        raise SystemExit(
            "Blueprints need a built library: run 'Build skeletons' first "
            "(it produces skeletons.json and sequences.json)."
        )

    library = blueprint_build.build_blueprints()
    blueprint_build.save(library)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = config.OUTPUT_DIR / f"blueprints_{ts}.md"
    _write_report(library, report_path)

    n = sum(len(moves) for moves in library["blueprints"].values())
    ui.ok(f"blueprints saved: {n} move blueprint(s) -> {config.BLUEPRINTS_FILE.name}")
    ui.ok(f"report:  {report_path}")
    return 0


def _write_report(library, path):
    lines = [
        "# Within-section blueprints\n",
        f"Generated: {library['generated']}  |  "
        f"Moves with share ≥ {library['major_share']:.0%} blueprinted\n",
    ]
    for sk_id, moves in library["blueprints"].items():
        lines.append(f"\n## {sk_id}")
        if not moves:
            lines.append("\n_No moves over the share threshold._")
            continue
        for move, bp in moves.items():
            band = bp["typical_paragraphs"]
            lines.append(
                f"\n### {move}  ({band[0]}–{band[1]} paragraphs, "
                f"{bp['n_sections_observed']} sections observed)"
            )
            if bp.get("reads_like"):
                lines.append(f"\n_{bp['reads_like']}_\n")
            for step in bp.get("progression", []):
                pos = step.get("typical_position", "")
                lines.append(
                    f"- **{step.get('sub_move', '')}** "
                    f"({pos}): {step.get('intent', '')}"
                )
    path.write_text("\n".join(lines), encoding="utf-8")
