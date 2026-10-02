"""Export each app's files from one commit: HEAD for a release, a snapshot of the working tree for a development build."""
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

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


def working_tree_commit():
    """A commit of the working tree as it is now, made without touching HEAD, the branch or the index,
    so a development build can test work before it is committed."""
    index_file = Path(tempfile.gettempdir()) / "pepa-workers-snapshot.index"
    environment = dict(os.environ, GIT_INDEX_FILE=str(index_file))
    git = ["git", "-C", str(manifest.ROOT)]
    subprocess.run(git + ["read-tree", "HEAD"], env=environment, check=True)
    subprocess.run(git + ["add", "--all"], env=environment, check=True)
    tree = subprocess.run(git + ["write-tree"], env=environment, capture_output=True, text=True, check=True)
    made = subprocess.run(git + ["commit-tree", tree.stdout.strip(), "-p", "HEAD", "-m", "Working tree snapshot"], capture_output=True, text=True, check=True)
    index_file.unlink()
    return made.stdout.strip()


def export(name, into, commit):
    """Write one app's files, as they are in the given commit, into a folder.

    Returns:
        dict with "commit" and "files", the number of files written.
    """
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
