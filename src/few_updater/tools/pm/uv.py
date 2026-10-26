"""Native uv operations."""

from pathlib import Path
from .base import PackageManager, validate_version
from ..process import run


class Uv(PackageManager):
    name = "uv"
    upgrade_files = {"uv.lock"}
    release_files = {"pyproject.toml", "uv.lock"}

    def detect(self) -> bool:
        return all(Path(path).is_file() for path in self.release_files)

    def upgrade(self) -> None:
        run("uv", "lock", "--upgrade", capture_output=False)

    def get_version(self) -> str:
        return validate_version(run("uv", "version", "--short").strip())

    def bump(self, level: str) -> None:
        run("uv", "version", "--bump", level, capture_output=False)
