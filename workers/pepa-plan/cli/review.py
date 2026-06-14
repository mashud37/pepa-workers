import sys
from datetime import datetime
from pathlib import Path

import config
from cli import ui
from backends import llm
from backends import prompt
from skeleton.build import load as load_library


def run(input_file=None):
    ui.header("Review argumentation")

    text = _resolve_input(input_file)
    library = load_library()
    skeleton = library["skeletons"][0] if library and library.get("skeletons") else None

    ui.step("Analysing argumentation flow")
    feedback_text = llm.complete(
        prompt.review_system(),
        prompt.review_prompt(text, skeleton),
        max_tokens=4000,
        quality=True,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = config.OUTPUT_DIR / f"feedback_{ts}.md"
    out_path.write_text(feedback_text, encoding="utf-8")

    ui.step("Feedback")
    for line in feedback_text.splitlines():
        print(f"  {line}")

    print(str(out_path))
    return 0


def _resolve_input(input_file):
    if input_file:
        p = Path(input_file)
        if not p.exists():
            raise SystemExit(f"Input file not found: {input_file}")
        return p.read_text(encoding="utf-8").strip()

    files = sorted(config.INPUT_DIR.glob("*.md")) + sorted(config.INPUT_DIR.glob("*.txt"))
    if files:
        options = [(f.name, "") for f in files] + [("Enter path or free text", "")]
        choice = ui.menu("Select file to review", options)
        if choice is None:
            raise SystemExit("No input selected.")
        if choice < len(files):
            return files[choice].read_text(encoding="utf-8").strip()

    if not sys.stdin.isatty():
        raise SystemExit("No input file provided and not running interactively.")
    text = ui.ask("Paste idea or draft text")
    if not text:
        raise SystemExit("No input provided.")
    return text
