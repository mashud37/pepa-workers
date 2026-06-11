"""Deploy the summariser service to Cloud Run.

Prompts for the GCP project (never silently uses the active gcloud config),
then runs the platform's deploy script — deploy.ps1 on Windows, deploy.sh
elsewhere. Both are the same two-pass deploy: build the image, deploy the
service, then write the resulting BASE_URL back into env.yaml. Region defaults
to europe-west1; gcloud_app.yaml records the same config declaratively.
"""
import os
import shutil
import subprocess

import config
from cli import ui


def run():
    ui.header("Deploy summariser service")
    if not shutil.which("gcloud"):
        raise SystemExit("gcloud CLI not found — install it first (run: python manage.py install).")

    project = _select_project()
    ui.ok(f"deploying to project: {project}  (region europe-west1)")

    cmd = _deploy_command()
    env = dict(os.environ, PROJECT=project)
    ui.info(f"Running {'deploy.ps1' if os.name == 'nt' else 'deploy.sh'} "
            "(builds the image, deploys, writes BASE_URL).")
    return subprocess.call(cmd, cwd=str(config.ROOT), env=env)


def _select_project():
    current = _gcloud("config", "get-value", "project")
    listing = _gcloud("projects", "list", "--format=value(projectId)")
    projects = [p for p in listing.splitlines() if p.strip()]

    ui.step("Select GCP project")
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


def _gcloud(*args):
    exe = shutil.which("gcloud") or "gcloud"
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except Exception:
        return ""


def _deploy_command():
    if os.name == "nt":
        script = config.ROOT / "deploy.ps1"
        if not script.exists():
            raise SystemExit("deploy.ps1 not found.")
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]

    script = config.ROOT / "deploy.sh"
    if not script.exists():
        raise SystemExit("deploy.sh not found.")
    if not shutil.which("bash"):
        raise SystemExit("bash not found — run `bash deploy.sh` from a shell that has it.")
    return ["bash", str(script)]
