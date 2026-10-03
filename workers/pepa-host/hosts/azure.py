"""Build a server image in an Azure container registry and run it on Azure Container Apps, which
checks the server's own key. The deploy and remove commands use it.
"""
import shutil
import subprocess

from cli import ui
from settings import IMAGES_DIR, SERVERS, SETTINGS

PROVIDERS = [
    "Microsoft.App",
    "Microsoft.ContainerRegistry",
]
QUIET_TIMEOUT_SECONDS = 600
GPU_PROFILE_NAME = "gpu"
STEPS = [
    "Choose the Azure subscription",
    "Register the services, the resource group, the registry and the environment",
    "Build the image (the model is part of it, so this takes a while)",
    "Start the server on Container Apps",
]


def az_path():
    """The az command, found the way the shell would find it.

    Raises:
        SystemExit: az is not installed.
    """
    found = shutil.which("az")
    if found is None:
        raise SystemExit("The az command is missing. Install the Azure CLI, then run: az login")
    return found


def quiet(*arguments):
    """Run an az command without showing it and return what it printed, or an empty text when it
    failed, such as looking up an app that does not exist yet."""
    try:
        finished = subprocess.run([az_path(), *arguments], capture_output=True, text=True, timeout=QUIET_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if finished.returncode != 0:
        return ""
    return finished.stdout.strip()


def shown(*arguments):
    """Run an az command where its output is seen.

    Raises:
        SystemExit: the command failed.
    """
    if subprocess.call([az_path(), *arguments]) != 0:
        raise SystemExit(f"This step failed: az {' '.join(arguments[:2])}")


def check():
    """Stop unless az is installed and signed in.

    Raises:
        SystemExit: az is missing or no account is signed in.
    """
    if not quiet("account", "show", "--query", "id", "-o", "tsv"):
        raise SystemExit("az is not signed in. Run: az login")


def choose_place():
    """Ask which subscription pays for the server, offering those this account can use."""
    ui.step(STEPS[0])
    current = quiet("account", "show", "--query", "id", "-o", "tsv")
    listing = quiet("account", "list", "--query", "[].[id, name]", "-o", "tsv")
    subscriptions = []
    for line in listing.splitlines():
        if "\t" in line:
            subscriptions.append(line.split("\t", 1))
    for number, (subscription, name) in enumerate(subscriptions, 1):
        marker = "  (active)" if subscription == current else ""
        ui.info(f"{number}) {name}  {subscription}{marker}")
    answer = (ui.ask("Subscription for the server (number or id)", default=current) or "").strip()
    if not answer:
        raise SystemExit("No subscription chosen.")
    if answer.isdigit() and 1 <= int(answer) <= len(subscriptions):
        return subscriptions[int(answer) - 1][0]
    return answer


def registry_name(subscription):
    """A registry name no other Azure customer holds: registry names are global, so part of the
    subscription id goes into it."""
    return SETTINGS["name_prefix"] + subscription.replace("-", "")[:12]


def prepare(subscription, group, size):
    """Create the resource group, registry and environment once; each later deploy finds them there."""
    region = SETTINGS["azure_region"]
    for provider in PROVIDERS:
        quiet("provider", "register", "--namespace", provider, "--wait", "--subscription", subscription)
    quiet("group", "create", "--name", group, "--location", region, "--subscription", subscription)
    registry = registry_name(subscription)
    if not quiet("acr", "show", "--name", registry, "--subscription", subscription, "--query", "name", "-o", "tsv"):
        shown("acr", "create", "--name", registry, "--resource-group", group, "--sku", "Basic", "--subscription", subscription)
    if not quiet("containerapp", "env", "show", "--name", group, "--resource-group", group, "--subscription", subscription, "--query", "name", "-o", "tsv"):
        shown("containerapp", "env", "create", "--name", group, "--resource-group", group, "--location", region, "--enable-workload-profiles", "--logs-destination", "none", "--subscription", subscription)
    if size["profile"] != "Consumption":
        quiet("containerapp", "env", "workload-profile", "add", "--name", group, "--resource-group", group, "--workload-profile-name", GPU_PROFILE_NAME, "--workload-profile-type", size["profile"], "--subscription", subscription)
    return registry


def start(target, size, key):
    """Create the container app, or point an existing one at the new image and key."""
    variables = ["API_KEY=secretref:api-key"]
    for name, value in size["variables"].items():
        variables.append(f"{name}={value}")
    profile = GPU_PROFILE_NAME if size["profile"] != "Consumption" else "Consumption"
    where = ["--name", target["app"], "--resource-group", target["group"], "--subscription", target["subscription"]]
    if quiet("containerapp", "show", *where, "--query", "name", "-o", "tsv"):
        shown("containerapp", "secret", "set", *where, "--secrets", f"api-key={key}")
        shown("containerapp", "update", *where, "--image", target["image"], "--cpu", size["cpu"], "--memory", size["memory"], "--set-env-vars", *variables)
        return
    shown(
        "containerapp", "create", *where,
        "--environment", target["group"],
        "--image", target["image"],
        "--registry-server", f"{target['registry']}.azurecr.io",
        "--registry-identity", "system",
        "--workload-profile-name", profile,
        "--target-port", "8080",
        "--ingress", "external",
        "--min-replicas", "0",
        "--max-replicas", "1",
        "--cpu", size["cpu"],
        "--memory", size["memory"],
        "--secrets", f"api-key={key}",
        "--env-vars", *variables,
    )


def deploy(server_name, subscription, key):
    """Put one server on Azure Container Apps and return where it runs.

    Returns:
        A dictionary with the server's address (ending in /v1), subscription and region.

    Raises:
        SystemExit: a step failed.
    """
    group = SETTINGS["name_prefix"]
    app = f"{group}-{server_name}"
    size = SERVERS[server_name]["azure"]

    ui.step(STEPS[1])
    registry = prepare(subscription, group, size)
    image = f"{registry}.azurecr.io/{group}/{server_name}:latest"

    ui.step(STEPS[2])
    folder = IMAGES_DIR / server_name
    built = subprocess.call([az_path(), "acr", "build", "--registry", registry, "--image", f"{group}/{server_name}:latest", "--subscription", subscription, "."], cwd=str(folder))
    if built != 0:
        raise SystemExit("The image did not build.")

    ui.step(STEPS[3])
    target = {
        "app": app,
        "image": image,
        "registry": registry,
        "subscription": subscription,
        "group": group,
    }
    start(target, size, key)
    domain = quiet("containerapp", "show", "--name", app, "--resource-group", group, "--subscription", subscription, "--query", "properties.configuration.ingress.fqdn", "-o", "tsv")
    if not domain:
        raise SystemExit(f"The server started, but its address could not be read. Run: az containerapp show --name {app} --resource-group {group}")
    return {"address": f"https://{domain}/v1", "place": subscription, "region": SETTINGS["azure_region"], "service": app, "group": group}


def remove(record):
    """Delete one server from Container Apps.

    Raises:
        SystemExit: Azure did not delete it.
    """
    shown("containerapp", "delete", "--name", record["service"], "--resource-group", record["group"], "--subscription", record["place"], "--yes")


def remove_everything(record):
    """Delete the resource group with its registry and environment, which the registry's daily
    charge makes worth doing once no server is left."""
    shown("group", "delete", "--name", record["group"], "--subscription", record["place"], "--yes")
