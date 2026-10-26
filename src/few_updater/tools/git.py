"""Git preconditions and release conventions."""

from pathlib import Path
import re
import shutil

from .process import Error, run
from .pm_selector import select
from .pm.base import VERSION, PackageManager


def check_preconditions(*, allow_untracked: bool = False,
                        allow_version_changes: bool = False) -> PackageManager:
    if shutil.which("git") is None:
        raise Error("Required executable not found: git")
    root = run("git", "rev-parse", "--show-toplevel").strip()
    if Path(root).resolve() != Path.cwd().resolve():
        raise Error("Run few-updater from the Git repository root.")
    if run("git", "symbolic-ref", "--short", "HEAD").strip() != "main":
        raise Error("Current branch must be main.")
    manager = select()
    untracked = "no" if allow_untracked else "all"
    if allow_version_changes:
        changed_files(manager.release_files, allow_untracked=allow_untracked)
    elif run("git", "status", "--porcelain", f"--untracked-files={untracked}"):
        raise Error("Git index and working tree must be clean.")
    if shutil.which(manager.name) is None:
        raise Error(f"Required executable not found: {manager.name}")
    run("git", "remote", "get-url", "origin")
    run("git", "fetch", "origin")
    if not run("git", "ls-remote", "--heads", "origin", "refs/heads/main").strip():
        raise Error("Remote branch origin/main does not exist.")
    remote = run("git", "rev-parse", "--verify", "refs/remotes/origin/main").strip()
    if run("git", "rev-parse", "HEAD").strip() != remote:
        raise Error("HEAD must match origin/main exactly; synchronize manually.")
    return manager


def already_released() -> bool:
    description = run("git", "describe").strip()
    if re.fullmatch(VERSION, description):
        return True
    if re.fullmatch(VERSION + r"-[1-9][0-9]*-g[0-9a-f]+", description):
        return False
    raise Error(f"Unexpected git describe format: {description}")


def check_tag_available(version: str) -> None:
    ref = f"refs/tags/{version}"
    if run("git", "tag", "--list", version).strip():
        raise Error(f"Target tag already exists: {version}")
    if run("git", "ls-remote", "--tags", "origin", ref).strip():
        raise Error(f"Target tag already exists on origin: {version}")


def changed_files(allowed: set[str], *, allow_untracked: bool = False) -> list[str]:
    # Disable rename detection so each path is represented independently.
    untracked = "no" if allow_untracked else "all"
    entries = run("git", "status", "--porcelain", "-z", "--no-renames",
                  f"--untracked-files={untracked}").split("\0")
    paths = [entry[3:] for entry in entries if entry]
    unexpected = set(paths) - allowed
    if unexpected:
        raise Error(f"Unexpected changed files: {', '.join(sorted(unexpected))}")
    return paths


def commit(paths: list[str], message: str, *, capture_output: bool = True) -> None:
    if not paths:
        raise Error("No version files changed; cannot create a release commit.")
    run("git", "add", "--", *paths)
    run("git", "commit", "-m", message, capture_output=capture_output)
