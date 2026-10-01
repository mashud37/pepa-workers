"""Write the wheel's packaging files around the exported apps and build the wheel."""
import shutil
import subprocess
import sys

from bundle import manifest

PACKAGE_NAME = "pepa_workers"
ENTRY_POINT = "pepa_workers.launch:main"
LOGO_PATH = 'src="docs/logo.png"'
LOGO_URL = 'src="https://raw.githubusercontent.com/mashud37/pepa-workers/master/docs/logo.png"'
CARRIED_FILES = [
    "LICENSE",
    "README.md",
]


def requirements_of(name):
    """The package names in one app's requirements.txt, with comments and blank lines left out."""
    path = manifest.app_folder(name) / "requirements.txt"
    if not path.exists():
        return []
    wanted = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.split("#")[0].strip()
        if text:
            wanted.append(text)
    return wanted


def extras_for(names):
    """Each app's own dependencies under its extra, plus "all", which is every one of them."""
    settings = manifest.load()
    extras = {}
    everything = []
    for name in names:
        wanted = requirements_of(name)
        extras[settings["apps"][name]["extra"]] = sorted(set(wanted))
        everything.extend(wanted)
    extras["all"] = sorted(set(everything))
    return extras


def toml_list(values):
    """A TOML list with one value per line, as the style rules ask for."""
    if not values:
        return "[]"
    lines = [f'    "{value}",' for value in values]
    return "[\n" + "\n".join(lines) + "\n]"


def metadata_lines(settings, version):
    """The pyproject header: how the wheel is built and what the package says about itself."""
    return [
        "[build-system]",
        'requires = ["setuptools>=77"]',
        'build-backend = "setuptools.build_meta"',
        "",
        "[project]",
        f'name = "{settings["package"]}"',
        f'version = "{version}"',
        f'description = "{settings["summary"]}"',
        'readme = "README.md"',
        f'requires-python = "{settings["python"]}"',
        f'license = "{settings["license"]}"',
        'license-files = ["LICENSE"]',
        f"dependencies = {toml_list(settings['base'])}",
    ]


def write_pyproject(build_folder, names, version):
    """Write the wheel's pyproject.toml: metadata, one extra per app, one command per app."""
    settings = manifest.load()
    lines = metadata_lines(settings, version)
    lines.extend(["", "[project.optional-dependencies]"])
    extras = extras_for(names)
    for extra in sorted(extras):
        lines.append(f"{extra} = {toml_list(extras[extra])}")
    lines.extend(["", "[project.scripts]"])
    for name in names:
        lines.append(f'{name} = "{ENTRY_POINT}"')
    lines.extend([
        "",
        "[tool.setuptools]",
        f'packages = ["{PACKAGE_NAME}"]',
        "include-package-data = true",
        "",
        "[tool.setuptools.package-data]",
        f'{PACKAGE_NAME} = ["apps/**/*"]',
    ])
    (build_folder / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare(build_folder):
    """Empty the build folder, put the launcher and the carried files in it, and point the
    README's logo at its public address, since PyPI cannot follow a path inside the repository.

    Returns:
        the folder the exported apps go into.
    """
    if build_folder.exists():
        shutil.rmtree(build_folder)
    package_folder = build_folder / PACKAGE_NAME
    apps_folder = package_folder / "apps"
    apps_folder.mkdir(parents=True)
    (package_folder / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy(manifest.ROOT / "bundle" / "launch.py", package_folder / "launch.py")
    for name in CARRIED_FILES:
        shutil.copy(manifest.ROOT / name, build_folder / name)
    readme = build_folder / "README.md"
    text = readme.read_text(encoding="utf-8")
    readme.write_text(text.replace(LOGO_PATH, LOGO_URL), encoding="utf-8")
    return apps_folder


def build_wheel(build_folder):
    """Build the wheel from the prepared folder and say where it landed.

    Raises:
        SystemExit: the build failed, or wrote no wheel.
    """
    asked = [sys.executable, "-m", "build", "--wheel", "--outdir", str(manifest.DIST_FOLDER)]
    built = subprocess.run(asked, cwd=str(build_folder))
    if built.returncode != 0:
        raise SystemExit("The wheel did not build.")
    wheels = sorted(manifest.DIST_FOLDER.glob("*.whl"))
    if not wheels:
        raise SystemExit("The build wrote no wheel.")
    return wheels[-1]
