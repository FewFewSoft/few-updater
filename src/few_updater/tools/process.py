"""Small subprocess wrapper shared by Git and uv."""

import shlex
import subprocess


class Error(Exception):
    """An actionable failure reported by the CLI."""


def run(*args: str, capture_output: bool = True) -> str:
    result = subprocess.run(args, capture_output=capture_output, text=True)
    if result.returncode:
        detail = (result.stderr or '').strip() or (result.stdout or '').strip()
        raise Error(f"{shlex.join(args)} failed ({result.returncode}): {detail}")
    return result.stdout or ''
