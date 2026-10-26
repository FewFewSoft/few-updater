"""Small contract for the two supported package managers."""

from abc import ABC, abstractmethod
import re

from ..process import Error

VERSION = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
LEVELS = ("major", "minor", "patch")


def validate_version(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(VERSION, value):
        raise Error(f"Expected a MAJOR.MINOR.PATCH version, got: {value}")
    return value


class PackageManager(ABC):
    name: str
    upgrade_files: set[str]
    release_files: set[str]

    @abstractmethod
    def detect(self) -> bool: ...

    @abstractmethod
    def upgrade(self) -> None: ...

    @abstractmethod
    def get_version(self) -> str: ...

    @abstractmethod
    def bump(self, level: str) -> None: ...
