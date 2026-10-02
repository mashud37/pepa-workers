"""Idempotent setup: create dirs, seed secrets, check dependencies."""
import config
from cli import ui


def _check_packages():
    missing = []
    for pkg in ("anthropic", "openai", "yaml", "numpy"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append("pyyaml" if pkg == "yaml" else pkg)
    if missing:
        ui.warn(f"missing packages: {', '.join(missing)}")
        ui.info("run: pip install -r requirements.txt")
    else:
        ui.ok("all required packages installed")


def run():
    ui.header("pepa-draft: install")

    for d in (config.DATA_DIR, config.INPUT_DIR, config.OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.touch()
    ui.ok("directories ready")

    if not config.SECRETS_FILE.exists() and config.SECRETS_EXAMPLE.exists():
        import shutil
        shutil.copy(config.SECRETS_EXAMPLE, config.SECRETS_FILE)
        ui.ok(f"created {config.SECRETS_FILE.name} from example, fill in your keys")
    elif config.SECRETS_FILE.exists():
        ui.ok("secrets.yaml present")
    else:
        ui.warn("secrets.example.yaml missing: cannot seed secrets")

    _check_packages()

    ui.info("review index: " + str(config.review_index_file()))
    if not config.review_index_file().exists():
        ui.warn("review index not found, build it in pepa-review: python manage.py index")

    ui.ok("install complete")
