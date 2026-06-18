import config
from cli import ui


def run():
    ui.header("Configuration")

    ui.step("Corpus")
    d = config.corpus_dir()
    ui.info(f"corpus_dir:  {d}")
    try:
        from corpus.load import paper_count
        ui.info(f"para files:  {paper_count()}")
    except Exception as e:
        ui.warn(f"could not count para files: {e}")

    ui.step("Models")
    ui.info(f"generation (fast):    {config.anthropic_model()}")
    ui.info(f"generation (quality): {config.review_model()}")

    ui.step("Labelling")
    ui.info(f"mode:        {config.mode()}  (auto|serial|parallel|batch)")
    ui.info(f"concurrency: {config.concurrency()}  ·  batch poll: {config.batch_poll_seconds()}s")

    ui.step("Plan templates")
    from cli.templates import list_templates
    tmpls = list_templates()
    if tmpls:
        ui.ok(f"{len(tmpls)} in {config.TEMPLATES_DIR.name}/: " + ", ".join(p.name for p in tmpls))
    else:
        ui.warn(f"none in {config.TEMPLATES_DIR.name}/ — create one: python manage.py template --new <name>")

    ui.step("Skeleton library")
    if config.SKELETONS_FILE.exists():
        import json
        lib = json.loads(config.SKELETONS_FILE.read_text(encoding="utf-8"))
        n = len(lib.get("skeletons", []))
        ui.ok(f"present: {n} skeletons from {lib.get('n_papers', '?')} papers ({lib.get('generated', '?')[:10]})")
    else:
        ui.warn("none yet — run: python manage.py abstract")

    ui.step("API keys")
    ui.info(f"anthropic_api_key: {'present' if config.anthropic_api_key() else 'absent'}")

    ui.step("Paths")
    ui.info(f"data/:   {config.DATA_DIR}")
    ui.info(f"input/:  {config.INPUT_DIR}")
    ui.info(f"output/: {config.OUTPUT_DIR}")
