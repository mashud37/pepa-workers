"""Print the effective configuration and a short cost note."""
import config
from cli import ui


def run():
    ui.header("Effective configuration")
    ui.info(f"input dir    {config.INPUT_DIR}")
    ui.info(f"output dir   {config.OUTPUT_DIR}")
    ui.info(f"backend      {config.backend()}")
    ui.info(f"para method  {config.para_method()}")
    ui.info(f"on existing  {config.on_existing()}")

    if config.backend() == "anthropic":
        ui.info(f"model        {config.anthropic_model()}")
        ui.info(f"API key      {'set' if config.anthropic_api_key() else 'MISSING'}")
    else:
        ui.info(f"model        {config.model()}")
        ui.info(f"endpoint     {config.base_url() or '(not deployed)'}")
        ui.info(f"token        {'set' if config.job_token() else 'missing'}")

    ui.info(f"text budget  {config.TEXT_BUDGET:,} chars sent per paper")

    ui.step("Cost")
    if config.backend() == "anthropic":
        ui.info("Claude Haiku is pay-per-use (~$0.03–0.05 per paper for all three")
        ui.info("documents); zero cost when idle.")
    else:
        ui.info("Self-hosted Cloud Run scales to zero — you pay only while a paper")
        ui.info("is being processed (CPU seconds), plus image storage.")
    ui.info("Estimates only; verify current pricing.")
    return 0
