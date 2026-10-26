"""Native npm operations for a root package."""

import json
from pathlib import Path
from .base import PackageManager, validate_version
from ..process import Error, run


class Npm(PackageManager):
    name = "npm"
    upgrade_files = {"package.json", "package-lock.json"}
    release_files = {"package.json", "package-lock.json"}

    def detect(self) -> bool:
        return all(Path(path).is_file() for path in self.release_files)

    def upgrade(self) -> None:
        run("npm", "update", capture_output=False)

    def get_version(self) -> str:
        try:
            package = json.loads(Path("package.json").read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise Error(f"Invalid package.json: {exc}") from exc
        return validate_version(package.get("version") if isinstance(package, dict) else None)

    def bump(self, level: str) -> None:
        run("npm", "version", level, "--no-git-tag-version", capture_output=False)
