"""Deploy the self-hosted model to Cloud Run as an OpenAI-compatible server, then point pepa-sum at
its address and key, so it is used like any other openai-compatible server.
"""
import secrets
import shutil
import subprocess
import time

import yaml

import config
from cli import ui

MANIFEST = config.ROOT / "gcloud_app.yaml"
APIS = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
]
BUILD_RETRY_SECONDS = 90
STEPS = [
    "Select GCP project",
    "Enable APIs, registry and service account",
    "Build the image (the model is baked in, so this takes a while)",
    "Deploy the service",
    "Point pepa-sum at the service",
]


def run():
    ui.header("Deploy self-hosted model")
    if not shutil.which("gcloud"):
        raise SystemExit(f"gcloud CLI not found, install it first (run: {config.COMMAND} install).")
    for number, name in enumerate(STEPS, 1):
        ui.info(f"{number}/{len(STEPS)}  {name}")

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    project = _select_project()
    region = manifest["region"]
    image = f"{region}-docker.pkg.dev/{project}/{manifest['artifact_registry']['image']}"

    ui.step(STEPS[1])
    _gcloud("services", "enable", *APIS, f"--project={project}")
    _gcloud("artifacts", "repositories", "create", manifest["artifact_registry"]["repo"], "--repository-format=docker", f"--location={region}", f"--project={project}")
    _gcloud("iam", "service-accounts", "create", manifest["service_account"]["name"], f"--display-name={manifest['service_account']['display']}", f"--project={project}")

    ui.step(STEPS[2])
    if _build(image, project) != 0:
        raise SystemExit("Image build failed.")

    ui.step(STEPS[3])
    api_key = secrets.token_hex(32)
    if _deploy(manifest, image, project, api_key) != 0:
        raise SystemExit("Deploy failed.")
    url = _gcloud("run", "services", "describe", manifest["service"]["name"], f"--region={region}", f"--project={project}", "--format=value(status.url)")
    ui.ok(f"service at {url}")

    ui.step(STEPS[4])
    _point_at_service(manifest, url, api_key)
    return 0


def _select_project():
    ui.step(STEPS[0])
    current = _gcloud("config", "get-value", "project")
    listing = _gcloud("projects", "list", "--format=value(projectId)")
    projects = [p for p in listing.splitlines() if p.strip()]

    if current:
        ui.info(f"active gcloud project: {current}")
    for i, p in enumerate(projects, 1):
        ui.info(f"{i}) {p}{'  (active)' if p == current else ''}")

    raw = (ui.ask("Project to deploy to (number or id)", default=current) or "").strip()
    if not raw:
        raise SystemExit("No project selected.")
    if raw.isdigit() and 1 <= int(raw) <= len(projects):
        return projects[int(raw) - 1]
    return raw


def _build(image, project):
    """Build on Cloud Build, retrying once: a first build right after enabling the API can be refused
    while its permissions propagate."""
    command = [_gcloud_exe(), "builds", "submit", "--tag", image, f"--project={project}", "."]
    code = subprocess.call(command, cwd=str(config.ROOT))
    if code != 0:
        ui.warn(f"build failed, retrying once in {BUILD_RETRY_SECONDS}s")
        time.sleep(BUILD_RETRY_SECONDS)
        code = subprocess.call(command, cwd=str(config.ROOT))
    return code


def _deploy(manifest, image, project, api_key):
    service = manifest["service"]
    account = f"{manifest['service_account']['name']}@{project}.iam.gserviceaccount.com"
    command = [
        _gcloud_exe(), "run", "deploy", service["name"],
        f"--image={image}",
        f"--region={manifest['region']}",
        f"--project={project}",
        f"--service-account={account}",
        f"--labels=app={manifest['app']}",
        f"--set-env-vars=API_KEY={api_key}",
        "--no-allow-unauthenticated",
        f"--memory={service['memory']}",
        f"--cpu={service['cpu']}",
        f"--max-instances={service['max_instances']}",
        f"--concurrency={service['concurrency']}",
        "--min-instances=0",
        f"--timeout={service['timeout']}",
    ]
    return subprocess.call(command, cwd=str(config.ROOT))


def _point_at_service(manifest, url, api_key):
    """Write the service's address, key and model into env.yaml, with one request at a time, since
    the service runs one instance that answers one request at once."""
    values = {
        "BACKEND": "openai-compatible",
        "LLM_BASE_URL": f"{url}/v1",
        "LLM_API_KEY": api_key,
        "LLM_MODEL": manifest["model"],
        "CONTEXT_TOKENS": manifest["context_tokens"],
        "MAX_CONCURRENCY": 1,
    }
    if not ui.confirm("Use this service for pepa-sum (writes env.yaml)?"):
        ui.info(f"address {values['LLM_BASE_URL']}  ·  model {values['LLM_MODEL']}")
        ui.info(f"Its key is the service's API_KEY: gcloud run services describe {manifest['service']['name']} --region={manifest['region']} shows it.")
        ui.info("Enter these on the console's Models page, or in env.yaml, to use it later.")
        return
    config.set_values(values)
    ui.ok(f"pepa-sum now uses {values['LLM_BASE_URL']}")
    ui.info(f"Summarise with:  {config.COMMAND} summarize")


def _gcloud_exe():
    return shutil.which("gcloud") or "gcloud"


def _gcloud(*args):
    """Run a gcloud command quietly and return its output; a failure (such as a repository that
    already exists) returns what little it printed."""
    try:
        out = subprocess.run([_gcloud_exe(), *args], capture_output=True, text=True, timeout=300)
        return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
