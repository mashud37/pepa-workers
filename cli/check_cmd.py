"""Hold every app against the release gate and print one row each, so what blocks a release is visible."""
import os
import subprocess

from bundle import manifest

from . import ui

COPYLEFT_PACKAGES = [
    "pymupdf",
    "language-tool-python",
]

COPYLEFT_IMPORTS = [
    "import fitz",
    "import language_tool_python",
]

GATE_CHECKS = [
    "licence",
    "free",
    "data root",
    "siblings",
    "no-input",
    "clean",
    "models",
]

GATE_COLUMNS = [
    "app",
    "released",
    "licence",
    "free",
    "data root",
    "siblings",
    "no-input",
    "clean",
    "models",
]

MODEL_FAMILIES = [
    "haiku",
    "sonnet",
    "opus",
]


def mark(passed):
    """A gate answer as the table shows it."""
    return "yes" if passed else "no"


def clears_gate(row):
    """True when every gate answer in one app's row is yes."""
    for name in GATE_CHECKS:
        if row[name] == "no":
            return False
    return True


def app_text(folder):
    """Every Python file of the app read as one piece of text."""
    pieces = []
    for path in sorted(folder.rglob("*.py")):
        pieces.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(pieces)


def finds_siblings_by_code_folder(text):
    """True when the app still finds a sibling's files next to its own code rather than its data."""
    without_data_root = text.replace("DATA_ROOT.parent", "")
    without_folder_name = without_data_root.replace("ROOT.parent.name", "")
    return "ROOT.parent" in without_folder_name


def has_clean_tree(folder):
    """True when the app's folder holds no uncommitted change."""
    asked = ["git", "-C", str(folder), "status", "--porcelain", "--", "."]
    found = subprocess.run(asked, capture_output=True, text=True)
    if found.returncode != 0:
        return False
    return not found.stdout.strip()


def copyleft_in(folder):
    """The copyleft packages an app still asks for, named in its requirements or imported in its code."""
    found = []
    path = folder / "requirements.txt"
    if path.exists():
        wanted = path.read_text(encoding="utf-8").lower()
        found.extend([name for name in COPYLEFT_PACKAGES if name in wanted])
    for line in COPYLEFT_IMPORTS:
        asked = ["git", "-C", str(folder), "grep", "--quiet", line]
        if subprocess.run(asked, capture_output=True).returncode == 0:
            found.append(line)
    return found


def newest_models():
    """The newest Claude model in each family, from Anthropic's models list; empty without ANTHROPIC_API_KEY."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {}
    import anthropic
    newest = {}
    for model in anthropic.Anthropic().models.list(limit=100):
        for family in MODEL_FAMILIES:
            if model.id.startswith(f"claude-{family}-") and family not in newest:
                newest[family] = model.id
    return newest


def models_mark(text, newest):
    """yes when the app names the newest model of every Claude family it uses; unchecked without the list."""
    if not newest:
        return "unchecked"
    for family, model_id in newest.items():
        if f"claude-{family}-" in text and model_id not in text:
            return "no"
    return "yes"


def gate_row(name, entry, newest):
    """Where one app stands against the release gate, as the fields the table shows."""
    folder = manifest.app_folder(name)
    text = app_text(folder)
    return {
        "app": name,
        "released": mark(entry["released"]),
        "licence": mark((manifest.ROOT / "LICENSE").exists()),
        "free": mark(not copyleft_in(folder)),
        "data root": mark("PEPA_PROJECT" in text),
        "siblings": mark(not finds_siblings_by_code_folder(text)),
        "no-input": mark("--no-input" in text),
        "clean": mark(has_clean_tree(folder)),
        "models": models_mark(text, newest),
    }


def run():
    """Print the gate for every app in the manifest and say how many are ready to release."""
    settings = manifest.load()
    names = sorted(settings["apps"])
    ui.step(f"Release gate  [{len(names)} app(s)]")
    newest = newest_models()
    if newest:
        ui.info(f"newest models: {', '.join(newest.values())}")
    else:
        ui.warn("models not checked: set ANTHROPIC_API_KEY to compare against Anthropic's models list")
    rows = []
    for number, name in enumerate(names, 1):
        ui.info(f"[{number}/{len(names)}] {name}")
        rows.append(gate_row(name, settings["apps"][name], newest))
    ui.table(rows, GATE_COLUMNS)

    ready = [row for row in rows if clears_gate(row)]
    if ready:
        ui.ok(f"{len(ready)} of {len(rows)} app(s) clear the gate: {', '.join(row['app'] for row in ready)}")
    else:
        ui.warn("No app clears the gate yet. Every no in the table above is one thing left to fix.")

    blocked = [row for row in rows if row["released"] == "yes" and not clears_gate(row)]
    if blocked:
        ui.error(f"released without clearing the gate: {', '.join(row['app'] for row in blocked)}")
        return 1
    return 0
