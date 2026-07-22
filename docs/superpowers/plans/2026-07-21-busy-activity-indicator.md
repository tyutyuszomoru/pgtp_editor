# Busy Activity Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a cosmetic "something is happening" indicator — a sticky status-bar message (with file name + size for open) and a wait-cursor hourglass, force-painted before the blocking work — during the slow synchronous operations (file open, schema enrichment, validate, reparse).

**Architecture:** A tiny `ui/busy.py` context manager sets the status message + `WaitCursor`, forces an immediate repaint with `processEvents(ExcludeUserInputEvents)`, and restores the cursor on exit (even on exception). Blocking call sites in `main_window.py` wrap their heavy region in it. No threading — the window is still frozen to input during each op; only the in-progress state becomes visible.

**Tech Stack:** Python 3.10+, PySide6 (QtWidgets/QtGui/QtCore), pytest + pytest-qt. Tests run with `$env:QT_QPA_PLATFORM='offscreen'` using system `python`.

**Spec:** `docs/superpowers/specs/2026-07-21-busy-activity-indicator-design.md`

## Global Constraints

- Progress text goes in the **status bar**, never the Audit panel (the Audit panel is for `[Prefix]` result records).
- In-progress message: gerund + `…`, **no timeout** (sticky). Terminal message: keep each operation's existing timed message.
- No threads / `run_async`, no `QProgressBar`/`QProgressDialog` (cosmetic only — Approach C).
- Every `setOverrideCursor` is balanced by exactly one `restoreOverrideCursor` (via the context manager's `finally`).
- Tests: offscreen Qt; never reach an un-patched modal (`QMessageBox.*`/`QFileDialog.*`/`QDialog.exec`) — monkeypatch them.
- **Generation is already async + already shows `"Generating…"`; it does NOT get the wait-cursor treatment** (a cosmetic cursor around a non-blocking call would restore immediately while the real work runs later). It receives only a wording tweak.

---

## Task 1: `busy.py` — `format_size` and `busy_status`

**Files:**
- Create: `pgtp_editor/ui/busy.py`
- Test: `tests/ui/test_busy.py`

**Interfaces:**
- Produces:
  - `format_size(num_bytes: int) -> str` — `"500 bytes"`, `"312 KB"`, `"1.4 MB"`.
  - `busy_status(status_bar, message: str)` — a context manager; on enter shows `message` (sticky) and sets a `WaitCursor`, force-paints; on exit restores the cursor.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_busy.py`:

```python
from PySide6.QtWidgets import QApplication, QStatusBar

from pgtp_editor.ui.busy import busy_status, format_size


def test_format_size_bytes():
    assert format_size(500) == "500 bytes"


def test_format_size_kb():
    assert format_size(312 * 1024) == "312 KB"


def test_format_size_mb():
    # 1.4 MB exactly, avoiding a .5 rounding boundary
    assert format_size(int(1.4 * 1024 * 1024)) == "1.4 MB"


def test_busy_status_sets_message_and_cursor_then_restores(qtbot):
    bar = QStatusBar()
    qtbot.addWidget(bar)
    assert QApplication.overrideCursor() is None

    with busy_status(bar, "Working…"):
        assert bar.currentMessage() == "Working…"
        assert QApplication.overrideCursor() is not None

    assert QApplication.overrideCursor() is None


def test_busy_status_restores_cursor_on_exception(qtbot):
    bar = QStatusBar()
    qtbot.addWidget(bar)

    class Boom(Exception):
        pass

    try:
        with busy_status(bar, "Working…"):
            raise Boom()
    except Boom:
        pass

    assert QApplication.overrideCursor() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_busy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.ui.busy'`.

- [ ] **Step 3: Implement `busy.py`**

Create `pgtp_editor/ui/busy.py` (keep the repo's standard GPL header comment at the top, matching sibling files like `pgtp_editor/ui/async_task.py`), then:

```python
"""Cosmetic "something is happening" indicator for blocking GUI operations.

`busy_status` shows a sticky status-bar message and a wait cursor, then forces
an immediate repaint BEFORE the blocking work runs so the user sees the app is
working rather than hung. It does NOT move work off the GUI thread -- the window
is still unresponsive to input during the operation (Approach C, cosmetic).

`processEvents(ExcludeUserInputEvents)` paints the pending message + cursor
without dispatching queued clicks/keys, so a double-triggered action cannot
re-enter the operation mid-flight. The cursor is always restored via `finally`.

Kept tiny and Qt-only, mirroring `ui/async_task.py`.
"""
from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication


def format_size(num_bytes: int) -> str:
    """Human-readable byte count: '500 bytes', '312 KB', '1.4 MB'."""
    if num_bytes < 1024:
        return f"{num_bytes} bytes"
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.0f} KB"
    return f"{kb / 1024:.1f} MB"


@contextmanager
def busy_status(status_bar, message: str):
    """Show `message` (sticky) + a wait cursor, painted immediately, for the
    duration of the wrapped block. Restores the cursor on exit, even on error.

    The caller is responsible for the terminal (done) message after the block.
    """
    status_bar.showMessage(message)
    QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
    try:
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )
        yield
    finally:
        QApplication.restoreOverrideCursor()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_busy.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/busy.py tests/ui/test_busy.py
git commit -m "Add busy_status context manager and format_size helper"
```

---

## Task 2: Wrap file open (and its schema enrichment)

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`open_project_file`, ~line 798; import from `busy`)
- Test: `tests/ui/test_open_project.py`

**Interfaces:**
- Consumes: `busy_status`, `format_size` from `pgtp_editor.ui.busy`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_open_project.py`:

```python
import os
from unittest.mock import patch

from PySide6.QtWidgets import QApplication


def _record_status(window, monkeypatch):
    messages = []
    monkeypatch.setattr(
        window.statusBar(), "showMessage",
        lambda msg, *a, **k: messages.append(msg),
    )
    return messages


def test_open_shows_opening_message_with_name_and_size(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "valid.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")
    messages = _record_status(window, monkeypatch)

    window.open_project_file(str(path))

    size = os.path.getsize(path)
    opening = [m for m in messages if m.startswith("Opening ")]
    assert opening, messages
    assert "valid.pgtp" in opening[0]
    # size suffix present (e.g. "... (NNN bytes)…" or "(N KB)…")
    assert "(" in opening[0] and opening[0].rstrip().endswith("…")
    # terminal message still shown
    assert any(m.startswith("Opened:") for m in messages)


def test_open_restores_cursor_on_success(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "valid.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(path))

    assert QApplication.overrideCursor() is None


def test_open_parse_failure_restores_cursor_before_dialog(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        # cursor must already be restored by the time the dialog is shown
        mock_critical.side_effect = lambda *a, **k: (
            None if QApplication.overrideCursor() is None
            else (_ for _ in ()).throw(AssertionError("cursor not restored before dialog"))
        )
        window.open_project_file(str(path))

    mock_critical.assert_called_once()
    assert QApplication.overrideCursor() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_open_project.py -q -k "opening_message or restores_cursor or parse_failure_restores"`
Expected: FAIL — no `Opening …` message is emitted (the current code only shows `Opened:`).

- [ ] **Step 3: Add the import**

Near the other `from pgtp_editor.ui...` imports at the top of `main_window.py`, add:

```python
from pgtp_editor.ui.busy import busy_status, format_size
```

- [ ] **Step 4: Rewrite `open_project_file` to wrap the heavy region**

Replace the body of `open_project_file` (currently lines ~808-839, from `_log.info(...)` through `self._enrich_schema_from_file(path)`) with:

```python
        _log.info("file: open %s", path)
        name = Path(path).name
        try:
            message = f"Opening {name} ({format_size(os.path.getsize(path))})…"
        except OSError:
            # Never fail the open over a stat hiccup; just drop the size.
            message = f"Opening {name}…"

        parse_error = None
        with busy_status(self.statusBar(), message):
            try:
                project = load_project(path)
            except PgtpParseError as exc:
                parse_error = exc
            else:
                self.project_tree.populate_from_project(project)
                self._current_project = project
                # Normalize to str so downstream string ops (e.g. the ".bak"
                # path concatenation in _revert_project / _write_project_text)
                # never hit a TypeError when a caller passes a pathlib.Path
                # instead of the QFileDialog string.
                self._current_project_path = str(path)
                raw_text = self._read_raw_text(path)
                if raw_text is not None:
                    self._loading = True
                    try:
                        self.center_stage.xml_editor.setPlainText(raw_text)
                    finally:
                        self._loading = False
                self._set_dirty(False)
                # A newly-opened project is a fresh document: drop the previous
                # project's snapshots so undo never crosses between documents,
                # then seed the history with the freshly-loaded text.
                self._history.clear()
                self._history.push(
                    self.center_stage.xml_editor.toPlainText(),
                    f"Opened {name}",
                    baseline=True,
                )
                # Schema enrichment is the slowest part of open; keep it inside
                # the busy block so the hourglass covers it.
                self._enrich_schema_from_file(path)

        # Cursor restored here (busy_status __exit__), BEFORE any dialog.
        if parse_error is not None:
            self._handle_parse_failure(path, parse_error)
            return
        self.statusBar().showMessage(f"Opened: {path}", 5000)
```

Verify `import os` is already present at the top of `main_window.py` (it is); if not, add it.

- [ ] **Step 5: Run the targeted tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_open_project.py -q`
Expected: PASS (all existing open tests + the 3 new ones).

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_open_project.py
git commit -m "Show busy hourglass + 'Opening <name> (<size>)…' during file open"
```

---

## Task 3: Wrap validate and reparse

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`_validate_project` ~962, `_reparse_raw_xml` ~1056)
- Test: `tests/ui/test_busy_wiring.py`

**Interfaces:**
- Consumes: `busy_status` from `pgtp_editor.ui.busy` (already imported in Task 2).

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_busy_wiring.py`:

```python
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="orders" tableName="pr.orders" caption="Orders"/>
    </Pages>
  </Presentation>
</Project>
"""


def _open(window, tmp_path):
    path = tmp_path / "p.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(path))


def _record_status(window, monkeypatch):
    messages = []
    monkeypatch.setattr(
        window.statusBar(), "showMessage",
        lambda msg, *a, **k: messages.append(msg),
    )
    return messages


def test_validate_shows_validating_message_and_restores_cursor(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    messages = _record_status(window, monkeypatch)

    window._validate_project()

    assert any(m.startswith("Validating ") for m in messages), messages
    assert QApplication.overrideCursor() is None


def test_reparse_shows_reparsing_message_and_restores_cursor(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    messages = _record_status(window, monkeypatch)

    window._reparse_raw_xml()

    assert any(m.startswith("Reparsing") for m in messages), messages
    assert any(m == "Reparsed raw XML into tree" for m in messages), messages
    assert QApplication.overrideCursor() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_busy_wiring.py -q`
Expected: FAIL — no `Validating …` / `Reparsing…` message is emitted yet.

- [ ] **Step 3: Wrap `_validate_project`**

In `_validate_project`, the current body after the `if self._current_project is None:` guard runs `self._clear_validation_results()` then `issues = validate_project(self._current_project)` then a loop populating the Audit panel then the terminal status message. Wrap the compute + population in `busy_status`. Replace from `self._clear_validation_results()` through the end of the method with:

```python
        name = (
            Path(self._current_project_path).name
            if self._current_project_path else "project"
        )
        self._clear_validation_results()
        with busy_status(self.statusBar(), f"Validating {name}…"):
            issues = validate_project(self._current_project)
            n_err = 0
            n_warn = 0
            for issue in issues:
                if issue.severity == "error":
                    n_err += 1
                else:
                    n_warn += 1
                if issue.line is None:
                    text = f"{_VALIDATION_PREFIX}{issue.severity.upper()}: {issue.message}"
                else:
                    text = (
                        f"{_VALIDATION_PREFIX}{issue.severity.upper()} "
                        f"line {issue.line}: {issue.message}"
                    )
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, issue.line)
                self.audit_panel.addItem(item)
        if issues:
            self.statusBar().showMessage(
                f"Validation: {n_err} error(s), {n_warn} warning(s)", 5000
            )
        else:
            self.statusBar().showMessage("Validation passed — no issues.", 5000)
```

- [ ] **Step 4: Wrap `_reparse_raw_xml`**

In `_reparse_raw_xml`, wrap the parse + success rebuild. Replace the body (from `text = self.center_stage.xml_editor.toPlainText()` through `self.statusBar().showMessage("Reparsed raw XML into tree", 5000)`) with:

```python
        text = self.center_stage.xml_editor.toPlainText()
        parse_error = None
        with busy_status(self.statusBar(), "Reparsing…"):
            try:
                project = load_project_from_text(text, source_description="<editor>")
            except PgtpParseError as exc:
                parse_error = exc
            else:
                # SUCCESS: rebuild tree + adopt the new model so click-sync realigns.
                self.project_tree.populate_from_project(project)
                self._current_project = project
                if self.left_tabs.isTabVisible(self.table_refs_tab_index):
                    self.table_refs_panel.set_usages(
                        collect_table_usages(self._current_project)
                    )
                # Properties has no valid selection against the freshly rebuilt
                # tree (populate_from_project cleared it); show the empty state
                # until the user clicks again. show_node(None, None) resets it.
                self.properties_panel.show_node(None, None)
        # Cursor restored before any failure dialog.
        if parse_error is not None:
            self._handle_reparse_failure(parse_error)
            return
        self.statusBar().showMessage("Reparsed raw XML into tree", 5000)
        self._refresh_db_check_if_open(project)
```

- [ ] **Step 5: Run the targeted tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_busy_wiring.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_busy_wiring.py
git commit -m "Show busy hourglass during validate and reparse"
```

---

## Task 4: Align the generation busy message (no cursor — already async)

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`_generate_php`, ~line 2269)
- Test: `tests/ui/test_generation.py`

**Rationale:** Generation already runs off the GUI thread via `self._generator_runner.run(...)` and already shows a sticky status message, so it satisfies the "visual clue" requirement WITHOUT `busy_status` (a cosmetic cursor would restore immediately while the QProcess runs later). The only change is to make the message name the activity, consistent with the other operations' wording.

- [ ] **Step 1: Write the failing test**

Add to `tests/ui/test_generation.py` (a fake runner + fakes for the pre-flight dialogs already exist in that file — follow its established pattern for constructing a window whose `_generate_php` reaches the run step; if a suitable helper exists, reuse it). Add:

```python
def test_generate_status_message_names_php(qtbot, tmp_path, monkeypatch):
    # Build a window wired so _generate_php reaches the runner step, following
    # the existing generation-test setup in this file (injected runner, patched
    # executable-path + save + output-folder dialogs). Then assert the busy
    # message names PHP.
    window, messages = _generation_window_reaching_run(qtbot, tmp_path, monkeypatch)

    window._generate_php()

    assert any(m == "Generating PHP…" for m in messages), messages
```

If `tests/ui/test_generation.py` has no reusable "reaches run" helper, add a module-level `_generation_window_reaching_run(qtbot, tmp_path, monkeypatch)` that constructs `MainWindow`, injects a fake `generator_runner` whose `run(command, on_output, on_finished)` records the call (does not spawn a process), patches `load_executable_path` to return a dummy path, patches `QMessageBox.question` to return `QMessageBox.StandardButton.Save`, patches `MainWindow._save_project` to set `self._current_project_path` to a temp `.pgtp`, patches `QFileDialog.getExistingDirectory` to return `str(tmp_path)`, records `statusBar().showMessage`, and returns `(window, messages)`. Model it on the existing generation tests in the file so the fakes match their conventions.

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_generation.py -q -k "names_php"`
Expected: FAIL — current message is `"Generating…"`, not `"Generating PHP…"`.

- [ ] **Step 3: Update the message**

In `_generate_php`, change the one line:

```python
        self.statusBar().showMessage("Generating…")
```

to:

```python
        self.statusBar().showMessage("Generating PHP…")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_generation.py -q`
Expected: PASS (new test + existing generation tests; if any existing test asserted the exact old string `"Generating…"`, update that assertion to `"Generating PHP…"` in the same commit).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_generation.py
git commit -m "Name the generation activity: 'Generating PHP…'"
```

---

## Task 5: Full-suite verification and gates

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
Expected: PASS — all green.

- [ ] **Step 2: Manual smoke check (optional)**

Launch the app, open `sample/dev_Ferrara.pgtp`, and confirm the status bar shows `Opening dev_Ferrara.pgtp (… KB)…` with an hourglass cursor during the load, then `Opened: …`. Try Tools ▸ Validate Project and Tools ▸ Reparse Raw XML into Tree.

Run: `python -m pgtp_editor.main`

- [ ] **Step 3: feature-tester gate**

Dispatch the `feature-tester` subagent with feature name "Busy activity indicator (cosmetic status message + hourglass)", the spec path `docs/superpowers/specs/2026-07-21-busy-activity-indicator-design.md`, and the changed files (`pgtp_editor/ui/busy.py`, `pgtp_editor/ui/main_window.py`). It appends the verified result to `docs/TEST_LOG.md`.

- [ ] **Step 4: manual-maintainer gate**

After feature-tester is green and `docs/TEST_LOG.md` is written, dispatch the `manual-maintainer` subagent (the status messages are a minor user-visible surface; it may no-op if it judges no manual change is warranted).

---

## Self-review notes

- **Spec coverage:** `busy_status` + `format_size` → Task 1. File open message with name+size + enrichment coverage + cursor-before-dialog edge → Task 2. Validate + reparse → Task 3. Generation (already async; wording only, with documented rationale) → Task 4. Status-bar-not-Audit, gerund+`…`/timed-terminal, balanced cursor, no-threading → Global Constraints + enforced in each task. Tests + feature-tester + manual-maintainer → Tasks 1-5.
- **Placeholder scan:** none — every code step shows full code; Task 4's test-helper is described concretely with each fake it must install.
- **Type consistency:** `busy_status(status_bar, message)` and `format_size(num_bytes)` used identically in Tasks 1-3; import line added once (Task 2) and reused (Task 3).
- **Deviation from spec (documented):** spec listed Generation for the busy indicator; the code shows generation is already non-blocking with its own status message, so Task 4 gives it a wording tweak instead of a (harmful) cosmetic cursor. Rationale recorded in Task 4 and Global Constraints.
