# Safety and recovery

## Preconditions

Every operation runs these checks before manager changes or confirmation.
Preflight itself fetches from origin, including when confirmation is later declined:

1. Require Git, the repository root as cwd, and branch `main`.
2. Evaluate every manager candidate. Select exactly one complete file set:
   uv: `pyproject.toml` + `uv.lock`; npm: `package.json` + `package-lock.json`.
   Zero or multiple matches produce clear errors. An incomplete other set does
   not interfere. Never select the first match without checking others.
3. Require a clean index and tracked working tree. Untracked files are ignored.
   `release --no-bump` also accepts changes confined to its manager's version
   files, including staged changes, to publish a standalone local bump.
4. Require the selected executable only; npm projects do not require uv.
5. Require `origin`; run `git fetch origin`. Verify remote `main` exists with
   `ls-remote`, then verify `HEAD` equals `refs/remotes/origin/main`.

Do not pull, merge, rebase, or change Git configuration. Failures stop execution.

## Failures and recovery

Every command failure stops later commands. An unchanged upgrade, an already
released HEAD, or a declined confirmation returns 0. CLI argument errors exit 2;
handled operation failures exit 1.

Command failures identify the command and exit code. Captured output supplies a
diagnostic when available; inherited output is displayed directly. Handled
operation errors tell the user to inspect local status, the last commit, tags,
and origin before manual recovery. Never force, retry automatically, or roll
back. Preserve partial manager changes, staged files, and local commits/tags.
Tag creation failure never pushes; failed atomic push leaves local commits/tags
intact.

Hooks and npm lifecycle scripts run normally. `--no-git-tag-version` disables
npm's own commit/tag behavior, not arbitrary script commands. Unexpected tracked
changes are rejected and preserved. Do not run application tests, generate
changelogs, call GitHub APIs, or publish to registries.
