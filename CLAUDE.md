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
- **The same agent HARMONIZES, and it does so first.** `spec-harmonizer` was
  merged into `spec-maintainer` (2026-08-10): surveying the spec against shipped
  code and authoring into it are one job, and the order is load-bearing. The spec
  must be clean **before a new feature request arrives**, so nobody designs
  against ghosts, and clean **before implementation starts**, because
  contradictions in the spec become deep problems in the code. Dispatch it after
  any batch of work lands, not only when folding something in.
- **The spec is the final single truth**, so it carries the obligation to be
  right: code and spec are never left diverged. If the spec is stale the agent
  corrects it; if the CODE is wrong the agent dispatches `bug-triager` rather
  than quietly rewriting the requirement to match. It also works
  **retroactively** — filing features that shipped differently than specified,
  and retiring assertions that no longer matter.
- **When reconciliation changes what should be built, the agent RESTATES the
  feature for implementation** rather than leaving the implementer to infer the
  delta — and says explicitly that the restatement supersedes the queue entry.
- **Brainstorming is gated by the same agent (placement gate).** Before design
  crystallizes, `spec-maintainer` first reports where the idea belongs and whether
  to extend an existing feature vs. create a new one — so the project grows
  cohesive complex features instead of near-duplicate parallel functionality. A
  `PreToolUse` hook on the brainstorming skill injects this reminder automatically.
- **The same agent owns `README.md`.** Every time it touches the spec it revisits the README in the
  same pass — identity, what is built today, and direction. The README drifted for a year because
  nobody owned it: the project became an **IDE for applications using `.pgtp` for CRUD and PostgreSQL
  functions for business logic** while its front page still called it a companion `.pgtp` file editor.
  The README is not a summary of the spec; it answers what this is, what it does today, and where it
  is going, for someone who has never seen the project.
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

## Feature idea triage (parallel workflow, opt-in)

- **When the user hands over a feature idea, change request, or improvement
  while other implementation work is in progress**, dispatch the
  `feature-triage` subagent (`.claude/agents/feature-triage.md`) in the
  **foreground** (not `run_in_background`) instead of interrupting the
  current work — unlike `bug-triager`, it is expected to ask
  clarifying/challenging questions and needs answers relayed back before it
  writes anything. It recommends EXTEND-vs-CREATE placement against
  `CONSOLIDATED_SPEC.md` and appends one elaborated proposal to
  `docs/FEATURE_QUEUE.md` — it never edits `CONSOLIDATED_SPEC.md`,
  `pgtp_editor/`, or `tests/`, so it cannot conflict with whatever the main
  session is mid-editing.
- **Queue ids are timestamps, not counters — and the dispatcher supplies them.**
  `FQ-<YYMMDDHHMMSS>` and `BUG-<YYMMDDHHMMSS>`. A sequential id is a function of what
  the agent can *see*, so two agents dispatched in parallel pick the same number — that
  happened for real (two `BUG-063` entries, 2026-08-10) and it survives every direction of
  merge, push and pull, because git merges two appends to different regions cleanly and
  neither side looks wrong. `bug-triager` has `Bash` and reads the clock itself; **
  `feature-triage` deliberately has no `Bash`, so the dispatching session must run
  `date +%y%m%d%H%M%S` and pass the id in the prompt.** It will ask rather than invent one.
  Never renumber an existing `FQ-001…035` / `BUG-001…064` entry — the schemes coexist, and
  an id is a name, not a position.
- **When the user asks to pick up the queue** (typically once the main
  implementation task has wrapped up), read `docs/FEATURE_QUEUE.md`, dispatch
  `spec-maintainer` (it harmonizes first, then folds) to fold each `QUEUED` entry into
  `CONSOLIDATED_SPEC.md`, implement it, run the feature-tester /
  manual-maintainer policies above as usual, then flip that entry's `Status`
  line to `PROCESSED (<commit or spec §>)` in place rather than deleting it.

## Owner decisions (mandatory routing)

- **Never bury a decision the owner must make inside an implementation report.** Decisions raised
  mid-report get missed; work then continues around them and the assumption hardens silently.
  Every blocking or clarifying decision goes through the `owner-decision` subagent
  (`.claude/agents/owner-decision.md`), which is the **sole writer** of
  `docs/DECISION_QUEUE.md`. No other session or agent appends, answers, or flips a status there.
- **`DEC` ids are timestamps too, and the dispatcher supplies them** — `DEC-<YYMMDDHHMMSS>`,
  same rule and same reason as `FQ`/`BUG`. Note that "sole writer" is not protection here:
  it means only this agent writes the file, not that only one instance runs at a time, and
  several have been dispatched concurrently. `owner-decision` has no `Bash`, so run
  `date +%y%m%d%H%M%S` and pass the id; it will ask rather than invent one.
