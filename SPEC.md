# few-updater — Specification

## 1. Objective

Develop `few-updater`, a Python CLI utility that automates dependency maintenance and release preparation for software projects.

The tool must remain simple, predictable, and easy to maintain.

Supports Python projects using **uv** and Node.js projects using **npm**. V1's uv behavior is preserved.

Two independent commands are required:

```bash
few-updater upgrade
few-updater release
```

The tool is exclusively interactive and must be run from the target Git repository's root directory.

## 2. Technical constraints

- Python >= 3.11.
- Project managed and distributed with uv.
- Python standard library only.
- Use `subprocess` for Git, uv, and npm.
- No external runtime dependencies.
- No CLI framework.
- No tool-specific configuration file.
- No GitHub API or Dependabot integration.
- No CI support or non-interactive mode.
- Refuse to run without an interactive terminal (TTY).
- Do not modify the user's Git configuration.

The Python package must be named `few_updater` and expose the `few-updater` command.

Prefer a minimal architecture without a universal package manager abstraction.

## 3. Common preconditions

Before any operation, both commands must verify:

1. The current directory is exactly the Git repository root.
2. The current branch is `main`.
3. The Git index and tracked files in the working tree are clean. `upgrade` and `release` allow untracked files.
4. Exactly one complete set of project files is present (see detection below).
5. The `git` executable and the detected manager (`uv` or `npm`) are available. Running against an npm project does not require uv.
6. The `origin` remote exists.
7. The remote branch `origin/main` exists.

Run:

```bash
git fetch origin
```

Then verify that `HEAD` matches `origin/main` exactly.

If a precondition fails, display an explicit error and stop without modifying the repository.

Do not automatically pull, merge, or rebase.

### Package manager detection

Detect the manager at the repository root, without a CLI argument or menu:

| Files present | Manager |
|---|---|
| `pyproject.toml` + `uv.lock` | uv |
| `package.json` + `package-lock.json` | npm |
| Both complete sets | Explicit error |
| No complete set | Explicit error |

An incomplete set does not interfere with another complete set. Only npm is
supported for Node.js; pnpm, Yarn, and Bun are not supported.

## 4. The `upgrade` command

### Objective

Update dependencies with the detected manager, create a commit, and push it to `main`.

### uv workflow (unchanged)

1. Check the common preconditions.
2. Run with stdout and stderr connected directly to the terminal, without capture, to preserve uv's native output and colors:

```bash
uv lock --upgrade
```

3. Check whether `uv.lock` changed.
4. If no change is detected:
   - Display `Dependencies already up to date`.
   - Exit with code `0`, without committing or pushing.
5. If `uv.lock` changed, automatically and without confirmation:
   - Display `Committing dependency updates...` before the commit.
   - Stage only `uv.lock`.
   - Create the commit with stdout and stderr connected directly to the terminal to preserve Git's native output:

```text
build: update dependencies
```

6. After the commit succeeds, display `Pushing to origin/main...`, then automatically run with stdout and stderr connected directly to the terminal:

```bash
git push origin main
```

### npm workflow

After the same preconditions, run `npm update` with stdout and stderr connected
directly to the terminal. npm respects the constraints in `package.json` and
manages dependencies and `node_modules` directly.

Detect tracked changes to `package.json` and `package-lock.json`.
If neither file changes, display `Dependencies already up to date` and exit
with code `0`, without committing or pushing. Otherwise, display
`Committing dependency updates...`, explicitly stage only the modified files
among these two paths, and create the commit `build: update dependencies`
with native output. Then display `Pushing to origin/main...` and run
`git push origin main` with native output. No diff or confirmation.

Never stage `node_modules`, untracked files, or other project files.
Any unexpected change to a tracked file causes an error before the commit,
without automatic restoration.

### uv rules (unchanged)

- Do not intentionally modify `pyproject.toml`.
- Do not bump the version.
- Do not create a tag.
- Do not modify application code.
- No user confirmation.
- No `git diff` output.
- Commit and push only if `uv.lock` changes.
- If uv fails, stop without committing or pushing.
- If uv modifies files before failing, leave them as they are.
- Do not commit unexpected files.
- `upgrade` ignores untracked files when checking for changes and does not include them in the commit.

## 5. The `release` command

### Objective

Automate the patch version bump, commit, annotated tag creation, and Git publication.

This command is independent of `upgrade`.

### Versioning convention

Use this format:

```text
MAJOR.MINOR.PATCH
```

Examples:

```text
0.1.0
1.2.3
2.0.1
```

Release tags must:

- Be annotated Git tags.
- Have no `v` prefix.
- Use the `X.Y.Z` format.
- Have an annotation message identical to the tag name.

Example:

```bash
git tag -a 1.2.3 -m "1.2.3"
```

### Detecting an unnecessary release

After the common preconditions, run:

```bash
git describe
```

Expected behavior:

| Result | Behavior |
|---|---|
| `1.2.3` | Already released; exit with code `0` |
| `1.2.3-4-gabcdef` | New commits; continue |
| No annotated tag | Error |
| Unexpected format | Error |

