# few-updater

A minimal CLI for dependency updates and patch releases, supporting Python projects with **uv** and Node.js projects with **npm**.

Automates dependency updates, version bumps, Git commits, and pushes while keeping the workflow predictable.

Python ≥ 3.11 · Standard library only · Interactive releases

## Installation

Requires Git, [uv](https://docs.astral.sh/uv/), and npm for Node.js projects.

```bash
uv tool install .
```

## Usage

Run from the root of a Git repository on `main`.

```bash
few-updater upgrade
few-updater release
```

### Upgrade

Updates dependencies within the project's existing version constraints:

- **uv:** `uv lock --upgrade`
- **npm:** `npm update`

If dependency files change, automatically commits them as `build: update dependencies` and pushes to `origin/main`.

No confirmation required.

### Release

Creates the next patch release (`1.2.3 → 1.2.4`):

- Bumps the project version using uv or npm.
- Commits the version changes as `build: bump version`.
- Creates an annotated Git tag (`X.Y.Z`).
- Atomically pushes the commit and tag to `origin`.

Requires confirmation before making changes.

## Requirements & limitations

- Automatically detects uv or npm from the project files.
- Requires a clean Git index and tracked working tree; untracked files are allowed.
- Requires `main` to match `origin/main`.
- Requires an existing annotated release tag for `release`.
- Supports single-project repositories; workspaces are not supported.
- Does not automatically pull, merge, rebase, or roll back changes.
- Does not run application tests or publish packages.

See [SPEC.md](SPEC.md) for detailed behavior, safety checks, and failure handling.

## Development

```bash
uv run python -m unittest discover -s tests
```
