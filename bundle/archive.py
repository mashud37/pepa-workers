"""Export each app's committed files at HEAD, so uncommitted work never reaches a wheel."""
import shutil
import subprocess
import zipfile

from bundle import manifest


def head_commit():
    """The commit this repository's HEAD points at.

    Raises:
        SystemExit: the family folder is not a git repository with a commit.
    """
    asked = ["git", "-C", str(manifest.ROOT), "rev-parse", "--verify", "HEAD^{commit}"]
    found = subprocess.run(asked, capture_output=True, text=True)
    if found.returncode != 0:
        raise SystemExit(f"{manifest.ROOT} is not a git repository with a commit.")
    return found.stdout.strip()


def export(name, into):
    """Write one app's committed files at HEAD into a folder.

    Returns:
        dict with "commit" and "files", the number of files written.
    """
    commit = head_commit()
    into.mkdir(parents=True, exist_ok=True)
    archive = into.parent / f"{name}.zip"
    packing = ["git", "-C", str(manifest.ROOT), "archive", "--format=zip", "-o", str(archive), f"{commit}:workers/{name}"]
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
