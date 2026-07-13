# Find All streaming + Stop, and Replace All count — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Find All stream results into the Audit panel a batch at a time with a Stop button that keeps partial results, add live/final status-bar counts, and add a replacement-count status message to Replace All.

**Architecture:** A lazy `search.iter_matches` generator (with `find_all_matches` delegating to it) feeds a `QTimer(0ms)`-driven chunked loop in `MainWindow`; the find bar's "Find All" button toggles to "Stop" and reports through two new injected callbacks (`on_stop_find_all`, `on_status`).

**Tech Stack:** Python 3.13, PySide6 (Qt widgets), pytest, pytest-qt. The suite runs headless offscreen with a `--timeout=60` guard (conftest.py + pyproject.toml on main).

---

## Current-state facts (confirmed by reading this worktree; do not re-derive)

- `pgtp_editor/ui/search.py`: `Match(frozen dataclass: start, line, preview)`, `find_next(text, term, from_pos, *, wrap=True)`, `find_all_matches(text, term)` (non-overlapping scan advancing by `len(term)`, 1-based `line`, trimmed `preview` via `_line_preview`).
- `pgtp_editor/ui/find_replace_bar.py`: `FindReplaceBar(editor, on_find_all=None, parent=None)`. Has `_find_field`, `_find_all_button` (`QPushButton("Find All")`, `clicked`→`find_all`), `_replace_field`, `set_on_find_all`, `find_all()` (term-guard → `self._on_find_all(term)`), `replace_all()` (returns early if no matches; else single `beginEditBlock`/`endEditBlock` reversed rewrite). `self._on_find_all = on_find_all or (lambda term: None)`.
- `pgtp_editor/ui/main_window.py`: imports `QListWidgetItem` (widgets block) and `from pgtp_editor.ui import search`; `Qt` from `PySide6.QtCore`. Module constant `_FIND_RESULT_PREFIX = "[Find] "`. In `__init__`: `self.center_stage.find_replace_bar.set_on_find_all(self._populate_find_all_results)` then `self.audit_panel.itemClicked.connect(self._on_audit_item_clicked)`. Methods `_populate_find_all_results(term)`, `_clear_find_results()`, `_on_audit_item_clicked(item)` exist as shown in the spec. `self.audit_panel` is a `QListWidget`. `QMainWindow.statusBar().showMessage(text)` / `.currentMessage()` are available.
- Tests live in `tests/ui/test_search.py`, `tests/ui/test_find_replace_bar.py`, `tests/ui/test_main_window.py`. `qtbot` + `qtbot.addWidget(...)` throughout; offscreen platform preconfigured.

---

## Task 1: `search.iter_matches` generator

**Files:**
- Modify: `pgtp_editor/ui/search.py`
- Test: `tests/ui/test_search.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/ui/test_search.py`:

```python
import itertools

from pgtp_editor.ui.search import iter_matches


def test_iter_matches_matches_find_all_matches():
    from pgtp_editor.ui.search import find_all_matches
    text = "page PAGE page\nno hits\nlast page"
    assert list(iter_matches(text, "page")) == find_all_matches(text, "page")


def test_iter_matches_empty_term_yields_nothing():
    assert list(iter_matches("anything", "")) == []


def test_iter_matches_empty_text_yields_nothing():
    assert list(iter_matches("", "page")) == []


def test_iter_matches_is_lazy():
    # A huge input with a match very early: islice must return the first hit
    # without scanning/among building the whole result list.
    text = "page" + ("x" * 1_000_000)
    first_two = list(itertools.islice(iter_matches(text, "x"), 2))
    assert [m.start for m in first_two] == [4, 5]


def test_iter_matches_line_and_preview():
    text = "l1\n  hit here  \nl3"
    (m,) = list(iter_matches(text, "hit"))
    assert m.line == 2
    assert m.preview == "hit here"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_search.py -v -k iter_matches`
Expected: FAIL — `ImportError: cannot import name 'iter_matches'`.

- [ ] **Step 3: Add `iter_matches` and delegate `find_all_matches` to it**

