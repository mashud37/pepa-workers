"""Choose the backend and paragraph-rundown method; persist them to env.yaml.

A saved setting applies to every later run until changed."""
import config
from cli import ui


def run():
    ui.header("Settings")

    backend = ui.ask_choice(
        f"Backend {list(config.BACKENDS)}", list(config.BACKENDS), default=config.backend()
    )
    para = ui.ask_choice(
        f"Paragraph rundown {list(config.PARA_METHODS)}", list(config.PARA_METHODS),
        default=config.para_method(),
    )
    on_existing = ui.ask_choice(
        f"When a paper is already done {list(config.ON_EXISTING_MODES)}",
        list(config.ON_EXISTING_MODES), default=config.on_existing(),
    )

    config.set_values({"BACKEND": backend, "PARA_METHOD": para, "ON_EXISTING": on_existing})
    ui.ok(f"saved: backend={backend}, para_method={para}, on_existing={on_existing}")

    if backend == "anthropic" and not config.anthropic_api_key():
        ui.warn("ANTHROPIC_API_KEY not set — run: python manage.py install")
    return 0
