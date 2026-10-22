"""Give feedback on how an idea or a draft builds its argument, against the field's learned structure when there is one.
The console's Draft page shows each feedback file.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import config
from backends import llm, prompt
from cli import costs, items, ui
from skeleton.build import load as load_library

FEEDBACK_TOKENS = 4000


def run(input_file=None, only_estimate=False, output_name=None):
    text = _resolve_input(input_file)
    library = load_library()
    skeleton = library["skeletons"][0] if library and library.get("skeletons") else None
    if only_estimate:
        sent = prompt.review_system() + prompt.review_prompt(text, skeleton)
        print(json.dumps(costs.estimate([{"input_chars": len(sent), "output_tokens": FEEDBACK_TOKENS}])))
        return 0
    ui.header("Review argumentation")

    ui.step("Plan")
    ui.info("  · 1/2  Analyse argumentation flow")
    ui.info("  · 2/2  Save feedback")

    items.stage("Reading how the argument builds")
    if skeleton:
        ui.info(f"against the learned structure {skeleton.get('name', '')}")
    feedback_text = llm.complete(
        prompt.review_system(),
        prompt.review_prompt(text, skeleton),
        max_tokens=FEEDBACK_TOKENS,
        quality=True,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = config.OUTPUT_DIR / (output_name or f"feedback_{ts}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(feedback_text, encoding="utf-8")

    ui.step("Feedback")
    for line in feedback_text.splitlines():
        print(f"  {line}", file=sys.stderr)

    print(str(out_path))
    return 0


def _resolve_input(input_file):
    if input_file:
        p = Path(input_file)
        if not p.exists():
            raise SystemExit(f"Input file not found: {input_file}")
        return p.read_text(encoding="utf-8").strip()

    if not sys.stdin.isatty():
        raise SystemExit("No file to review given: pass --input FILE.")
    files = sorted(config.INPUT_DIR.glob("*.md")) + sorted(config.INPUT_DIR.glob("*.txt"))
    if files:
        options = [(f.name, "") for f in files] + [("Enter path or free text", "")]
        choice = ui.menu("Select file to review", options)
        if choice is None:
            raise SystemExit("No input selected.")
        if choice < len(files):
            return files[choice].read_text(encoding="utf-8").strip()

    text = ui.ask("Paste idea or draft text")
    if not text:
        raise SystemExit("No input provided.")
    return text
