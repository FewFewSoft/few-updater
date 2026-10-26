from ..tools import git
from ..tools.pm.base import PackageManager
from ..tools.process import run


def upgrade(manager: PackageManager) -> None:
    manager.upgrade()
    allowed = manager.upgrade_files
    paths = git.changed_files(allowed, allow_untracked=True)
    if not paths:
        print("Dependencies already up to date")
        return
    print("Committing dependency updates...", flush=True)
    git.commit(paths, "build: update dependencies", capture_output=False)
    print("Pushing to origin/main...", flush=True)
    run("git", "push", "origin", "main", capture_output=False)

