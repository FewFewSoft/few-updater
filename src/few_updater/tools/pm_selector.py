"""Check every supported candidate; never prefer the first match."""

from .pm.base import PackageManager
from .pm.uv import Uv
from .pm.npm import Npm
from .process import Error

CANDIDATES = (Uv(), Npm())


def select() -> PackageManager:
    matches = [manager for manager in CANDIDATES if manager.detect()]
    if len(matches) > 1:
        raise Error("Ambiguous project: multiple package managers detected: "
                    + ", ".join(manager.name for manager in matches))
    if not matches:
        raise Error("No supported project: need pyproject.toml + uv.lock "
                    "or package.json + package-lock.json.")
    return matches[0]
