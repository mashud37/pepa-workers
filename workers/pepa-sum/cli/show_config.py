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
    ui.info(f"run mode     {config.mode()}  ·  speed tier {config.speed()}  ·  "
            f"local stage {config.local_workers()} process(es)")
    ui.info(f"concurrency  {config.paper_workers()} papers at once  ·  "
            f"max {config.max_concurrency()} LLM calls in flight  ·  "
            f"{config.max_workers()} rundown workers")
    ui.info(f"look-ahead   read up to {config.local_batch()} papers ahead (parallel mode)")
    if config.backend() == "anthropic":
        ui.info(f"batch poll   every {config.batch_poll_seconds()}s (batch mode)")

    ui.step("Cost")
    if config.backend() == "anthropic":
        ui.info("Claude Haiku is pay-per-use (~$0.03–0.05 per paper for all three")
        ui.info("documents); batch mode bills the same tokens at ~50%; idle is free.")
    else:
        ui.info("Self-hosted Cloud Run scales to zero — you pay only while a paper")
        ui.info("is being processed (CPU seconds), plus image storage.")
    ui.info("Estimates only; verify current pricing.")
    return 0