In `pgtp_editor/ui/search.py`, replace the existing `find_all_matches` function body with a generator plus a thin list wrapper (keep `_line_preview` and `Match` unchanged):

```python
def iter_matches(text: str, term: str):
    """Yield every non-overlapping case-insensitive match of `term` lazily,
    left-to-right, advancing by len(term) after each hit. Empty term/text
    yields nothing. This is the single scan implementation; find_all_matches
    is list(iter_matches(...))."""
    if not term:
        return
    lowered_text = text.lower()
    lowered_term = term.lower()
    term_len = len(term)
    pos = 0
    while True:
        found = lowered_text.find(lowered_term, pos)
        if found == -1:
            break
        line = text.count("\n", 0, found) + 1
        yield Match(start=found, line=line, preview=_line_preview(text, found))
        pos = found + term_len


def find_all_matches(text: str, term: str) -> list[Match]:
    """Return every non-overlapping case-insensitive match of `term`
    (list form of iter_matches). Empty `term` -> []."""
    return list(iter_matches(text, term))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_search.py -v`
Expected: PASS (new `iter_matches` tests + all pre-existing `find_all_matches`/`find_next` tests).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/search.py tests/ui/test_search.py
git commit -m "feat: add lazy search.iter_matches; find_all_matches delegates to it"
```

---

## Task 2: FindReplaceBar — Stop toggle, stop callback, status callback, Replace All count

**Files:**
- Modify: `pgtp_editor/ui/find_replace_bar.py`
- Test: `tests/ui/test_find_replace_bar.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/ui/test_find_replace_bar.py` (the `_editor`, `_select` helpers exist at the top from the search-replace work):

```python
def test_set_find_all_running_toggles_button_label(qtbot):
    editor = _editor(qtbot, "page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    assert bar._find_all_button.text() == "Find All"
    bar.set_find_all_running(True)
    assert bar._find_all_button.text() == "Stop"
    bar.set_find_all_running(False)
    assert bar._find_all_button.text() == "Find All"


def test_find_all_calls_on_find_all_when_idle(qtbot):
    editor = _editor(qtbot, "page page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    calls = []
    bar.set_on_find_all(lambda term: calls.append(term))
    bar._find_field.setText("page")
    bar.find_all()
    assert calls == ["page"]


def test_find_all_calls_stop_callback_when_running(qtbot):
    editor = _editor(qtbot, "page page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    find_calls, stop_calls = [], []
    bar.set_on_find_all(lambda term: find_calls.append(term))
    bar.set_on_stop_find_all(lambda: stop_calls.append(True))
    bar._find_field.setText("page")
    bar.set_find_all_running(True)  # simulate an active run
    bar.find_all()
    assert stop_calls == [True]
    assert find_calls == []  # does NOT start a new find while running


def test_replace_all_reports_status_count(qtbot):
    editor = _editor(qtbot, "page page PAGE")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    messages = []
    bar.set_on_status(lambda msg: messages.append(msg))
    bar._find_field.setText("page")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "X X X"
    assert messages == ['3 replacement(s) for "page"']


def test_replace_all_reports_zero_when_no_matches(qtbot):
    editor = _editor(qtbot, "nothing here")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    messages = []
    bar.set_on_status(lambda msg: messages.append(msg))
    bar._find_field.setText("zzz")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "nothing here"
    assert messages == ['0 replacement(s) for "zzz"']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_find_replace_bar.py -v -k "find_all_running or stop_callback or on_find_all_when_idle or reports_status or reports_zero"`
Expected: FAIL — `AttributeError` on `set_find_all_running` / `set_on_stop_find_all` / `set_on_status`.

- [ ] **Step 3: Implement**

In `pgtp_editor/ui/find_replace_bar.py`:

(a) In `__init__`, right after `self._on_find_all = on_find_all or (lambda term: None)`, add:

```python
        self._on_stop_find_all: Callable[[], None] = lambda: None
        self._on_status: Callable[[str], None] = lambda msg: None
        self._find_all_running = False
```

(b) After `set_on_find_all`, add the two setters and the running-state toggle:

```python
    def set_on_stop_find_all(self, callback: Callable[[], None]) -> None:
        self._on_stop_find_all = callback

    def set_on_status(self, callback: Callable[[str], None]) -> None:
        self._on_status = callback

    def set_find_all_running(self, running: bool) -> None:
        """Driven by the Find All controller: flips the button between
        'Find All' (idle) and 'Stop' (a streaming run is active)."""
        self._find_all_running = running
        self._find_all_button.setText("Stop" if running else "Find All")
```

(c) Replace `find_all` with the running-aware version:

```python
    def find_all(self) -> None:
        if self._find_all_running:
            self._on_stop_find_all()
            return
        term = self._find_field.text()
        if not term:
            return
        self._on_find_all(term)
```

(d) Replace `replace_all` so it always reports a count (including 0) and drops the early return:

```python
    def replace_all(self) -> None:
        term = self._find_field.text()
        if not term:
            return
        replacement = self._replace_field.text()
        text = self._editor.toPlainText()
        matches = search.find_all_matches(text, term)
        if matches:
            cursor = QTextCursor(self._editor.document())
            cursor.beginEditBlock()
            for match in reversed(matches):
                cursor.setPosition(match.start)
                cursor.setPosition(match.start + len(term), QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(replacement)
            cursor.endEditBlock()
        self._on_status(f'{len(matches)} replacement(s) for "{term}"')
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_find_replace_bar.py -v`
Expected: PASS (new tests + all pre-existing bar tests, including the existing single-undo replace-all test which is unaffected by the added status call).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/find_replace_bar.py tests/ui/test_find_replace_bar.py
git commit -m "feat: FindReplaceBar Stop toggle + stop/status callbacks + Replace All count"
```

---

## Task 3: Chunked streaming Find All driver in MainWindow

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_main_window.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/ui/test_main_window.py`:

```python
def test_find_all_streaming_completes_and_reports_final_count(qtbot):
    from PySide6.QtCore import Qt as _Qt
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("page one\nsecond\nthird page here")
    bar = window.center_stage.find_replace_bar

    window._populate_find_all_results("page")
    qtbot.waitUntil(lambda: not bar._find_all_running, timeout=5000)

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert texts == [
        "[Find] line 1: page one",
        "[Find] line 3: third page here",
        '[Find] 2 match(es) for "page"',
    ]
    assert window.audit_panel.item(0).data(_Qt.ItemDataRole.UserRole) == 1
    assert window.statusBar().currentMessage() == "Found 2 item(s)"
    assert bar._find_all_button.text() == "Find All"


def test_find_all_stop_keeps_partial_results(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    # Many matches so a single batch is a strict subset of the total.
    window.center_stage.xml_editor.setPlainText("\n".join(f"a{i}" for i in range(500)))
    bar = window.center_stage.find_replace_bar

    window._populate_find_all_results("a")
    # Take manual control of stepping so the test is deterministic (no timing).
    window._find_all_timer.stop()
    window._find_all_step()          # process exactly one batch
    partial = window._find_all_count
    assert 0 < partial < 500
    results_before_summary = window.audit_panel.count()

    window._stop_find_all()
    window._find_all_step()          # observes the stop flag -> finishes

    assert bar._find_all_running is False
    assert bar._find_all_button.text() == "Find All"
    # Partial results kept; exactly one summary line appended after them.
    assert window.audit_panel.count() == results_before_summary + 1
    summary = window.audit_panel.item(window.audit_panel.count() - 1).text()
    assert summary == f'[Find] {partial} match(es) for "a"'
    assert window.statusBar().currentMessage() == f"Find All stopped — found {partial} item(s)"


def test_find_all_live_count_status_after_a_batch(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("\n".join(f"a{i}" for i in range(500)))

    window._populate_find_all_results("a")
    window._find_all_timer.stop()
    window._find_all_step()
    msg = window.statusBar().currentMessage()
    assert msg.startswith('Finding "a"… found ')


def test_find_all_restart_does_not_leak_a_second_timer(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("page page")
    bar = window.center_stage.find_replace_bar

    window._populate_find_all_results("page")
    first_timer = window._find_all_timer
    window._populate_find_all_results("page")  # re-trigger while (nominally) active
    # The previous timer was stopped/dropped; a fresh one is in place.
    assert window._find_all_timer is not first_timer
    assert not first_timer.isActive()
    qtbot.waitUntil(lambda: not bar._find_all_running, timeout=5000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "streaming or stop_keeps or live_count or restart_does_not_leak"`
Expected: FAIL — `_populate_find_all_results` is still synchronous (no `_find_all_timer`, no running toggle, no live/final status).

- [ ] **Step 3: Implement the chunked driver**

In `pgtp_editor/ui/main_window.py`:

(a) Add `QTimer` to the `PySide6.QtCore` import (currently `from PySide6.QtCore import Qt` — make it `from PySide6.QtCore import Qt, QTimer`).

(b) Add a batch-size constant next to `_FIND_RESULT_PREFIX`:

```python
_FIND_ALL_BATCH = 200
```

(c) In `__init__`, initialise the run state and wire the two new callbacks. Immediately after the existing
`self.center_stage.find_replace_bar.set_on_find_all(self._populate_find_all_results)` line, add:

```python
        self.center_stage.find_replace_bar.set_on_stop_find_all(self._stop_find_all)
        self.center_stage.find_replace_bar.set_on_status(self.statusBar().showMessage)
        self._find_all_timer = None
        self._find_all_iter = None
        self._find_all_stop = False
        self._find_all_count = 0
        self._find_all_term = ""
```

(d) Replace the whole synchronous `_populate_find_all_results` method with the streaming driver (keep `_clear_find_results` and `_on_audit_item_clicked` exactly as they are):

```python
    def _populate_find_all_results(self, term: str) -> None:
        """Start a streaming Find All: results are appended to the Audit panel
        a batch at a time on a 0ms QTimer, yielding to the event loop between
        batches so the UI stays responsive and Stop takes effect promptly."""
        self._cancel_find_all_timer()
        self._clear_find_results()
        self._find_all_term = term
        self._find_all_count = 0
        self._find_all_stop = False
        text = self.center_stage.xml_editor.toPlainText()
        self._find_all_iter = search.iter_matches(text, term)
        self.center_stage.find_replace_bar.set_find_all_running(True)
        self.statusBar().showMessage(f'Finding "{term}"…')
        self._find_all_timer = QTimer(self)
        self._find_all_timer.timeout.connect(self._find_all_step)
        self._find_all_timer.start(0)

    def _find_all_step(self) -> None:
        if self._find_all_stop:
            self._finish_find_all(stopped=True)
            return
        for _ in range(_FIND_ALL_BATCH):
            try:
                match = next(self._find_all_iter)
            except StopIteration:
                self._finish_find_all(stopped=False)
                return
            item = QListWidgetItem(f"{_FIND_RESULT_PREFIX}line {match.line}: {match.preview}")
            item.setData(Qt.ItemDataRole.UserRole, match.line)
            self.audit_panel.addItem(item)
            self._find_all_count += 1
        self.statusBar().showMessage(
            f'Finding "{self._find_all_term}"… found {self._find_all_count}'
        )

    def _finish_find_all(self, stopped: bool) -> None:
        self._cancel_find_all_timer()
        summary = QListWidgetItem(
            f'{_FIND_RESULT_PREFIX}{self._find_all_count} match(es) for "{self._find_all_term}"'
        )
        self.audit_panel.addItem(summary)  # no line data -> clicking is a no-op
        self.center_stage.find_replace_bar.set_find_all_running(False)
        if stopped:
            self.statusBar().showMessage(
                f"Find All stopped — found {self._find_all_count} item(s)"
            )
        else:
            self.statusBar().showMessage(f"Found {self._find_all_count} item(s)")

    def _stop_find_all(self) -> None:
        """Request that an in-flight streaming Find All stop; the next
        _find_all_step tick finishes the run, keeping results found so far."""
        self._find_all_stop = True

    def _cancel_find_all_timer(self) -> None:
        if self._find_all_timer is not None:
            self._find_all_timer.stop()
            self._find_all_timer = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "streaming or stop_keeps or live_count or restart_does_not_leak"`
Expected: PASS (4 passed). The pre-existing Find-All tests may assert the old synchronous behaviour — see Task 4.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_main_window.py
git commit -m "feat: stream Find All in QTimer batches with Stop and live/final status"
```

---

## Task 4: Reconcile pre-existing synchronous Find-All tests

The search-replace work added synchronous Find-All tests (e.g. `test_find_all_populates_audit_panel_with_line_items_and_summary`, `test_find_all_clears_only_prior_find_entries`, `test_find_all_via_menu_populates_audit_panel`) that call `_populate_find_all_results(...)` (or trigger the menu) and then assert the Audit panel contents **synchronously** — which no longer holds now that population is deferred onto a timer.

**Files:**
- Modify: `tests/ui/test_main_window.py`

- [ ] **Step 1: Identify the affected tests**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "find_all or audit"`
Expected: the streaming tests from Task 3 PASS; some older synchronous Find-All tests now FAIL (they read `audit_panel` immediately after `_populate_find_all_results` returns, before any timer tick).

- [ ] **Step 2: Make each affected test drain the run deterministically**

For every pre-existing test that calls `_populate_find_all_results(...)` (or triggers the "Find All" menu action) and then inspects `audit_panel`, insert a drain step immediately after the trigger, before the assertions:

```python
    qtbot.waitUntil(lambda: not window.center_stage.find_replace_bar._find_all_running, timeout=5000)
```

Do **not** weaken the assertions themselves — the final Audit-panel contents (result items + summary line, `UserRole` line data, `[Find]`-only clearing, click-to-navigate) are unchanged; only the timing is. The summary text format (`[Find] N match(es) for "term"`) and result format (`[Find] line N: preview`) are identical to before.

If a test triggers Find All via the Edit menu and pre-populates the term through `bar._find_field.setText(...)`, keep that; just add the `waitUntil` drain before asserting.

- [ ] **Step 3: Run the affected tests**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "find_all or audit"`
Expected: PASS (both the Task 3 streaming tests and the reconciled pre-existing tests).

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_main_window.py
git commit -m "test: drain streaming Find All before asserting in pre-existing tests"
```

---

## Task 5: Full-suite verification

**Files:** none

- [ ] **Step 1: Run the entire suite**

Run: `python -m pytest -q`
Expected: all green, no test hits the 60s timeout (no unpatched-modal hang; this feature shows no modals). Real-sample tests SKIP only if the gitignored `sample/*.pgtp` are absent.

- [ ] **Step 2: Confirm the Replace-All menu path also shows the count**

The Edit-menu "Replace All" action calls the bar's `replace_all`, which now emits the status message through the injected `on_status` (wired to `statusBar().showMessage`). Verify the existing `test_replace_all_via_menu_mutates_document` still passes (it asserts the document mutation; the added status call is side-effect only and must not break it).

- [ ] **Step 3: Final commit if anything is uncommitted**

```bash
git status
# if clean, nothing to do; otherwise:
git add -A && git commit -m "chore: finalize Find All streaming + Replace All count"
```

---

## Requirement → task traceability (self-review)
- Lazy `iter_matches` + `find_all_matches` delegation → **Task 1** (spec §3.1).
- Continuous/streaming output, batch-at-a-time → **Task 3** (`_find_all_step`, spec §3.2).
- Stop button keeping partial results → **Tasks 2 + 3** (`set_find_all_running` toggle, `_stop_find_all`, `_finish_find_all(stopped=True)`, spec §3.2/§3.3).
- "Found [N] items" in the status bar (live + final + stopped) → **Task 3** (spec §3.2).
- Replace All "[N] replacements" status message → **Task 2** (spec §3.3).
- Clean restart / no leaked timer, snapshot-stable iteration → **Task 3** (`_cancel_find_all_timer`, spec §4).
- Reconcile prior synchronous tests → **Task 4**.
