"""Confirmed version bump and atomic Git publication."""

from collections.abc import Callable
from ..tools import git
from ..tools.pm.base import PackageManager
from ..tools.process import run
from .bump import apply_bump


def release(manager: PackageManager, level: str | None,
            confirm: Callable[[str], bool]) -> None:
    if git.already_released():
        print("Release already performed")
        return
    current = manager.get_version()
    if level is None:
        git.check_tag_available(current)
    print(f"Current version: {current}\nBump: {level or 'none'}\n")
    if not confirm("Proceed with release?"):
        return
    target = apply_bump(manager, level, current) if level else current
    if level:
        git.check_tag_available(target)
    paths = git.changed_files(manager.release_files, allow_untracked=True)
    if paths:
        print("Committing version bump...", flush=True)
        git.commit(paths, "build: bump version", capture_output=False)
    print(f"Creating annotated tag {target}...", flush=True)
    run("git", "tag", "-a", target, "-m", target)
    print(f"Pushing main and {target} atomically...", flush=True)
    run("git", "push", "--atomic", "origin", "main", target, capture_output=False)
