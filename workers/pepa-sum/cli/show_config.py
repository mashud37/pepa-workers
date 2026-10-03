"""Print the effective configuration and a short cost note."""
import config
from cli import ui


def run():
    ui.header("Effective configuration")
    ui.info(f"input dir    {config.INPUT_DIR}")
    ui.info(f"sub-folders  {'read too' if config.scan_subfolders() else 'not read'}")
    ui.info(f"output dir   {config.OUTPUT_DIR}")
    ui.info(f"backend      {config.load('BACKEND')}")
    ui.info(f"para method  {config.load('PARA_METHOD')}")
    ui.info(f"on existing  {config.load('ON_EXISTING')}")

    backend = config.load('BACKEND')
    ui.info(f"model        {config.model_name() or 'MISSING'}")
    if backend == "anthropic":
        ui.info(f"API key      {'set' if config.load('ANTHROPIC_API_KEY') else 'MISSING'}")
    elif backend == "openai-compatible":
        ui.info(f"server       {config.load('LLM_BASE_URL') or 'MISSING'}")
        ui.info(f"API key      {'set' if config.load('LLM_API_KEY') else 'none'}")
        ui.info(f"context      {config.context_tokens():,} tokens")

    ui.info(f"text budget  {config.text_budget():,} chars sent per paper")
    ui.info(f"run mode     {config.load('MODE')}  ·  speed tier {config.speed()}  ·  "
            f"local stage {config.local_workers()} process(es)")
    ui.info(f"concurrency  {config.throughput('PAPER_WORKERS')} papers at once  ·  "
            f"max {config.throughput('MAX_CONCURRENCY')} LLM calls in flight  ·  "
            f"{config.throughput('MAX_WORKERS')} rundown workers")
    ui.info(f"look-ahead   read up to {config.local_batch()} papers ahead (parallel mode)")
    if config.load('BACKEND') == "anthropic":
        ui.info(f"batch poll   every {config.batch_poll_seconds()}s (batch mode)")

    ui.step("Cost")
    if backend == "anthropic":
        ui.info("Claude Haiku is pay-per-use (~$0.03–0.05 per paper for all three")
        ui.info("documents); batch mode bills the same tokens at ~50%; idle is free.")
    else:
        ui.info("Billed by the provider per token, or by the second while a server")
        ui.info("deployed with pepa-host runs.")
    ui.info("Estimates only; verify current pricing.")
    return 0
