# CLI and package managers

## Scope and interface

Python ≥ 3.11, standard library, argparse, subprocess, no runtime dependencies.
Expose `few-updater` from the `few_updater` package. Support uv, npm and bun root
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
  tools/pm/{base,uv,npm,bun}.py
```

Include package initializers. CLI handles arguments, confirmation, and dispatch;
workflows handle sequencing; tools handle commands and checks. The small shared
manager contract exposes `detect`, `upgrade`, `get_version`, `bump(level)`,
`upgrade_files`, and `release_files` (plus the executable name).
Native uv/npm/bun commands remain explicit in their respective modules. No custom
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

## bun

bun requires `package.json` and either `bun.lock`, `bun.lockb`, or a string
`packageManager` starting with `bun@` followed by a nonempty version. Lock markers
win even if packageManager names npm. Both bun locks together still mean bun.
Without a manifest no JavaScript manager matches. Invalid JSON is not a
packageManager marker; version reading still reports invalid manifests.
Evaluate all candidates, discard npm when bun matches, then require exactly one
match. uv plus bun remains ambiguous, as does uv plus npm. Missing selected bun
is an explicit executable error, never a fallback to npm.

- Upgrade: `bun update` (within existing constraints, without `--latest`).
- Read version: parse and validate root package.json, as for npm.
- Bump: `bun pm version LEVEL --no-git-tag-version`, then
  `bun install --lockfile-only` to synchronize the lock without upgrading dependencies.
- Upgrade/release files: `package.json`, `bun.lock`, `bun.lockb`.

Requires a bun version supporting `bun pm version`; unsupported commands fail
without fallback or Python version arithmetic. Native output is inherited.
An accompanying npm lock is not maintained by bun and is outside allowed files.
bun owns lock format choice. If an operation creates a new lock or migrates to a
previously absent lock path, stop before publication and preserve changes. The
user must review and track the intended lock manually before retrying. This
also applies to packageManager-only projects: detection succeeds but initial
lock creation cannot be published automatically under the no-untracked-staging
contract. Existing tracked legacy locks are allowed; no automatic migration or
removal is performed by few-updater.

Command references: [bun version](https://bun.sh/docs/pm/cli/pm#version),
[bun update](https://bun.sh/docs/pm/cli/update),
[bun lockfiles](https://bun.sh/docs/pm/lockfile).
