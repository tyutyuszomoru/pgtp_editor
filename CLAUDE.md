# PGTP Editor — project instructions

## Specification policy (mandatory)

- **`docs/superpowers/CONSOLIDATED_SPEC.md` is the single, authoritative spec.**
  It is the one document that describes current design. Do **not** create new
  dated spec files under `docs/superpowers/specs/` for new work — that folder is
  now **frozen historical record** (the source the consolidated spec and its
  Supersession Ledger were built from). Read those old files for rationale/history;
  never add to them.
- **All new or changed design goes into the consolidated spec via the
  `spec-maintainer` agent — never hand-written into a new file.** When a design
  decision is settled (after brainstorming, or when a shipped feature diverges
  from the spec), dispatch the `spec-maintainer` subagent
  (`.claude/agents/spec-maintainer.md`) to fold it into `CONSOLIDATED_SPEC.md`
  with latest-wins reconciliation and a Supersession Ledger row for any override.
  The agent is the sole writer of specification content.
- **Brainstorming is gated by the same agent (placement gate).** Before design
  crystallizes, `spec-maintainer` first reports where the idea belongs and whether
  to extend an existing feature vs. create a new one — so the project grows
  cohesive complex features instead of near-duplicate parallel functionality. A
  `PreToolUse` hook on the brainstorming skill injects this reminder automatically.
- Other agents (`feature-tester`, `manual-maintainer`) that were dispatched with
  "spec paths under `docs/superpowers/`" now take the relevant **section of
  `CONSOLIDATED_SPEC.md`** (plus the feature's plan under
  `docs/superpowers/plans/`, which is still written per-feature) as their spec input.

## Testing policy (mandatory)

- **Every completed feature triggers the `feature-tester` agent.** When a feature's
  implementation is finished — before declaring it done, before committing it as
  finished, and before moving to the next feature — dispatch the `feature-tester`
  subagent (`.claude/agents/feature-tester.md`) with the feature name, its
  spec/plan paths under `docs/superpowers/`, and the changed files. A feature
  without a green feature-tester run and a `docs/TEST_LOG.md` entry is not done.
- **Run tests frequently while implementing, not just at the end.** After each
  meaningful change, run the targeted tests for the area you touched
  (`… -m pytest tests/<area> -q` — see **Test environment** below for the
  interpreter and the offscreen setting on your platform).
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

## Bug report triage (parallel workflow, opt-in)

- **When the user hands over a bug report while other implementation work is
  in progress**, dispatch the `bug-triager` subagent
  (`.claude/agents/bug-triager.md`) with `run_in_background: true` instead of
  interrupting the current work. It investigates the report read-only and
  appends a root-caused, ready-to-implement proposal to
  `docs/BUGFIX_QUEUE.md` — it never edits `pgtp_editor/`, `tests/`, or specs,
  so it cannot conflict with whatever the main session is mid-editing.
  Dispatch one instance per report; several can be in flight at once.
- **When the user asks to resolve the queue** (typically once the main
  implementation task has wrapped up), read `docs/BUGFIX_QUEUE.md`, implement
  each `OPEN` entry, run the feature-tester / manual-maintainer / spec
  policies above as usual, then flip that entry's `Status` line to
  `RESOLVED (<commit>)` in place rather than deleting it.

## Test environment

Development happens on **both Windows and Linux**, and the two differ in which
interpreter has the test dependencies. Always confirm which one works in the
current checkout before concluding anything about a failure:

```
python -c "import pytest, PySide6"          # Windows: usually the system python
venv/bin/python -c "import pytest, PySide6" # Linux: usually the repo venv
```

- **Interpreter.** On Windows the project is typically installed editable into
  the **system `python`** and the repo's `venv\` is a bare leftover without
  pytest. On Linux it is the reverse: the system `python` has no pytest and the
  repo's **`venv/bin/python`** carries pytest/pytest-qt/pytest-xdist. Use
  whichever import check above succeeds — do not assume.
- **Offscreen platform.** Qt must run headless, via the `QT_QPA_PLATFORM`
  environment variable set to `offscreen`. Set it the way your shell does:
  - PowerShell: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q -n 10`
  - bash/zsh:   `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q -n 10`
- **Full suite runs in parallel.** `-n 10` (pytest-xdist, a declared dev
  dependency) takes ~2.5 min; serially the same suite takes ~8 min and can
  additionally produce spurious per-test `Timeout` failures from pytest-timeout
  that do NOT reproduce under `-n 10`. Never diagnose those as code regressions
  — re-run in parallel first. Adjust the worker count to the machine.
- **Never pipe a suite run through `tail`** — it discards the failing test's
  name, which is the one thing you need. Filter with
  `grep -E "passed|failed|^FAILED"` (or `Select-String`) instead.
- Tests mirror the package layout: `pgtp_editor/<area>/foo.py` →
  `tests/<area>/test_foo.py`. Never let a test reach an un-patched modal Qt call
  (`QDialog.exec`, `QMessageBox.*`, `QFileDialog.*`) — monkeypatch them.
