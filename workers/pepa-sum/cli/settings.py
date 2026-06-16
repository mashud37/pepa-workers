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
    run_mode = ui.ask_choice(
        f"Run mode {list(config.MODES)} (auto picks by estimated time)",
        list(config.MODES), default=config.mode(),
    )
    speed = ui.ask_choice(
        f"Parallel speed {list(config.SPEED_TIERS)} (API + local throughput; "
        f"turbo needs rate-limit headroom)",
        list(config.SPEED_TIERS), default=config.speed(),
    )
    ocr = ui.ask_choice(
        f"Scanned-PDF OCR {list(config.OCR_MODES)} (off = skip image-only papers, "
        f"fast; auto = OCR only mostly-scanned docs; force = OCR every sparse page)",
        list(config.OCR_MODES), default=config.ocr_mode(),
    )

    config.set_values({"BACKEND": backend, "PARA_METHOD": para,
                       "ON_EXISTING": on_existing, "MODE": run_mode, "SPEED": speed,
                       "OCR": ocr})
    ui.ok(f"saved: backend={backend}, para_method={para}, on_existing={on_existing}, "
          f"mode={run_mode}, speed={speed}, ocr={ocr}")
    ui.info(f"{speed} → {config.paper_workers()} papers · "
            f"{config.max_concurrency()} LLM calls · {config.local_workers()} read process(es) "
            f"· up to {config.local_batch()} read ahead")

    if backend == "anthropic" and not config.anthropic_api_key():
        ui.warn("ANTHROPIC_API_KEY not set — run: python manage.py install")
    return 0
