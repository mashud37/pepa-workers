"""Build the family wheel: export every chosen app, write the packaging files, and pack it."""
from bundle import archive, manifest, package

from . import ui


def version_for(settings, dev):
    """The version a build carries; a development build marks itself as one."""
    if dev:
        return f"{settings['version']}.dev0"
    return settings["version"]


def export_apps(names, apps_folder, settings, commit):
    """Export each chosen app from the commit, drop what it does not ship, and return a row each."""
    rows = []
    for number, name in enumerate(names, 1):
        entry = settings["apps"][name]
        ui.info(f"[{number}/{len(names)}] {name}")
        written = archive.export(name, apps_folder / name, commit)
        gone = archive.drop(apps_folder / name, entry["leave_out"])
        rows.append({
            "app": name,
            "commit": written["commit"][:8],
            "files": written["files"],
            "left out": gone,
        })
    return rows


def run(dev=False):
    """Build one wheel holding every released app at HEAD, or every app as it is in the working
    tree for a development build.

    Raises:
        SystemExit: no app is released and this is not a development build.
    """
    settings = manifest.load()
    names = manifest.chosen_apps(settings, dev)
    if not names:
        raise SystemExit("No app is released yet. Mark one in workers.yaml, or build with --dev.")

    ui.step("Plan")
    source = "as they are in the working tree" if dev else "as committed at HEAD"
    ui.info(f"Step 1/3: Export {len(names)} app(s) {source}")
    ui.info("Step 2/3: Write the packaging files")
    ui.info("Step 3/3: Build the wheel")

    ui.step(f"Step 1/3: Export  [{len(names)} app(s)]")
    apps_folder = package.prepare(manifest.BUILD_FOLDER)
    commit = archive.working_tree_commit() if dev else archive.head_commit()
    rows = export_apps(names, apps_folder, settings, commit)
    ui.table(rows, ["app", "commit", "files", "left out"])

    ui.step("Step 2/3: Packaging files")
    version = version_for(settings, dev)
    package.write_pyproject(manifest.BUILD_FOLDER, names, version)
    ui.ok(f"{settings['package']} {version}, {len(names)} command(s)")

    ui.step("Step 3/3: Build the wheel")
    wheel = package.build_wheel(manifest.BUILD_FOLDER)
    ui.step("Done")
    ui.ok(str(wheel))
    return 0
