"""Interactive CLI arguments and dispatch."""

import argparse
import sys

from .tools import git
from .tools.process import Error
from .tools.pm.base import LEVELS
from .workflows.upgrade import upgrade
from .workflows.release import release
from .workflows.bump import bump


def confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N]: ").strip().lower() in {"y", "yes"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update dependencies and prepare releases for uv and npm projects.",
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
        "release --no-bump also accepts changes limited to version files.\n"
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
    release_parser = commands.add_parser(
        "release",
        help="Confirm a version bump, commit, tag, and push atomically.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Automatically detect uv or npm; bump patch by default, or select a level.\n"
            "Require an existing annotated release tag and a strict X.Y.Z version.\n"
            "If HEAD is already released, exit successfully without changes.\n\n"
            "After safety checks, ask for explicit user\n"
            "confirmation once (default: no), before any version changes. Run\n"
            "uv version --bump patch or npm version patch --no-git-tag-version.\n"
            "Read the resulting version and check its tag is unused. Commit changed\n"
            "files with "
            "'build: bump version'. Create an annotated Git tag X.Y.Z (no v prefix),\n"
            "with X.Y.Z as its message, then atomically push the branch and tag:\n"
            "git push --atomic origin main X.Y.Z\n\n"
            "Version files: pyproject.toml/uv.lock (uv), or\n"
            "package.json/package-lock.json (npm). Native bump, commit, and push\n"
            "output is preserved. Declining confirmation makes no changes."
        ),
        epilog=requirements,
    )
    options = release_parser.add_mutually_exclusive_group()
    options.add_argument("--bump", choices=LEVELS, default="patch",
                         help="Version increment (default: patch).")
    options.add_argument("--no-bump", action="store_true",
                         help="Publish the currently declared version without incrementing.")
    bump_parser = commands.add_parser("bump", description=(
        "Automatically detect uv or npm. Confirm once, then bump only local version files; "
        "no commit, tag or push."), epilog=requirements,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Confirm a local major, minor or patch version change.")
    bump_parser.add_argument("level", choices=LEVELS)
    args = parser.parse_args(argv)
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise Error("An interactive terminal (TTY) is required.")
        manager = git.check_preconditions(
            allow_untracked=True,
            allow_version_changes=args.command == "release" and args.no_bump,
        )
        if args.command == "upgrade":
            upgrade(manager)
        elif args.command == "bump":
            bump(manager, args.level, confirm)
        else:
            release(manager, None if args.no_bump else args.bump, confirm)
    except (Error, OSError, EOFError, KeyboardInterrupt) as exc:
        print(f"Error: {exc or 'Operation interrupted.'}", file=sys.stderr)
        print("No rollback performed. Inspect git status, git log -1 and git tag "
              "before retrying; changes, commits or tags may remain locally. "
              "After a failed push, check origin before retrying the reported push command.",
              file=sys.stderr)
        return 1
    return 0
