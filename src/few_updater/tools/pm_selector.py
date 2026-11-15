"""Check every supported candidate; prefer Bun only over npm."""

from .pm.base import PackageManager
from .pm.uv import Uv
from .pm.npm import Npm
from .pm.bun import Bun
from .process import Error

CANDIDATES = (Uv(), Npm(), Bun())


def select() -> PackageManager:
    matches = [manager for manager in CANDIDATES if manager.detect()]
    if any(manager.name == "bun" for manager in matches):
        matches = [manager for manager in matches if manager.name != "npm"]
    if len(matches) > 1:
        raise Error("Ambiguous project: multiple package managers detected: "
                    + ", ".join(manager.name for manager in matches))
    if not matches:
        raise Error("No supported project: need pyproject.toml + uv.lock "
                    "or package.json + package-lock.json; Bun needs package.json + "
                    "bun.lock/bun.lockb or packageManager bun@VERSION.")
    return matches[0]
