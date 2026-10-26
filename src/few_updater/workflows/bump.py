"""A confirmed local version change, without Git publication."""

from collections.abc import Callable
from ..tools import git
from ..tools.pm.base import PackageManager
from ..tools.process import Error


def apply_bump(manager: PackageManager, level: str, current: str) -> str:
    print("Bumping version...", flush=True)
    manager.bump(level)
    obtained = manager.get_version()
    if tuple(map(int, obtained.split('.'))) <= tuple(map(int, current.split('.'))):
        raise Error(f"Version did not increase: {current} -> {obtained}.")
    git.changed_files(manager.release_files, allow_untracked=True)
    return obtained


def bump(manager: PackageManager, level: str, confirm: Callable[[str], bool]) -> None:
    current = manager.get_version()
    print(f"Current version: {current}\nBump: {level}\n")
    if confirm("Proceed with version bump?"):
        obtained = apply_bump(manager, level, current)
        print(f"Version: {obtained}")
