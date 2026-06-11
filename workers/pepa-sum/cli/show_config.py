"""Print the effective configuration and a short cost note."""
import config
from cli import ui


def run():
    ui.header("Effective configuration")
    ui.info(f"input dir   {config.INPUT_DIR}")
    ui.info(f"output dir  {config.OUTPUT_DIR}")
    ui.info(f"model       {config.model()}")
    ui.info(f"endpoint    {config.base_url() or '(not deployed)'}")
    ui.info(f"token       {'set' if config.job_token() else 'missing'}")
    ui.info(f"text budget {config.TEXT_BUDGET:,} chars sent per paper")

    ui.step("Cost")
    ui.info("Cloud Run service scales to zero — you pay only while a paper is")
    ui.info("being summarised (CPU seconds), plus Artifact Registry image storage.")
    ui.info("Estimates only; verify current pricing for your region.")
    return 0
