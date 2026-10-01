"""Export each app's tracked files at one commit, so uncommitted work never reaches a wheel."""
import shutil
import subprocess
import zipfile

from bundle import manifest


def resolve_ref(name, ref):
    """The commit one app's ref points at.

    Raises:
        SystemExit: the app is not a repository here, or has no such ref.
    """
    folder = manifest.app_folder(name)
    if not (folder / ".git").is_dir():
        raise SystemExit(f"{name} is not a git repository at {folder}.")
    asked = ["git", "-C", str(folder), "rev-parse", "--verify", f"{ref}^{{commit}}"]
    found = subprocess.run(asked, capture_output=True, text=True)
    if found.returncode != 0:
        raise SystemExit(f"{name} has no ref {ref}.")
    return found.stdout.strip()


def export(name, ref, into):
    """Write one app's tracked files at a ref into a folder.

    Returns:
        dict with "commit" and "files", the number of files written.
    """
    commit = resolve_ref(name, ref)
    into.mkdir(parents=True, exist_ok=True)
    archive = into.parent / f"{name}.zip"
    packing = ["git", "-C", str(manifest.app_folder(name)), "archive", "--format=zip", "-o", str(archive), commit]
    subprocess.run(packing, check=True)
    with zipfile.ZipFile(archive) as packed:
        packed.extractall(into)
    archive.unlink()
    written = [path for path in into.rglob("*") if path.is_file()]
    return {"commit": commit, "files": len(written)}


def drop(folder, leave_out):
    """Remove the files and folders an app does not ship, and say how many went."""
    gone = 0
    for name in leave_out:
        target = folder / name
        if target.is_dir():
            shutil.rmtree(target)
            gone += 1
        elif target.exists():
            target.unlink()
            gone += 1
    return gone
