import config
from cli import ui


def run():
    ui.header("Configuration")
    settings = config.load()

    ui.step("Corpus")
    d = settings["corpus_dir"]
    ui.info(f"corpus_dir:  {d}")
    try:
        from corpus.load import paper_count
        ui.info(f"para files:  {paper_count()}")
    except Exception as e:
        ui.warn(f"could not count para files: {e}")

    ui.step("Models")
    models = config.model_names()
    ui.info(f"backend:              {settings['backend']}")
    if settings["backend"] == "openai-compatible":
        ui.info(f"server:               {config.get('llm_base_url') or 'missing'}")
    ui.info(f"generation (fast):    {models['fast'] or 'missing'}")
    ui.info(f"generation (quality): {models['quality'] or 'missing'}")

    ui.step("Labelling")
    ui.info(f"mode:        {settings['mode']}  (auto|serial|parallel|batch)")
    ui.info(f"concurrency: {settings['concurrency']}  ·  batch poll: "
            f"{settings['batch_poll_seconds']}s")

    ui.step("Plan templates")
    from cli.templates import list_templates
    tmpls = list_templates()
    if tmpls:
        ui.ok(f"{len(tmpls)} in {config.TEMPLATES_DIR.name}/: " + ", ".join(p.name for p in tmpls))
    else:
        ui.warn(f"none in {config.TEMPLATES_DIR.name}/, "
                f"create one: {config.COMMAND} template --new <name>")

    ui.step("Skeleton library")
    if config.SKELETONS_FILE.exists():
        import json
        lib = json.loads(config.SKELETONS_FILE.read_text(encoding="utf-8"))
        n = len(lib.get("skeletons", []))
        ui.ok(f"present: {n} skeletons from {lib.get('n_papers', '?')} papers "
              f"({lib.get('generated', '?')[:10]})")
    else:
        ui.warn(f"none yet, run: {config.COMMAND} abstract")

    ui.step("API keys")
    ui.info(f"anthropic_api_key: {'present' if settings['anthropic_api_key'] else 'absent'}")
    ui.info(f"llm_api_key:       {'present' if config.get('llm_api_key') else 'absent'}")

    ui.step("Paths")
    ui.info(f"data/:   {config.DATA_DIR}")
    ui.info(f"input/:  {config.INPUT_DIR}")
    ui.info(f"output/: {config.OUTPUT_DIR}")
