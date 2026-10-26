# CLI and package managers

## Scope and interface

Python ≥ 3.11, standard library, argparse, subprocess, no runtime dependencies.
Expose `few-updater` from the `few_updater` package. Support only uv and npm root
projects; no workspace orchestration, configuration framework, or plugin system.

```text
few-updater upgrade
few-updater bump major|minor|patch
few-updater release [--bump major|minor|patch | --no-bump]
```

Release defaults to patch. Release options are mutually exclusive. Help works
without a TTY or any external command. All operations require stdin and stdout
TTYs. No yes, force, dry-run, or non-interactive modes.

## Architecture

```text
src/few_updater/
  cli.py
  workflows/{upgrade,release,bump}.py
  tools/{git,process,pm_selector}.py
  tools/pm/{base,uv,npm}.py
```

Include package initializers. CLI handles arguments, confirmation, and dispatch;
workflows handle sequencing; tools handle commands and checks. The small shared
manager contract exposes `detect`, `upgrade`, `get_version`, `bump(level)`,
`upgrade_files`, and `release_files` (plus the executable name).
Native uv/npm commands remain explicit in their respective modules. No custom
version increment implementation or `version.py`.

## Manager commands and files

| Operation | uv | npm |
|---|---|---|
| Upgrade | `uv lock --upgrade` | `npm update` |
| Read version | `uv version --short` | Parse root `package.json` version |
| Bump | `uv version --bump LEVEL` | `npm version LEVEL --no-git-tag-version` |
| Upgrade files | `uv.lock` | `package.json`, `package-lock.json` |
| Release files | `pyproject.toml`, `uv.lock` | `package.json`, `package-lock.json` |

Versions must match strict `MAJOR.MINOR.PATCH` without leading zeroes. Read and
validate before a bump and again afterward. The resulting version must increase;
its exact value is owned by the manager. Do not calculate the next version in
Python. Native upgrade and bump commands inherit stdout/stderr.
