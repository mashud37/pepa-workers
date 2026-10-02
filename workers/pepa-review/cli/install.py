"""Idempotent setup: create secrets.yaml, check deps, verify CORPUS_DIR."""
import getpass
import shutil
import sys

import config
from cli import ui

_CORE_DEPS = ["anthropic", "openai", "numpy", "yaml"]


def run():
    ui.header("Install / setup")
    _ensure_dirs()
    _ensure_secrets()
    _check_deps()
    _check_corpus()
    ui.step("Next steps")
    ui.info(f"1) {config.COMMAND} index: build the embedding index")
    ui.info(f"2) {config.COMMAND}: open the menu")
    return 0


def _ensure_dirs():
    for d in (config.DATA_DIR, config.INPUT_DIR, config.OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    ui.ok("data/, input/, output/ ready")


def _ensure_secrets():
    if not config.SECRETS_FILE.exists():
        shutil.copyfile(config.SECRETS_EXAMPLE, config.SECRETS_FILE)
        ui.ok("created secrets.yaml from template")
    else:
        ui.info("secrets.yaml already exists")

    _prompt_key("anthropic_api_key", "ANTHROPIC_API_KEY", "  Anthropic API key (blank to skip): ")
    _prompt_key("gemini_api_key", "GEMINI_API_KEY", "  Gemini API key (blank to skip): ")


def _prompt_key(name, env_hint, prompt_text):
    if config.setting(name):
        ui.ok(f"{name} present")
        return
    if not sys.stdin.isatty():
        ui.warn(f"{name} not set: add it to secrets.yaml or set {env_hint}")
        return
    key = getpass.getpass(prompt_text).strip()
    if key:
        config.set_values({name: key})
        ui.ok(f"stored {name}")


def _check_deps():
    import importlib
    missing = []
    for mod in _CORE_DEPS:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        ui.warn(f"missing packages: {', '.join(missing)}. Run: pip install -r requirements.txt")
    else:
        ui.ok("core dependencies present")


def _check_corpus():
    d = config.corpus_dir()
    if not d.exists():
        ui.warn(f"CORPUS_DIR not found: {d}")
        ui.info("Set corpus_dir in secrets.yaml or PEPAREVIEW_CORPUS_DIR env var")
        return
    from cli import progress
    sp = progress.StepSpinner("scanning corpus")
    sp.start()
    from corpus.load import paper_count
    count = paper_count()
    sp.done()
    ui.ok(f"corpus ready: {count} papers in {d}")
