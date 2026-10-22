"""Print the effective configuration and a short cost note."""
import json

import config
from cli import ui


def effective():
    """The effective settings as name: value, shared by the screen and --json."""
    backend = config.load('BACKEND')
    shown = {
        "input_dir": str(config.INPUT_DIR),
        "sub_folders": "read too" if config.scan_subfolders() else "not read",
        "output_dir": str(config.OUTPUT_DIR),
        "backend": backend,
        "para_method": config.load('PARA_METHOD'),
        "on_existing": config.load('ON_EXISTING'),
        "model": config.model_name() or "MISSING",
    }
    if backend == "anthropic":
        shown["api_key"] = "set" if config.load('ANTHROPIC_API_KEY') else "MISSING"
    elif backend == "openai-compatible":
        shown["server"] = config.load('LLM_BASE_URL') or "MISSING"
        shown["api_key"] = "set" if config.load('LLM_API_KEY') else "none"
        shown["context"] = f"{config.context_tokens():,} tokens"
    shown["text_budget"] = f"{config.text_budget():,} chars sent per paper"
    shown["run_mode"] = config.load('MODE')
    shown["speed_tier"] = config.speed()
    shown["local_stage"] = f"{config.local_workers()} process(es)"
    shown["papers_at_once"] = config.throughput('PAPER_WORKERS')
    shown["llm_calls"] = f"max {config.throughput('MAX_CONCURRENCY')} in flight"
    shown["rundown_workers"] = config.throughput('MAX_WORKERS')
    shown["look_ahead"] = f"read up to {config.local_batch()} papers ahead (parallel mode)"
    return shown


def run(as_json=False):
    shown = effective()
    if as_json:
        print(json.dumps(shown))
        return 0

    ui.header("Effective configuration")
    for name, value in shown.items():
        ui.info(f"{name.replace('_', ' '):<16} {value}")

    ui.step("Cost")
    if shown["backend"] == "anthropic":
        ui.info("Claude Haiku is pay-per-use (~$0.03–0.05 per paper for all three")
        ui.info("documents); batch mode bills the same tokens at ~50%; idle is free.")
    else:
        ui.info("Billed by the provider per token, or by the second while a server")
        ui.info("deployed with pepa-host runs.")
    ui.info("Estimates only; verify current pricing.")
    return 0
