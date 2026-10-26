# Workflows and verification

All workflows follow the shared [safety preconditions](safety.md) and use the
[manager commands and file sets](cli-and-managers.md).

## Upgrade

After checks, upgrade without confirmation. Inspect tracked status, rejecting
changes outside upgrade files. If none changed, report
`Dependencies already up to date` and exit 0. Otherwise:

1. Print `Committing dependency updates...`.
2. Explicitly stage only changed dependency paths using `git add -- PATHS`.
3. Commit `build: update dependencies` with native output.
4. Print `Pushing to origin/main...`, then run `git push origin main` with native output.

No version bump, tag, or diff display. Never stage untracked files or
`node_modules`. uv upgrade does not intentionally modify `pyproject.toml`.

## Standalone bump

After checks and reading the current version, display the current version and
requested increment. Ask exactly once, default no, before modifying version
files. Only `y` or `yes` (case-insensitive, surrounding whitespace ignored) confirms.
On confirmation run the manager's bump, validate the resulting version, and
reject unexpected tracked changes. Leave all version changes local. Never
commit, tag, or push. Declining exits 0 without modifications.

## Release

After common checks run `git describe`:

- Strict `X.Y.Z`: HEAD already released; report `Release already performed` and
  exit successfully before reading the declared version or asking for confirmation.
  This also applies to `--no-bump` with local version-file changes; those changes
  remain untouched. A standalone bump alone does not make a released HEAD eligible.
- Strict `X.Y.Z-N-gHEX`, with N positive: continue.
- Missing annotated history or any other format: fail.

Read the declared version. For `--no-bump`, check the current tag is unused
locally and on origin before confirmation. Display the version and bump level
(or none), then ask exactly once, default no, before version changes, committing or tagging.
Confirmation uses the same `y`/`yes` rule as standalone bump. Declining exits 0
and preserves any pre-existing local changes.

For a bump, run the native manager command, read and validate its resulting
version, reject unexpected changes, then check that resulting tag is unused
locally (`git tag --list VERSION`) and remotely
(`git ls-remote --tags origin refs/tags/VERSION`). The target is obtained from
the native bump, so a collision at this point preserves local version changes
and stops before any commit. `--no-bump` never invokes a manager bump.

Inspect tracked status and reject changes outside release files. If relevant
files changed, print `Committing version bump...`, explicitly stage only those
paths, then commit `build: bump version` with native output. If nothing changed,
skip the commit; never create an empty commit.

Then print progress immediately before each step:

```text
Creating annotated tag X.Y.Z...
Pushing main and X.Y.Z atomically...
```

Run `git tag -a X.Y.Z -m X.Y.Z` (no v prefix), followed by
`git push --atomic origin main X.Y.Z` with native push output.
No subsequent interaction. Do not upgrade dependencies or publish packages.
Existing GitHub release automation remains outside this tool.

## Verification

Use the existing standard-library unittest suite with temporary Git
repositories/bare remotes and simulated package managers. Git and Python are
required; installed uv/npm and network access are not required for this command.
Tests must run from a Git-free workspace and never affect real repositories.
Cover all detection outcomes, Git preconditions, terminal requirements, native
output, allowed/unexpected/untracked paths, unchanged upgrades, confirmation,
all bump levels, release options, no empty commit, annotated tags, atomic push,
and failures without rollback or subsequent publication.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

The fixtures isolate Git identity and global/system configuration. Git init,
commits and pushes inside temporary test fixtures are expected; they must never
target the source workspace or a real remote. Simulation verifies command
contracts and sequencing, not compatibility with every installed uv/npm version.
