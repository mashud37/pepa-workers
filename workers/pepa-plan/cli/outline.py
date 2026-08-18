import sys
from datetime import datetime
from pathlib import Path

import config
from cli import templates, ui
from plan.outline import generate
from plan.refine import refine
from skeleton.build import load as load_library


def run(options):
    """Generate a paper outline from an idea, then refine it against feedback.

    Args:
        options: dict with `input_file`, `literature_file`, `skeleton_id`,
            `feedback`, `no_input`, and `template_file`, matching the
            outline subcommand's flags in manage.py.
    """
    input_file = options.get("input_file")
    literature_file = options.get("literature_file")
    skeleton_id = options.get("skeleton_id")
    feedback = options.get("feedback")
    no_input = options.get("no_input", False)
    template_file = options.get("template_file")
    ui.header("Outline a paper")

    idea = _resolve_idea(input_file, no_input)
    literature = _resolve_literature(literature_file)
    structure = _resolve_structure(template_file, no_input)
    # A user-authored template defines the structure outright; only fall back to a
    # learned skeleton (and its requirement that the library exists) when none is set.
    skeleton = None if structure else _resolve_skeleton(skeleton_id, no_input)
    blueprint = _resolve_blueprint(skeleton) if skeleton else None

    ui.step("Plan")
    ui.info("  · 1/3  Generate outline")
    ui.info("  · 2/3  Review and refine  (optional)")
    ui.info("  · 3/3  Save")

    ui.step("Generating first outline")
    if blueprint:
        ui.info(f"using within-section blueprints for {len(blueprint)} move(s)")
    outline_text = generate(idea, literature, skeleton, structure, blueprint)

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


def _read_file(path):
    """Read text from .txt, .md, or .docx; raises SystemExit on unsupported format."""
    p = Path(path)
    if p.suffix.lower() == ".docx":
        try:
            import docx
        except ImportError:
            raise SystemExit(
                "python-docx is required to read .docx files.\n"
                "Run: pip install python-docx"
            )
        doc = docx.Document(str(p))
        return "\n".join(para.text for para in doc.paragraphs).strip()
    return p.read_text(encoding="utf-8").strip()


def _resolve_idea(input_file, no_input):
    if input_file:
        p = Path(input_file)
        if not p.exists():
            raise SystemExit(f"Input file not found: {input_file}")
        return _read_file(p)

    files = (
        sorted(config.INPUT_DIR.glob("*.md"))
        + sorted(config.INPUT_DIR.glob("*.txt"))
        + sorted(config.INPUT_DIR.glob("*.docx"))
    )
    if files:
        options = [(f.name, "") for f in files] + [("Enter a file path", "")]
        choice = ui.menu("Select idea file", options)
        if choice is None:
            raise SystemExit("No idea selected.")
        if choice < len(files):
            return _read_file(files[choice])
        # User chose "Enter a file path"
        if not no_input and sys.stdin.isatty():
            typed = _read_typed_path()
            if typed is not None:
                return typed

    if no_input or not sys.stdin.isatty():
        raise SystemExit("No input file provided and not running interactively.")
    text = ui.ask("Paste your paper idea")
    if not text:
        raise SystemExit("No idea provided.")
    return text


def _read_typed_path():
    """Prompt for a file path and read it, or None if the user left it blank."""
    raw = ui.ask("File path")
    if not raw:
        return None
    p = Path(raw.strip())
    if not p.exists():
        raise SystemExit(f"File not found: {p}")
    return _read_file(p)


def _resolve_literature(literature_file):
    if not literature_file:
        return None
    p = Path(literature_file)
    if not p.exists():
        raise SystemExit(f"Literature file not found: {literature_file}")
    return p.read_text(encoding="utf-8").strip()


def _resolve_structure(template_file, no_input):
    """A plan template's text if the user supplies/picks one, else None (the outline
    then follows a learned skeleton). Templates take precedence over skeletons."""
    if template_file:
        p = Path(template_file)
        if not p.exists():
            raise SystemExit(f"Template not found: {template_file}")
        return p.read_text(encoding="utf-8").strip()

    existing = templates.list_templates()
    if not existing or no_input or not sys.stdin.isatty():
        return None

    options = [(p.name, "") for p in existing] + [("No template, use a learned skeleton", "")]
    choice = ui.menu("Plan structure", options)
    if choice is None or choice == len(existing):
        return None
    return templates.read(existing[choice])


def _resolve_blueprint(skeleton):
    """The chosen skeleton's within-section blueprints, if the add-on has been built;
    None otherwise (outlining works fine without it)."""
    from skeleton.blueprint import load as load_blueprints
    library = load_blueprints()
    if not library:
        return None
    return library.get("blueprints", {}).get(skeleton.get("id")) or None


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
