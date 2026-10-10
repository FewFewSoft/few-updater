"""Read the root npm package version without changing the project."""

import json
from pathlib import Path
import re

from .git import VERSION
from .process import Error


def version() -> str:
    try:
        package = json.loads(Path('package.json').read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise Error(f'Invalid package.json: {exc}') from exc
    value = package.get('version') if isinstance(package, dict) else None
    if not isinstance(value, str) or not re.fullmatch(VERSION, value):
        raise Error(f'Expected a MAJOR.MINOR.PATCH version, got: {value}')
    return value
