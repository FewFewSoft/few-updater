"""Detect the two supported project layouts."""

from pathlib import Path

from .process import Error

FILES = {
    'uv': {'pyproject.toml', 'uv.lock'},
    'npm': {'package.json', 'package-lock.json'},
}


def detect() -> str:
    matches = [manager for manager, files in FILES.items()
               if all(Path(filename).is_file() for filename in files)]
    if len(matches) == 2:
        raise Error('Ambiguous project: both uv and npm file sets are present.')
    if not matches:
        raise Error('No supported project: need pyproject.toml + uv.lock '
                    'or package.json + package-lock.json.')
    return matches[0]
