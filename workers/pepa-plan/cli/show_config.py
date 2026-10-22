import json

import config
from cli import ui


def effective():
    """The effective settings as one dictionary, for --json."""
    settings = config.load()
    models = config.model_names()
    from cli.templates import list_templates
    skeletons = 0
    if config.SKELETONS_FILE.exists():
        skeletons = len(json.loads(config.SKELETONS_FILE.read_text(encoding="utf-8")).get("skeletons", []))
    return {
        "corpus_dir": str(settings["corpus_dir"]),
        "backend": settings["backend"],
        "server": config.get("llm_base_url") or None,
        "model_fast": models["fast"] or None,
        "model_quality": models["quality"] or None,
        "mode": settings["mode"],
        "concurrency": settings["concurrency"],
        "templates": [str(path) for path in list_templates()],
        "skeletons": skeletons,
        "anthropic_api_key": "present" if settings["anthropic_api_key"] else "absent",
        "llm_api_key": "present" if config.get("llm_api_key") else "absent",
        "data_dir": str(config.DATA_DIR),
        "input_dir": str(config.INPUT_DIR),
        "output_dir": str(config.OUTPUT_DIR),
    }


def run(as_json=False):
    if as_json:
        print(json.dumps(effective()))
        return 0
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
    return 0