Validate the expected format with a strict regular expression.

Do not implement complex tag searches or mechanisms to reconstruct release history.

The convention assumes that annotated tags reachable by `git describe` are exclusively release tags.

### Workflow

1. Check the common preconditions.
2. Run `git describe`.
3. Exit successfully if `HEAD` already corresponds to a release.
4. Read the current version with `uv version --short` for uv, or read the `version` field from the root `package.json` using the JSON parser for npm. A missing or invalid version, or one outside the strict `X.Y.Z` format, is an error.
5. Calculate the next patch version.
6. Check that the target tag does not already exist.
7. Display the current and target versions.
8. Ask the user for confirmation.
9. After confirmation, display `Bumping version...`, then run with stdout and stderr connected directly to the terminal to preserve uv's native output:

```bash
uv version --bump patch
```

For npm, use the following instead, with the same native output handling:

```bash
npm version patch --no-git-tag-version
```

This option prevents npm from automatically creating a commit or tag;
these operations remain under few-updater's control.

10. Verify the resulting version.
11. Display `Committing version bump...`, then stage only modified files among `pyproject.toml` and `uv.lock` for uv, or `package.json` and `package-lock.json` for npm, naming these paths explicitly in `git add --`. Never use `git add -A`, `git add .`, or an equivalent command that could include untracked files.
12. Create the commit with stdout and stderr connected directly to the terminal to preserve Git's native output:

```text
build: bump version
```

13. Display `Creating annotated tag X.Y.Z...`, then create the annotated tag:

```bash
git tag -a X.Y.Z -m "X.Y.Z"
```

14. Display `Pushing main and X.Y.Z atomically...`, then publish atomically with stdout and stderr connected directly to the terminal:

```bash
git push --atomic origin main X.Y.Z
```

In these messages, replace `X.Y.Z` with the target version. Display each message immediately before its corresponding step, only if that step is reached after confirmation.

### Rules

- Never create a release if `HEAD` already corresponds to a release tag.
- Do not upgrade dependencies.
- Use the manager's native version bump mechanism.
- Do not modify application code.
- Ask for confirmation once, immediately before the bump.
- Ignore untracked files when checking for changes and never include them in the version commit.
- After confirmation, commit, tag, and push without further interaction.
- If confirmation is declined, exit with code `0`.
- Never push if a previous step fails.
- Do not perform an automatic rollback.
- If the push fails, preserve the local commit and tag.
- Display an error and the information needed for manual recovery.

The existing GitHub Actions workflow is responsible for creating a draft GitHub Release after the tag is pushed.

`few-updater` must not interact with that GitHub Release.

## 6. Error handling

General principles:

- Errors must produce a nonzero exit code.
- Having no work to do must produce exit code `0`.
- Declining confirmation must produce exit code `0`.
- Display concise, understandable messages.
- Never hide a critical command failure.
- Never automatically discard local changes.

Prohibited operations:

```bash
git reset --hard
git push --force
git clean -fd
```

No automatic rollback may be implemented.

### Specific cases

**`git fetch` failure**

Stop immediately without modifying the repository.

**Failure of `uv lock --upgrade`, `npm update`, or the native version bump**

Stop without committing. Preserve any changes.

**`git commit` failure**

Stop without pushing. Preserve local changes.

**Tag creation failure**

Stop without pushing. Preserve the created commit.

**`git push` failure**

Stop without rolling back. Clearly state that changes may already be committed or tagged locally.

## 7. CLI interface

Required commands:

```bash
few-updater upgrade
few-updater release
few-updater --help
few-updater upgrade --help
few-updater release --help
```

Use `argparse`.

The `release` confirmation must be explicit, with a negative answer by default.
`upgrade` asks for no confirmation; an interactive terminal (TTY) is still required for both commands.

Example:

```text
Current version: 1.2.3
Next version:    1.2.4

Proceed with release? [y/N]:
```

Do not implement `--yes`, `--force`, `--dry-run`, or `--non-interactive` modes.

## 8. Architecture

Suggested structure:

```text
few-updater/
├── pyproject.toml
├── uv.lock
├── README.md
├── SPEC.md
├── src/
│   └── few_updater/
│       ├── __init__.py
│       ├── cli.py
│       ├── git.py
│       └── uv.py
└── tests/
    ├── test_git.py
    ├── test_upgrade.py
    └── test_release.py
```

This structure is illustrative and may be simplified as needed.

Responsibilities:

- `cli.py`: arguments, confirmations, and orchestration.
- `git.py`: Git operations and checks.
- `uv.py`: uv operations and next patch version calculation.
- `npm.py`: reading and validating the root npm package version.
- `project.py`: detecting the two supported file sets.

Avoid classes and abstractions that add no real value.

## 9. Automated tests

Use `unittest`, without external dependencies.

Tests must cover the main operations and failure cases.

### Git tests

