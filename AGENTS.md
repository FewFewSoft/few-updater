# few-updater maintenance

few-updater is a Python ≥ 3.11, standard-library-only interactive CLI for uv and
npm root projects. It upgrades dependencies, bumps local versions, and publishes
Git releases. Keep both managers equally supported without hiding their native
commands or calculating version increments in Python.

- Work in this existing directory. The Codex source sandbox is Git-free: never
  initialize Git here, commit, push, sync files, or deploy. Do not run the CLI's
  publishing workflows against this workspace. The existing tests may initialize,
  commit, tag and push only in their isolated temporary repositories/remotes.
- Keep `src/few_updater/cli.py` responsible for arguments, confirmation and
  dispatch; `workflows/` for sequencing; `tools/` for Git, subprocesses, detection
  and package-manager adapters. Keep native uv/npm commands explicit in
  `tools/pm/uv.py` and `tools/pm/npm.py` and the shared contract small.
- Prefer minimal changes, dependencies and abstractions. Preserve the existing
  argparse/subprocess/unittest approach; do not introduce backend frameworks,
  configuration systems, plugins or empty architectural layers.
- Preserve the safety and confirmation contracts in [specs/safety.md](specs/safety.md)
  and [specs/workflows.md](specs/workflows.md), including explicit path staging,
  default-no confirmation, atomic release publication and no automatic rollback.
- Maintain concise topic-based specs in `specs/` whenever behavior changes;
  reconcile them with implementation and focused tests.
- Write `README.md` for end users: keep it short, approachable and easy to scan.
  Explain the purpose, installation and common usage, not every edge case or
  implementation detail. Put exhaustive behavior, constraints and failure cases
  in `specs/` instead of duplicating them in the README.
- Run `PYTHONPATH=src python3 -m unittest discover -s tests` from the project root.
  Tests use temporary repositories and simulated managers; the source workspace
  needs no Git metadata or npm installation. Report checks and limitations, and
  preserve unrelated user changes.
