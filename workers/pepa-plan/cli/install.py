import getpass
import shutil
import sys

import config
from cli import ui

_CORE_DEPS = ["anthropic", "yaml"]


def run():
    ui.header("Install / setup")
    _ensure_dirs()
    _ensure_secrets()
    _check_deps()
    _check_corpus()
    ui.step("Next steps")
    ui.info("1) python manage.py abstract: build the skeleton library")
    ui.info("2) python manage.py: open the menu")
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
    api_key = config.load()["anthropic_api_key"]
    _prompt_key("anthropic_api_key", api_key,
                "ANTHROPIC_API_KEY", "  Anthropic API key (blank to skip): ")


def _prompt_key(name, current_value, env_hint, prompt_text):
    if current_value:
        ui.ok(f"{name} present")
        return
    if not sys.stdin.isatty():
        ui.warn(f"{name} not set, add it to secrets.yaml or set {env_hint}")
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
        ui.warn(f"missing packages: {', '.join(missing)}, run: pip install -r requirements.txt")
    else:
        ui.ok("core dependencies present")


def _check_corpus():
    d = config.load()["corpus_dir"]
    if not d.exists():
        ui.warn(f"CORPUS_DIR not found: {d}")
        ui.info("Set corpus_dir in secrets.yaml or PEPAPLAN_CORPUS_DIR env var")
        return
    from corpus.load import paper_count
    count = paper_count()
    ui.ok(f"corpus ready: {count} para files in {d}")