- Invalid Git repository.
- Execution outside the repository root.
- Branch other than `main`.
- Dirty working tree.
- Dirty index.
- Missing `origin` remote.
- Fetch failure.
- Local branch ahead of or behind `origin/main`.
- Detection of an annotated tag.
- Detection of an existing release.
- Unexpected tag format.

### uv `upgrade` tests

- Untracked files allowed, preserved, and excluded from commits, with or without changes to `uv.lock`.
- Changes to tracked files in the working tree or index still rejected, even with untracked files present.
- No lockfile changes: exit code `0`, no commit or push.
- Successful lockfile update.
- Automatic commit with the expected message.
- Automatic push after the commit.
- No confirmation or `git diff` output.
- uv stdout and stderr connected directly to the terminal.
- Progress messages before the commit and push, only when `uv.lock` changes.
- Native `git commit` and `git push` output connected directly to the terminal.
- No push message if the commit fails.
- uv failure.
- Commit failure.
- Push failure.
- No changes to unrelated files.

### uv `release` tests

- Untracked files allowed and preserved, without staging or inclusion in the version commit.
- Changes to tracked files in the working tree or index rejected, even with untracked files present.
- Explicit staging limited to modified files among `pyproject.toml` and `uv.lock`.
- Already released.
- New commits since the last release.
- Correct patch version calculation.
- Confirmation declined.
- Commit with the expected message.
- Creation of an annotated tag.
- Tag message identical to its version.
- Atomic push of `main` and the tag.
- Progress messages in order before each step, after the single confirmation.
- Native output from the uv bump, commit, and atomic push connected directly to the terminal.
- No step messages after confirmation is declined or for steps not reached after a failure.
- Target tag already exists.
- uv failure.
- Commit failure.
- Tag creation failure.
- Push failure without rollback.

### npm tests

- uv/npm detection, incomplete sets, no set, and ambiguous detection.
- npm executable required only for npm projects.
- Upgrade with no changes, lockfile-only changes, or changes to both files.
- No confirmation or diff; native output and progress messages.
- Explicit staging limited to `package.json` and `package-lock.json`; exclusion of `node_modules` and untracked files.
- Release with a single confirmation, JSON reading and version validation, and patch bump with `--no-git-tag-version`.
- Already released, confirmation declined, existing target tag, and incorrect bump.
- Expected commit, annotated tag with the version as its message, and atomic push.
- npm, commit, tag, and push failures; preservation of local changes, commits, and tags.
- All existing uv tests continue to pass.

### Isolation

Use temporary Git repositories for integration tests.

Simulate uv and npm commands where necessary.

Tests must never modify or push to a real project repository.

Run with:

```bash
uv run python -m unittest discover -s tests
```

## 10. Packaging and documentation

The project must be installable with:

```bash
uv tool install .
```

For development:

```bash
uv run few-updater --help
```

`README.md` must document:

- The project's purpose.
- Prerequisites.
- Installation.
- The `upgrade` and `release` commands.
- Git conventions.
- Known limitations.
- Running tests.

Keep the documentation concise.

## 11. Out of scope

Do not implement:

- pnpm, Yarn, or Bun support.
- Dependabot integration.
- GitHub API integration.
- Changelog generation.
- Publishing to PyPI or the npm registry.
- Automatic publication of GitHub Releases.
- Minor or major version management.
- Running tests for target applications.
- Automatic conflict resolution.
- A tool-specific configuration file.
- A plugin system.
- CI or non-interactive mode.
- Automatic rollback.

## 12. Acceptance criteria

1. `few-updater` can be installed via uv.
2. The `upgrade` and `release` commands work independently.
3. `upgrade` preserves the manager's native terminal output and, only when allowed files change, creates the expected commit and pushes to `main`, without confirmation or `git diff` output.
4. `release` performs a patch bump, creates the expected commit, and creates an annotated `X.Y.Z` tag.
5. The release push is atomic.
6. An existing release is detected without modifying the repository.
7. The interactive `release` confirmation works.
8. Errors never trigger an automatic rollback.
9. Automated tests pass.
10. The tool can be used on its own repository after an initial release has been created.

## 13. Implementation instructions for Codex

Implement this specification with simplicity as the consistent priority.

- Do not add unrequested features.
- Limit support to uv and npm, without a universal package manager.
- Do not introduce external dependencies without a demonstrated need.
- Prefer short, explicit functions.
- Avoid unnecessary duplication.
- Add automated tests.
- Run the tests and fix any failures.
- Document actual limitations instead of building complex mechanisms to work around them.

The expected result is a small, robust, maintainable CLI utility, not a release management framework.

## 14. npm limitations

Manages the root package and its `package-lock.json`, without orchestrating
workspace versions. npm lifecycle scripts and project Git hooks run normally;
few-updater does not rewrite them or provide a sandbox for them.
`--no-git-tag-version` disables npm's automatic Git operations, not arbitrary
commands in project scripts. Unexpected tracked changes are rejected before
the commit and preserved. No rollback or npm registry publication.
