"""Register the pepa-* child apps and their commands so the orchestrator
can shell out to `manage.py <command>` without importing any child.
"""
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Command:
    name: str
    kind: str
    help: str
    no_input: bool = False
    default_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class App:
    name: str
    blurb: str
    commands: list[Command] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return ROOT / self.name


APPS: list[App] = [
    App("pepa-sum", "Summarise academic PDFs into structured Markdown", [
        Command("config", "safe", "Print effective config and cost note"),
        Command("clean", "safe", "List/delete failed outputs", default_flags=("-n",)),
        Command("summarize", "heavy", "Summarise every PDF in input/"),
        Command("deploy", "heavy", "Build and deploy the fallback service"),
        Command("settings", "interactive", "Choose backend + rundown method"),
        Command("install", "safe", "Create env.yaml, store key, check deps"),
    ]),
    App("pepa-review", "Literature review and corpus exploration", [
        Command("config", "safe", "Show effective configuration"),
        Command("review", "heavy", "Assemble a literature review"),
        Command("gaps", "heavy", "Gap-check a draft against the corpus"),
        Command("map", "heavy", "Generate corpus thematic map"),
        Command("threadmap", "heavy", "Re-cluster one thread of a saved map"),
        Command("index", "heavy", "Build/refresh the embedding index"),
        Command("explore", "interactive", "Interactive discovery over the corpus"),
        Command("install", "safe", "Set up files and check dependencies"),
    ]),
    App("pepa-plan", "Plan and outline a manuscript", [
        Command("config", "safe", "Show effective configuration"),
        Command("template", "safe", "List/manage plan templates", default_flags=("--list",)),
        Command("abstract", "heavy", "Build skeleton library from corpus"),
        Command("blueprint", "heavy", "Build paragraph-progression blueprints"),
        Command("outline", "heavy", "Generate a paragraph outline", no_input=True),
        Command("review", "heavy", "Argumentation-flow feedback"),
        Command("install", "safe", "Set up files and check dependencies"),
    ]),
    App("pepa-prep", "Prepare and validate the source corpus", [
        Command("validate", "safe", "Grade chapters / report only", default_flags=("-n",)),
        Command("score", "safe", "Score segmentation against tag files"),
        Command("extract", "heavy", "Categorise and extract PDFs to markdown"),
        Command("label", "heavy", "Create segmentation tag files from PDFs"),
        Command("biblio", "heavy", "Fetch bibliography from OpenAlex"),
        Command("split", "interactive", "Mark chapter boundaries by hand"),
        Command("install", "safe", "Check dependencies"),
    ]),
    App("pepa-draft", "Write a full manuscript draft", [
        Command("config", "safe", "Show effective configuration"),
        Command("style", "safe", "Manage author writing samples", default_flags=("list",)),
        Command("draft", "heavy", "Write a full manuscript draft"),
        Command("sections", "heavy", "Assign plan paragraphs to sections"),
        Command("setup", "interactive", "Configure API keys and paths"),
        Command("install", "safe", "Set up files and check dependencies"),
    ]),
]

KIND_SYMBOL = {"safe": "·", "heavy": "▶", "interactive": "✗"}


def get_app(name: str) -> App | None:
    for app in APPS:
        if app.name == name:
            return app
    return None


def get_command(app_name: str, command: str) -> Command | None:
    app = get_app(app_name)
    if not app:
        return None
    for candidate in app.commands:
        if candidate.name == command:
            return candidate
    return None
