"""Native Bun operations for a root package."""

import json
from pathlib import Path

from .base import PackageManager
from .npm import Npm
from ..process import Error, run


class Bun(PackageManager):
    name = "bun"
    upgrade_files = {"package.json", "bun.lock", "bun.lockb"}
    release_files = {"package.json", "bun.lock", "bun.lockb"}

    def detect(self) -> bool:
        manifest = Path("package.json")
        if not manifest.is_file():
            return False
        if any(Path(path).is_file() for path in ("bun.lock", "bun.lockb")):
            return True
        try:
            package = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            return False
        marker = package.get("packageManager") if isinstance(package, dict) else None
        return isinstance(marker, str) and marker.startswith("bun@") and bool(marker[4:])

    def get_version(self) -> str:
        return Npm().get_version()

    def _locks(self) -> set[str]:
        return {path for path in ("bun.lock", "bun.lockb") if Path(path).is_file()}

    def _check_locks(self, before: set[str]) -> None:
        after = self._locks()
        if not after or after - before:
            raise Error("Bun created or migrated a lockfile. Track the intended Bun lockfile "
                        "manually and retry; new untracked files are never staged.")

    def upgrade(self) -> None:
        before = self._locks()
        run("bun", "update", capture_output=False)
        self._check_locks(before)

    def bump(self, level: str) -> None:
        before = self._locks()
        run("bun", "pm", "version", level, "--no-git-tag-version", capture_output=False)
        run("bun", "install", "--lockfile-only", capture_output=False)
        self._check_locks(before)
