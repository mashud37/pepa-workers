import sys
from datetime import datetime
from pathlib import Path

import config
from cli import ui
from plan.outline import generate
from plan.refine import refine
from skeleton.build import load as load_library


def run(input_file=None, literature_file=None, skeleton_id=None,
        feedback=None, no_input=False):
    ui.header("Outline a paper")

    idea = _resolve_idea(input_file, no_input)
    literature = _resolve_literature(literature_file)
    skeleton = _resolve_skeleton(skeleton_id, no_input)

    ui.step("Generating first outline")
    outline_text = generate(idea, literature, skeleton)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = config.OUTPUT_DIR / f"outline_{ts}.md"
    _save(outline_text, out_path)
    ui.info(out_path.name)
    _show(outline_text)

    if feedback:
        ui.step("Applying feedback")
        outline_text = refine(outline_text, feedback, skeleton)
        _save(outline_text, out_path)
        _show(outline_text)
    elif not no_input and sys.stdin.isatty():
        while True:
            fb = ui.ask("Feedback (blank to accept)")
            if not fb:
                break
            ui.step("Refining outline")
            outline_text = refine(outline_text, fb, skeleton)
            _save(outline_text, out_path)
            _show(outline_text)

    print(str(out_path))
    return 0


def _resolve_idea(input_file, no_input):
    if input_file:
        p = Path(input_file)
        if not p.exists():
            raise SystemExit(f"Input file not found: {input_file}")
        return p.read_text(encoding="utf-8").strip()

    files = sorted(config.INPUT_DIR.glob("*.md")) + sorted(config.INPUT_DIR.glob("*.txt"))
    if files:
        options = [(f.name, "") for f in files] + [("Enter path or free text", "")]
        choice = ui.menu("Select idea file", options)
        if choice is None:
            raise SystemExit("No idea selected.")
        if choice < len(files):
            return files[choice].read_text(encoding="utf-8").strip()

    if no_input or not sys.stdin.isatty():
        raise SystemExit("No input file provided and not running interactively.")
    text = ui.ask("Paste your paper idea")
    if not text:
        raise SystemExit("No idea provided.")
    return text


def _resolve_literature(literature_file):
    if not literature_file:
        return None
    p = Path(literature_file)
    if not p.exists():
        raise SystemExit(f"Literature file not found: {literature_file}")
    return p.read_text(encoding="utf-8").strip()


def _resolve_skeleton(skeleton_id, no_input):
    library = load_library()
    if library is None:
        raise SystemExit(
            "No skeleton library found.\n"
            "Run: python manage.py abstract"
        )
    skeletons = library.get("skeletons", [])
    if not skeletons:
        raise SystemExit(
            "Skeleton library is empty.\n"
            "Run: python manage.py abstract"
        )

    if skeleton_id:
        for sk in skeletons:
            if sk.get("id") == skeleton_id:
                return sk
        raise SystemExit(f"Skeleton ID not found: {skeleton_id}")

    if len(skeletons) == 1 or no_input or not sys.stdin.isatty():
        return skeletons[0]

    options = [(sk.get("name", sk.get("id", "")), sk.get("paper_type", "")) for sk in skeletons]
    choice = ui.menu("Select skeleton", options)
    if choice is None:
        return skeletons[0]
    return skeletons[choice]


def _save(text, path):
    path.write_text(text, encoding="utf-8")


def _show(text):
    ui.step("Outline")
    for line in text.splitlines():
        print(f"  {line}")