- **To file one:** dispatch `owner-decision` with `run_in_background: true` the moment you hit a
  choice you must not make alone — a design trade-off with no obviously right answer, a ruling that
  would reverse recorded design, or a question whose wrong answer is expensive. Then **continue
  with everything that decision does not block**; filing is not a reason to stop.
- **Do not file** what the code can answer (go read it), what `CONSOLIDATED_SPEC.md` already
  settles, or a choice with an obviously right answer — make that one and say you did. Filing
  trivia trains the owner to skim the queue, which recreates the problem.
- **To answer them:** the owner runs a session dedicated to decisions and dispatches
  `owner-decision` in the **foreground**. It sweeps the queue, retires entries already overtaken by
  shipped code, puts the live ones as self-contained questions, and writes the answers back **with
  the owner's reasoning** — an answer without its why gets re-litigated.
- An answered entry may contradict the spec, the manual, or a queue entry. `owner-decision` reports
  that; reconciling it belongs to `spec-maintainer`, `manual-maintainer`, or `bug-triager` as usual.

## Keyboard shortcuts (mandatory — this is the most expensive area in the project)

Keyboard work has consumed more owner attention and more tokens than any feature, almost
entirely on re-deriving facts that should have been written down once: five owner decisions
and a dozen bugs in a single day. Every one of them was a *"who answers this chord"* question
that nothing in the repo could answer. These rules exist to end that.

- **`docs/KEYBINDINGS.md` is the single register of every chord in the app** — the chord, the
  command, which mechanism hosts it, which surfaces it is live on, and its gate. **It is kept
  true by a test, not by discipline.** `shortcut_registry.RESERVED_SEQUENCES` was meant to be
  this and rotted precisely because its docstring says *"transcribed from §27"* — a hand
  transcription silently lost `Ctrl+Shift+Z` until BUG-050. A ledger nobody verifies is a
  second document, not a source of truth.
- **Before proposing or assigning any chord, read the ledger, and PUSH BACK if it is taken.**
  Name what holds it and on which surfaces. Do not offer a "probably free" chord and do not
  reason from a menu listing — six different mechanisms can answer a keystroke here
  (`QAction.setShortcut`, `QShortcut`, `keyPressEvent`, `eventFilter`/`ShortcutOverride`,
  context-menu actions, and Qt's `StandardKey` platform defaults), and a chord bound by any of
  them is bound.
- **Always establish the GATE before the chord, and ask the owner rather than deciding it.**
  The gate is not a formality; it determines where the code lives and how many hosts are legal:
  - **Does the command have a command form** — a menu-bar entry *or* a context-menu action?
    Then it has **exactly one keyboard host** (DEC-012), and that host is the `QAction`.
  - **No command form at all?** A widget host is legitimate (DEC-009's carve-out) — but only
    then, and the reason must be a product reason, never "the tests need it".
  - **Answered inside a widget's key handling?** It must be in `RESERVED_SEQUENCES`, and under
    DEC-014 *every* editing surface must state its answer for that chord.
  - **Is the chord platform-conditional?** Qt's table is not the app's answer — DEC-015: an
    operation's chord is bound by this app on every platform, never inherited.
- **A chord means the same thing on every system, and the ledger records ONE binding per command.**
  No platform-conditional shortcuts. Qt's own table is not uniform — its Windows scheme binds
  `Ctrl+Y` and `Alt+Backspace`/`Alt+Shift+Backspace` for undo/redo where X11 does not, and
  `Ctrl+Shift+Z` is bound on both. Wherever Qt would differ, **this app binds explicitly on both
  platforms or suppresses the chord on both** — a chord that works on Windows and is dead on Linux
  is a bug, not a platform nicety. This is why `Ctrl+Y` had to become an explicit binding
  (DEC-015) and why the offscreen suite cannot be trusted here: it runs Qt's **Windows** scheme,
  so a Linux-only dead key passes every test.
- **Never bind by feel, and never widen a carve-out by analogy.** DEC-009's exemption was read
  wider than it was drawn twice in one day (BUG-052, BUG-063), each time by a comment citing a
  defensible rule for the wrong gesture.
- **The offscreen test platform runs Qt's WINDOWS keyboard scheme**, so Linux-only key
  behaviour is invisible to the whole suite. Assert the handler, never Qt's native answer. And
  `QShortcut` *does* fire offscreen — the requirement is that the widget's top level has been
  `show()`n, which is what every "offscreen is unreliable" comment in this repo got wrong.

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
