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

## Test environment

- Use the system `python` — the project is installed editable there with
  pytest/pytest-qt. The repo's `venv\` directory is a bare leftover without
  pytest; do not use it.
- Full suite: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
- Tests mirror the package layout: `pgtp_editor/<area>/foo.py` →
  `tests/<area>/test_foo.py`. Never let a test reach an un-patched modal Qt call
  (`QDialog.exec`, `QMessageBox.*`, `QFileDialog.*`) — monkeypatch them.
