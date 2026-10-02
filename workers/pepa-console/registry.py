"""Register the pepa-* child apps, their commands, form fields, and key variables.
The console shells out to each app's `manage.py` and never imports a child.
"""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The package installs every app into a folder named apps; the repository keeps them in workers.
INSTALLED = ROOT.name == "apps"

KIND_SYMBOL = {
    "safe": "·",
    "heavy": "▶",
    "interactive": "✗",
    "terminal": "✗",
    "service": "◆",
}

MODES = (
    "auto",
    "serial",
    "parallel",
    "batch",
)


@dataclass(frozen=True)
class Command:
    name: str
    kind: str
    help: str
    no_input: bool = False
    default_flags: tuple[str, ...] = ()
    fields: tuple[dict, ...] = ()


@dataclass(frozen=True)
class App:
    name: str
    blurb: str
    commands: list[Command]
    keys: tuple[str, ...] = ()

    @property
    def path(self) -> Path:
        return ROOT / self.name


APPS: list[App] = [
    App("pepa-prep", "PDFs to clean markdown, fully local", [
        Command("extract", "heavy", "Categorise and extract every PDF in input/ to markdown"),
        Command("validate", "safe", "Grade book chapters, report only", default_flags=("-n",)),
        Command("refine", "safe", "Diagnose chapter files; tick --apply to write the repairs", fields=(
            {"name": "--apply", "type": "bool", "help": "Write the repairs instead of reporting them"},
            {"name": "--book", "type": "text", "help": "Only books whose stem contains this"},
        )),
        Command("biblio", "heavy", "Fetch bibliography from OpenAlex for pepa-sum papers", fields=(
            {"name": "--zotero", "type": "file", "help": "Zotero CSL-JSON export (default: found in input/)"},
            {"name": "--corpus", "type": "folder", "help": "pepa-sum output folder (default: from config.yaml)"},
            {"name": "--cite", "type": "bool", "help": "Also fetch citation networks from OpenCitations"},
            {"name": "--force", "type": "bool", "help": "Overwrite existing biblio files"},
        )),
        Command("split", "interactive", "Mark chapter boundaries by hand"),
        Command("install", "safe", "Check dependencies"),
    ], keys=("OPENALEX_API_KEY",)),
    App("pepa-sum", "Each paper to a brief, a paragraph rundown, and verified quotes", [
        Command("config", "safe", "Print effective config and cost note"),
        Command("summarize", "heavy", "Summarise every PDF in the input folder", fields=(
            {"name": "--input", "type": "folder", "help": "Folder of PDFs (default: input/)"},
            {"name": "--output", "type": "folder", "help": "Folder for the documents (default: output/)"},
            {"name": "--force", "type": "bool", "help": "Redo papers already processed"},
            {"name": "--mode", "type": "choice", "choices": MODES, "help": "Execution mode (default: auto)"},
        )),
        Command("clean", "safe", "List failed outputs, delete nothing", default_flags=("-n",), fields=(
            {"name": "--output", "type": "folder", "help": "Output folder to check (default: output/)"},
        )),
        Command("deploy", "heavy", "Build and deploy the self-hosted fallback service"),
        Command("settings", "interactive", "Choose backend and rundown method"),
        Command("install", "safe", "Create env.yaml, store the key, check dependencies"),
    ], keys=("ANTHROPIC_API_KEY", "PEPA_LLM_API_KEY", "PEPA_JOB_TOKEN")),
    App("pepa-read", "Full-text search over prep and sum output, local web UI, literature lists", [
        Command("index", "safe", "Build or refresh the search index", fields=(
            {"name": "--force", "type": "bool", "help": "Reindex every file, ignoring modification times"},
        )),
        Command("search", "safe", "One-shot keyword search", fields=(
            {"name": "query", "type": "text", "help": "Free text, for example: brand personality author:aaker"},
            {"name": "--author", "type": "text", "help": "Filter by author"},
            {"name": "--limit", "type": "int", "help": "Results to show (default: 20)"},
        )),
        Command("serve", "service", "Start the local search page", default_flags=("--no-browser",), fields=(
            {"name": "--port", "type": "int", "help": "Port (default: 5151)"},
        )),
        Command("open", "safe", "Open a document in its default Windows app", fields=(
            {"name": "id", "type": "int", "help": "Document id from a search result"},
            {"name": "--which", "type": "choice", "choices": ("text", "sum"), "help": "Which file to open"},
        )),
        Command("lists", "safe", "Show all literature lists and their item counts"),
        Command("list-show", "safe", "Show the documents in a literature list", fields=(
            {"name": "name", "type": "text", "help": "List name"},
        )),
        Command("list-export", "safe", "Export a list's document stems", fields=(
            {"name": "name", "type": "text", "help": "List name"},
            {"name": "--output", "type": "file", "help": "Write to this file instead of the result pane"},
        )),
        Command("list-delete", "interactive", "Delete a literature list, after confirming"),
        Command("install", "safe", "Check dependencies and source folders"),
    ]),
    App("pepa-review", "Embedding index over the sum corpus; literature review, gaps, and maps", [
        Command("config", "safe", "Show effective configuration (counts the corpus first, so it is slow)"),
        Command("index", "heavy", "Build or refresh the embedding index", fields=(
            {"name": "--force", "type": "bool", "help": "Rebuild from scratch"},
        )),
        Command("review", "heavy", "Assemble a literature review, choosing works as it asks, or by similarity", fields=(
            {"name": "--input", "type": "file", "help": "Outline file"},
            {"name": "--auto", "type": "bool", "help": "Select works by similarity instead of asking"},
            {"name": "--list", "type": "file", "help": "Stem list exported from pepa-read"},
        )),
        Command("gaps", "heavy", "Gap-check a draft against the corpus", fields=(
            {"name": "--input", "type": "file", "help": "Draft file"},
        )),
        Command("map", "heavy", "Generate the corpus thematic map", fields=(
            {"name": "--threads", "type": "int", "help": "Target thread count (default: auto)"},
        )),
        Command("threadmap", "heavy", "Re-cluster one thread of a saved map", fields=(
            {"name": "--map", "type": "file", "help": "Corpus map file in output/"},
            {"name": "--thread", "type": "text", "help": "Thread number, name substring, or all"},
        )),
        Command("biblio", "heavy", "Bibliographic enrichment: ingest, export, stats, or network", fields=(
            {"name": "subcmd", "type": "choice", "choices": ("ingest", "export", "stats", "network"), "help": "What to do"},
            {"name": "--works", "type": "file", "help": "Works metadata file, required for ingest"},
            {"name": "--citations", "type": "file", "help": "Citations edge list, optional for ingest"},
            {"name": "--graph-type", "type": "choice", "choices": ("citation", "coupling"), "help": "Network type"},
            {"name": "--format", "type": "choice", "choices": ("html", "graphml"), "help": "Network file format"},
        )),
        Command("explore", "interactive", "Interactive discovery over the corpus"),
        Command("install", "safe", "Set up files and check dependencies"),
    ], keys=("ANTHROPIC_API_KEY", "PEPA_LLM_API_KEY", "GEMINI_API_KEY", "PEPA_EMBED_API_KEY")),
    App("pepa-plan", "Rhetorical-move labelling and learned skeletons to a paragraph outline", [
        Command("config", "safe", "Show effective configuration"),
        Command("template", "safe", "List plan templates", default_flags=("--list",)),
        Command("abstract", "heavy", "Build the skeleton library from the pepa-sum corpus", fields=(
            {"name": "--limit", "type": "int", "help": "Use only the first N para files"},
            {"name": "--sample", "type": "int", "help": "Use a random sample of N para files"},
            {"name": "--mode", "type": "choice", "choices": MODES, "help": "Labelling mode (default: auto)"},
        )),
        Command("blueprint", "heavy", "Build paragraph-progression blueprints"),
        Command("outline", "heavy", "Generate a paragraph-by-paragraph outline", no_input=True, fields=(
            {"name": "--input", "type": "file", "help": "Idea file"},
            {"name": "--literature", "type": "file", "help": "Literature notes file"},
            {"name": "--template", "type": "file", "help": "Plan template to follow"},
            {"name": "--skeleton-id", "type": "text", "help": "Skeleton ID to use"},
            {"name": "--feedback", "type": "text", "help": "One scripted feedback pass"},
        )),
        Command("review", "heavy", "Argumentation-flow feedback on an idea or draft", fields=(
            {"name": "--input", "type": "file", "help": "Idea or draft file"},
        )),
        Command("install", "safe", "Set up files and check dependencies"),
    ], keys=("ANTHROPIC_API_KEY", "PEPA_LLM_API_KEY")),
    App("pepa-draft", "Plan plus review to a first draft, section by section", [
        Command("config", "safe", "Show effective configuration"),
        Command("style", "safe", "List author writing samples", default_flags=("list",)),
        Command("sections", "heavy", "Assign plan paragraphs to manuscript sections", fields=(
            {"name": "--plan", "type": "file", "help": "Plan file"},
            {"name": "--reset", "type": "bool", "help": "Start the section assignment again"},
        )),
        Command("draft", "heavy", "Write a full manuscript draft", fields=(
            {"name": "--review", "type": "file", "help": "Literature review file"},
            {"name": "--plan", "type": "file", "help": "Plan file"},
            {"name": "--sections", "type": "file", "help": "Section assignment file"},
            {"name": "--backend", "type": "choice", "choices": ("anthropic", "openai-compatible", "vllm"), "help": "Model backend"},
            {"name": "--no-retrieval", "type": "bool", "help": "Skip corpus retrieval"},
            {"name": "--no-style", "type": "bool", "help": "Skip style matching"},
            {"name": "--style-profile", "type": "text", "help": "Style profile name"},
        )),
        Command("setup", "terminal", "Configure API keys and paths; keys typed here belong on the Keys page"),
        Command("install", "safe", "Set up files and check dependencies"),
    ], keys=("ANTHROPIC_API_KEY", "PEPA_LLM_API_KEY", "GEMINI_API_KEY", "PEPA_EMBED_API_KEY", "PEPADRAFT_VLLM_TOKEN")),
]


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
