"""Interactive upgrade and release workflows."""

import argparse
import sys

from . import git, npm, project, uv
from .process import Error, run


def confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N]: ").strip().lower() in {"y", "yes"}


def upgrade(manager: str = "uv") -> None:
    command = ("uv", "lock", "--upgrade") if manager == "uv" else ("npm", "update")
    run(*command, capture_output=False)
    allowed = {"uv.lock"} if manager == "uv" else project.FILES[manager]
    paths = git.changed_files(allowed, allow_untracked=True)
    if not paths:
        print("Dependencies already up to date")
        return
    print("Committing dependency updates...", flush=True)
    git.commit(paths, "build: update dependencies", capture_output=False)
    print("Pushing to origin/main...", flush=True)
    run("git", "push", "origin", "main", capture_output=False)


def release(manager: str = "uv") -> None:
    if git.already_released():
        print("Release already performed")
        return
    read_version = uv.version if manager == "uv" else npm.version
    current = read_version()
    target = uv.next_patch(current)
    git.check_tag_available(target)
    print(f"Current version: {current}\nNext version:    {target}\n")
    if not confirm("Proceed with release?"):
        return
    print("Bumping version...", flush=True)
    command = (("uv", "version", "--bump", "patch") if manager == "uv"
               else ("npm", "version", "patch", "--no-git-tag-version"))
    run(*command, capture_output=False)
    obtained = read_version()
    if obtained != target:
        raise Error(f"Expected version {target}, got {obtained}.")
    paths = git.changed_files(project.FILES[manager], allow_untracked=True)
    print("Committing version bump...", flush=True)
    git.commit(paths, "build: bump version", capture_output=False)
    print(f"Creating annotated tag {target}...", flush=True)
    run("git", "tag", "-a", target, "-m", target)
    print(f"Pushing main and {target} atomically...", flush=True)
    run("git", "push", "--atomic", "origin", "main", target, capture_output=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update dependencies and prepare patch releases for uv and npm projects.",
        epilog="Run a command with --help for its workflow and Git requirements.",
    )
    requirements = (
        "Detection: pyproject.toml + uv.lock selects uv;\n"
        "package.json + package-lock.json selects npm.\n"
        "Both complete sets, or neither, are an error.\n\n"
        "Requirements: run in an interactive terminal (TTY) at the Git repository\n"
        "root, on main. Git and the detected package manager must be available.\n"
        "The index and tracked working-tree files must be clean. Untracked files\n"
        "are allowed and never staged. origin and origin/main must exist; after\n"
        "git fetch origin, HEAD must match origin/main exactly.\n\n"
        "Failures stop the workflow without automatic rollback."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "upgrade",
        help="Update dependencies, then automatically commit and push changes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Automatically detect uv or npm and update dependencies within existing\n"
            "version constraints using uv lock --upgrade or npm update.\n\n"
            "If dependency files change, explicitly stage only uv.lock (uv), or\n"
            "modified package.json/package-lock.json files (npm), commit with\n"
            "'build: update dependencies', and run git push origin main.\n"
            "No changes means success without a commit or push. No confirmation\n"
            "required and no diff displayed. Native command output is preserved."
        ),
        epilog=requirements,
    )
    commands.add_parser(
        "release",
        help="Confirm a patch bump, commit, tag, and push atomically.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Automatically detect uv or npm and propose the next patch version.\n"
            "Require an existing annotated release tag and a strict X.Y.Z version.\n"
            "If HEAD is already released, exit successfully without changes.\n\n"
            "After checking that the target tag is unused, ask for explicit user\n"
            "confirmation once (default: no), before any version changes. Run\n"
            "uv version --bump patch or npm version patch --no-git-tag-version.\n"
            "Verify the version and commit only changed version files with\n"
            "'build: bump version'. Create an annotated Git tag X.Y.Z (no v prefix),\n"
            "with X.Y.Z as its message, then atomically push the branch and tag:\n"
            "git push --atomic origin main X.Y.Z\n\n"
            "Version files: pyproject.toml/uv.lock (uv), or\n"
            "package.json/package-lock.json (npm). Native bump, commit, and push\n"
            "output is preserved. Declining confirmation makes no changes."
        ),
        epilog=requirements,
    )
    args = parser.parse_args(argv)
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise Error("An interactive terminal (TTY) is required.")
        manager = git.check_preconditions(allow_untracked=True)
        if args.command == "upgrade":
            upgrade(manager)
        else:
            release(manager)
    except (Error, OSError, EOFError, KeyboardInterrupt) as exc:
        print(f"Error: {exc or 'Operation interrupted.'}", file=sys.stderr)
        print("No rollback performed. Inspect git status, git log -1 and git tag "
              "before retrying; changes, commits or tags may remain locally. "
              "After a failed push, check origin before retrying the reported push command.",
              file=sys.stderr)
        return 1
    return 0
