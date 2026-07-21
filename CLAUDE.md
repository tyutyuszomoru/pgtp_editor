# PGTP Editor — project instructions

## Testing policy (mandatory)

- **Every completed feature triggers the `feature-tester` agent.** When a feature's
  implementation is finished — before declaring it done, before committing it as
  finished, and before moving to the next feature — dispatch the `feature-tester`
  subagent (`.claude/agents/feature-tester.md`) with the feature name, its
  spec/plan paths under `docs/superpowers/`, and the changed files. A feature
  without a green feature-tester run and a `docs/TEST_LOG.md` entry is not done.
- **Run tests frequently while implementing, not just at the end.** After each
  meaningful change, run the targeted tests for the area you touched:
  `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\<area>\ -q`
- **Test passing is recorded in the repo.** `docs/TEST_LOG.md` is the append-only
  record; the feature-tester agent owns appending to it. Commit the log entry
  together with the feature (or with its tests).
- If the feature-tester reports implementation bugs, fix them in the main session
  and re-dispatch the agent until it reports green.

## Manual policy (mandatory)

- **Every completed feature triggers the `manual-maintainer` agent — after the
  feature-tester is green.** Once `feature-tester` reports a green run and the
  `docs/TEST_LOG.md` entry is written, dispatch the `manual-maintainer` subagent
  (`.claude/agents/manual-maintainer.md`) with the feature name, its spec/plan
  paths under `docs/superpowers/`, and the changed files. It updates
  `pgtp_editor/resources/manual.md` so the manual (prose text and the
  heading-derived Contents tree) always reflects current behavior, menu
  locations, and shortcuts. A feature is not done until the manual reflects it,
  or the agent has explicitly reported that no manual change was needed.
- The manual update rides with the feature: commit the `manual.md` change
  together with the feature (git history is the sole record — there is no manual
  changelog file).
- If the manual-maintainer reports manual-vs-reality drift or a broken Contents
  tree it cannot resolve, fix it in the main session and re-dispatch until clean.

## Test environment

- Use the system `python` — the project is installed editable there with
  pytest/pytest-qt. The repo's `venv\` directory is a bare leftover without
  pytest; do not use it.
- Full suite: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
- Tests mirror the package layout: `pgtp_editor/<area>/foo.py` →
  `tests/<area>/test_foo.py`. Never let a test reach an un-patched modal Qt call
  (`QDialog.exec`, `QMessageBox.*`, `QFileDialog.*`) — monkeypatch them.
