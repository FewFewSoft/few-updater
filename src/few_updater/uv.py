"""Native uv version operations."""

import re

from .git import VERSION
from .process import Error, run


def version() -> str:
    value = run("uv", "version", "--short").strip()
    if not re.fullmatch(VERSION, value):
        raise Error(f"Expected a MAJOR.MINOR.PATCH version, got: {value}")
    return value


def next_patch(value: str) -> str:
    if not re.fullmatch(VERSION, value):
        raise Error(f"Expected a MAJOR.MINOR.PATCH version, got: {value}")
    major, minor, patch = value.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"
