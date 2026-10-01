"""Install the newest wheel into a fresh environment and run every bundled app's command once."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bundle import manifest

from . import ui

TEST_ENVIRONMENT = Path(tempfile.gettempdir()) / "pepa-workers-testenv"
HELP_SECONDS = 180


def newest_wheel():
    """The wheel a smoke test runs against.

    Raises:
        SystemExit: nothing has been built yet.
    """
    wheels = sorted(manifest.DIST_FOLDER.glob("*.whl"))
    if not wheels:
        raise SystemExit("No wheel in dist. Build one first: python manage.py bundle --dev")
    return wheels[-1]


def fresh_environment():
    """Make an empty virtual environment for the test and return the python inside it."""
    if TEST_ENVIRONMENT.exists():
        shutil.rmtree(TEST_ENVIRONMENT)
    subprocess.run([sys.executable, "-m", "venv", str(TEST_ENVIRONMENT)], check=True)
    if os.name == "nt":
        return TEST_ENVIRONMENT / "Scripts" / "python.exe"
    return TEST_ENVIRONMENT / "bin" / "python"


def install_wheel(python_path, wheel):
    """Install the wheel and every dependency it names into the test environment.

    Raises:
        SystemExit: the install failed.
    """
    asked = [str(python_path), "-m", "pip", "install", "--quiet", str(wheel)]
    if subprocess.run(asked).returncode != 0:
        raise SystemExit(f"Could not install {wheel.name}.")


def command_path(name):
    """Where one app's command lands inside the test environment."""
    if os.name == "nt":
        return TEST_ENVIRONMENT / "Scripts" / f"{name}.exe"
    return TEST_ENVIRONMENT / "bin" / name


def help_row(name):
    """Run one app's command with --help and report how it ended."""
    path = command_path(name)
    if not path.exists():
        return {"app": name, "command": "missing", "exit": "", "first line": ""}
    try:
        ran = subprocess.run([str(path), "--help"], capture_output=True, text=True, timeout=HELP_SECONDS)
    except subprocess.TimeoutExpired:
        return {"app": name, "command": "hung", "exit": "", "first line": ""}
    printed = (ran.stdout + ran.stderr).strip().splitlines()
    return {
        "app": name,
        "command": "ran" if ran.returncode == 0 else "failed",
        "exit": ran.returncode,
        "first line": printed[0][:60] if printed else "",
    }


def run():
    """Install the newest wheel in a fresh environment and run every app's --help once."""
    settings = manifest.load()
    wheel = newest_wheel()
    names = sorted(settings["apps"])

    ui.step("Plan")
    ui.info("Step 1/2: Install the wheel in a fresh environment")
    ui.info(f"Step 2/2: Run --help for {len(names)} app(s)")

    ui.step("Step 1/2: Install")
    ui.info(wheel.name)
    python_path = fresh_environment()
    install_wheel(python_path, wheel)
    ui.ok(f"installed into {TEST_ENVIRONMENT}")

    ui.step(f"Step 2/2: Commands  [{len(names)} app(s)]")
    rows = []
    for number, name in enumerate(names, 1):
        ui.info(f"[{number}/{len(names)}] {name} --help")
        rows.append(help_row(name))
    ui.table(rows, ["app", "command", "exit", "first line"])

    failed = [row for row in rows if row["command"] != "ran"]
    if failed:
        ui.error(f"{len(failed)} of {len(rows)} command(s) did not run")
        return 1
    ui.ok(f"{len(rows)} command(s) ran")
    return 0
