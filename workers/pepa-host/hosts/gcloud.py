"""Build a server image on Google Cloud Build and run it on Cloud Run, which only your own Google
account may call. The deploy and remove commands use it.
"""
import shutil
import subprocess
import time

from cli import ui
from settings import IMAGES_DIR, SERVERS, SETTINGS

APIS = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
]
BUILD_RETRY_SECONDS = 90
QUIET_TIMEOUT_SECONDS = 300
SERVICE_TIMEOUT_SECONDS = 900
STEPS = [
    "Choose the Google Cloud project",
    "Enable the services, the image registry and the server's account",
    "Build the image (the model is part of it, so this takes a while)",
    "Start the server on Cloud Run",
]


def gcloud_path():
    """The gcloud command, found the way the shell would find it.

    Raises:
        SystemExit: gcloud is not installed.
    """
    found = shutil.which("gcloud")
    if found is None:
        raise SystemExit("The gcloud command is missing. Install the Google Cloud CLI, then run: gcloud auth login")
    return found


def quiet(*arguments):
    """Run a gcloud command without showing it and return what it printed, or an empty text
    when it failed, such as creating a registry that already exists."""
    try:
        finished = subprocess.run([gcloud_path(), *arguments], capture_output=True, text=True, timeout=QUIET_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return finished.stdout.strip()


def check():
    """Stop unless gcloud is installed and signed in.

    Raises:
        SystemExit: gcloud is missing or no account is signed in.
    """
    if not quiet("auth", "list", "--filter=status:ACTIVE", "--format=value(account)"):
        raise SystemExit("gcloud is not signed in. Run: gcloud auth login")


def choose_place():
    """Ask which project the server goes into, offering the projects this account can see."""
    ui.step(STEPS[0])
    current = quiet("config", "get-value", "project")
    listing = quiet("projects", "list", "--format=value(projectId)")
    projects = [line.strip() for line in listing.splitlines() if line.strip()]
    for number, project in enumerate(projects, 1):
        marker = "  (active)" if project == current else ""
        ui.info(f"{number}) {project}{marker}")
    answer = (ui.ask("Project for the server (number or name)", default=current) or "").strip()
    if not answer:
        raise SystemExit("No project chosen.")
    if answer.isdigit() and 1 <= int(answer) <= len(projects):
        return projects[int(answer) - 1]
    return answer


def build(image, project, folder):
    """Build the image on Cloud Build, retrying once: a first build right after the service is
    switched on can be refused while its permissions spread."""
    command = [gcloud_path(), "builds", "submit", "--tag", image, f"--project={project}", "."]
    code = subprocess.call(command, cwd=str(folder))
    if code != 0:
        ui.warn(f"The build failed, trying once more in {BUILD_RETRY_SECONDS} seconds")
        time.sleep(BUILD_RETRY_SECONDS)
        code = subprocess.call(command, cwd=str(folder))
    if code != 0:
        raise SystemExit("The image did not build.")


def run_command(target, size, key):
    """The gcloud run deploy command for one server: no idle instances, one at most, and only
    signed-in callers."""
    variables = {"API_KEY": key}
    variables.update(size["variables"])
    pairs = [f"{name}={value}" for name, value in variables.items()]
    command = [
        gcloud_path(), "run", "deploy", target["service"],
        f"--image={target['image']}",
        f"--region={SETTINGS['gcloud_region']}",
        f"--project={target['project']}",
        f"--service-account={target['account']}",
        f"--set-env-vars={','.join(pairs)}",
        "--no-allow-unauthenticated",
        f"--cpu={size['cpu']}",
        f"--memory={size['memory']}",
        "--min-instances=0",
        "--max-instances=1",
        f"--concurrency={size['concurrency']}",
        f"--timeout={SERVICE_TIMEOUT_SECONDS}",
    ]
    if size["gpu"]:
        command += ["--gpu=1", f"--gpu-type={size['gpu']}", "--no-gpu-zonal-redundancy", "--no-cpu-throttling"]
    return command


def deploy(server_name, project, key):
    """Put one server on Cloud Run and return where it runs.

    Returns:
        A dictionary with the server's address (ending in /v1), project and region.

    Raises:
        SystemExit: the build or the deploy failed.
    """
    region = SETTINGS["gcloud_region"]
    prefix = SETTINGS["name_prefix"]
    service = f"{prefix}-{server_name}"
    image = f"{region}-docker.pkg.dev/{project}/{prefix}/{server_name}:latest"
    target = {
        "service": service,
        "image": image,
        "project": project,
        "account": f"{prefix}-host@{project}.iam.gserviceaccount.com",
    }

    ui.step(STEPS[1])
    quiet("services", "enable", *APIS, f"--project={project}")
    quiet("artifacts", "repositories", "create", prefix, "--repository-format=docker", f"--location={region}", f"--project={project}")
    quiet("iam", "service-accounts", "create", f"{prefix}-host", "--display-name=pepa-host model server", f"--project={project}")

    ui.step(STEPS[2])
    build(image, project, IMAGES_DIR / server_name)

    ui.step(STEPS[3])
    size = SERVERS[server_name]["gcloud"]
    if subprocess.call(run_command(target, size, key)) != 0:
        raise SystemExit("Cloud Run did not start the server.")
    url = quiet("run", "services", "describe", service, f"--region={region}", f"--project={project}", "--format=value(status.url)")
    if not url:
        raise SystemExit(f"The server started, but its address could not be read. Run: gcloud run services describe {service} --region={region}")
    return {"address": f"{url}/v1", "place": project, "region": region, "service": service}


def remove(record):
    """Delete one server from Cloud Run; its image stays in the project's registry.

    Raises:
        SystemExit: Cloud Run did not delete it.
    """
    command = [gcloud_path(), "run", "services", "delete", record["service"], f"--region={record['region']}", f"--project={record['place']}", "--quiet"]
    if subprocess.call(command) != 0:
        raise SystemExit(f"Cloud Run did not delete {record['service']}.")
