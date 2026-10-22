"""Show effective configuration."""
import json

import config
from cli import ui


def effective():
    """The effective settings as one dictionary, for --json."""
    embed = config.embed_config()
    shown = {"backend": config.backend()}
    if config.backend() == "openai-compatible":
        shown["llm_base_url"] = config.get("llm_base_url") or None
        shown["llm_model"] = config.get("llm_model") or None
    else:
        shown["anthropic_model"] = config.draft_model()
        shown["bulk_model"] = config.bulk_model()
    shown["embed_provider"] = embed["provider"] or None
    shown["embed_model"] = embed["model"] or None
    shown["review_index"] = str(config.review_index_file())
    shown["review_index_exists"] = config.review_index_file().exists()
    shown["style_index"] = str(config.STYLE_INDEX_FILE)
    shown["style_index_exists"] = config.STYLE_INDEX_FILE.exists()
    shown["section_targets"] = dict(config.SECTION_TARGETS)
    return shown


def run(as_json=False):
    if as_json:
        print(json.dumps(effective()))
        return
    ui.header("pepa-draft: configuration")
    ui.info(f"backend         : {config.backend()}")
    if config.backend() == "openai-compatible":
        ui.info(f"llm_base_url    : {config.get('llm_base_url') or '(none)'}")
        ui.info(f"llm_model       : {config.get('llm_model') or '(none)'}")
    else:
        ui.info(f"anthropic_model : {config.draft_model()}")
        ui.info(f"bulk_model      : {config.bulk_model()}")
    embed = config.embed_config()
    ui.info(f"embed_provider  : {embed['provider'] or '(none)'}")
    ui.info(f"embed_model     : {embed['model'] or '(none)'}")
    ui.info(f"review_index    : {config.review_index_file()}")
    ui.info(f"  exists        : {config.review_index_file().exists()}")
    ui.info(f"style_index     : {config.STYLE_INDEX_FILE}")
    ui.info(f"  exists        : {config.STYLE_INDEX_FILE.exists()}")
    ui.info("")
    ui.info("Section word count targets:")
    for key, words in config.SECTION_TARGETS.items():
        ui.info(f"  {key:<20} {words}")
