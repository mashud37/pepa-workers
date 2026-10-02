"""Write the documentation site's pages: the console's guides, the news, and one commands page per app from its own help."""
import shutil
import subprocess
import sys

from bundle import manifest

from . import ui

DOCS_FOLDER = manifest.ROOT / "docs"
COMMANDS_FOLDER = DOCS_FOLDER / "commands"
GUIDES_FOLDER = manifest.ROOT / "workers" / "pepa-console" / "guides"
HELP_SECONDS = 180


def help_text(app_name, words):
    """What `<app> <words> --help` prints, named the way an installed user types it.

    Raises:
        SystemExit: the help did not print.
    """
    asked = [sys.executable, "manage.py", *words, "--help"]
    ran = subprocess.run(asked, cwd=manifest.app_folder(app_name), capture_output=True, text=True, encoding="utf-8", timeout=HELP_SECONDS)
    if ran.returncode != 0:
        raise SystemExit(f"{app_name} {' '.join(words)} --help failed:\n{ran.stderr}")
    shift = len("python manage.py") - len(app_name)
    usage, gap, rest = ran.stdout.partition("\n\n")
    usage = usage.replace("\n" + " " * shift, "\n")
    text = usage + gap + rest
    return text.replace("python manage.py", app_name).rstrip()


def subcommands(top_help):
    """The subcommand names listed in an app's top-level help, in the order it lists them."""
    for line in top_help.splitlines():
        text = line.strip()
        if text.startswith("{") and text.endswith("}"):
            return text[1:-1].split(",")
    return []


def commands_page(app_name):
    """One app's commands page: its top-level help, then each subcommand's help under its own heading."""
    top_help = help_text(app_name, [])
    lines = [f"# {app_name} commands", "", "```text", top_help, "```"]
    for name in subcommands(top_help):
        lines.extend(["", f"## {name}", "", "```text", help_text(app_name, [name]), "```"])
    return "\n".join(lines) + "\n"


def copy_guides():
    """Copy every guide and the news into the site folder, and return how many files went."""
    copied = 0
    for guide in sorted(GUIDES_FOLDER.glob("*.md")):
        shutil.copy(guide, DOCS_FOLDER / guide.name)
        copied += 1
    shutil.copy(manifest.ROOT / "NEWS.md", DOCS_FOLDER / "news.md")
    return copied + 1


def run():
    """Write every generated page of the site, then say how to render it."""
    names = list(manifest.load()["apps"])

    ui.step("Plan")
    ui.info("Step 1/2: Copy the guides and the news")
    ui.info(f"Step 2/2: Write a commands page for {len(names)} app(s)")

    ui.step("Step 1/2: Guides and news")
    ui.ok(f"{copy_guides()} page(s) copied into {DOCS_FOLDER}")

    ui.step(f"Step 2/2: Commands  [{len(names)} app(s)]")
    COMMANDS_FOLDER.mkdir(exist_ok=True)
    for number, name in enumerate(names, 1):
        ui.info(f"[{number}/{len(names)}] {name}")
        (COMMANDS_FOLDER / f"{name}.md").write_text(commands_page(name), encoding="utf-8")

    ui.step("Done")
    ui.ok("Render the site with: quarto render docs")
    return 0
