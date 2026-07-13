# PGTP Editor — Search & Replace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Find / Find Next / Find All / Replace / Replace All over the Raw XML editor's text, via a modeless find/replace bar below the editor and matching Edit-menu actions, with Find All reporting into the existing Audit panel.

**Architecture:** A pure Qt-free search core (`pgtp_editor/ui/search.py`) provides `find_next` and `find_all_matches`/`Match`. A modeless `FindReplaceBar(QWidget)` (`pgtp_editor/ui/find_replace_bar.py`) drives the core against an injected editor via a small interface, and delegates Find All to an injected callback. The Raw XML tab becomes a small container widget (editor + bar) while preserving `center_stage.xml_editor`. `MainWindow` wires five Edit-menu actions (each sharing the bar's code path) and populates/handles clickable `[Find]` entries in the Audit panel. Only one small method is added to the concurrently-edited `xml_editor.py`.

**Tech Stack:** Python 3.13, PySide6 (Qt widgets), pytest, pytest-qt.

---

## Current-state facts confirmed by reading this worktree's code (do not re-derive these — just use them)

- `pgtp_editor/ui/xml_editor.py`: `XmlEditor(QPlainTextEdit)` already has `navigate_to_line(line)` (1-based; `findBlockByNumber(line - 1)` + `centerCursor()` + full-line highlight), `line_text(line)` (1-based), `select_range_on_line(line, start, end)`, `set_line_wrap_enabled(enabled)`, and a `keyPressEvent` override handling `<`/quotes/`>`/Return. It has **no** `replace_current_selection` method yet. It inherits `toPlainText`, `textCursor`, `setTextCursor`, `document`, `setFocus`, `ensureCursorVisible`, `undo` from `QPlainTextEdit`.
- `pgtp_editor/ui/center_stage.py`: `CenterStage(QTabWidget)` builds `self.xml_editor = XmlEditor()` and `self.raw_xml_tab_index = self.addTab(self.xml_editor, "Raw XML")` — the tab widget **is** the editor today. Also has `diff_merge_panel`/`diff_merge_tab_index`, a `caption_management_tab_index`, and `set_raw_xml_tab_visible(visible)`.
- `pgtp_editor/ui/main_window.py`: `_build_edit_menu` currently ends the Find block with `self._add_stub_action(menu, "Find...")` then `find_replace = self._add_stub_action(menu, "Find & Replace...")` / `find_replace.setShortcut("Ctrl+H")`. `_build_menu_bar` (last statement of `__init__`) calls `_build_view_menu` (creates `self._raw_xml_panel_action`) **before** `_build_edit_menu`. `self.center_stage` is created in `__init__` before `_build_menu_bar`. `audit_panel` is a `QListWidget`; schema entries are added as plain strings all starting with `"[Schema] "`. `_handle_parse_failure` reveals the Raw XML tab via `set_raw_xml_tab_visible(True)` + `self._raw_xml_panel_action.setChecked(True)` + `setCurrentIndex(raw_xml_tab_index)`. The QtWidgets import block imports `QListWidget` but not `QListWidgetItem`; `Qt` is imported from `PySide6.QtCore`.
- `tests/ui/test_center_stage.py`: asserts three tabs in order; raw tab hidden by default; `set_raw_xml_tab_visible`; diff panel identity; and (the one that must change) `test_raw_xml_tab_holds_a_real_xml_editor` asserts both `isinstance(stage.xml_editor, XmlEditor)` **and** `stage.widget(stage.raw_xml_tab_index) is stage.xml_editor`.
- `tests/ui/test_menus.py`: `test_edit_menu_contents` asserts the exact label list `["Undo","Redo","―","Cut","Copy","Paste","Delete","―","Find...","Find & Replace...","―","Preferences..."]`; `test_find_and_replace_has_ctrl_h_shortcut` asserts `find_action(edit_menu, "Find & Replace...").shortcut().toString() == "Ctrl+H"`. Helpers `action_labels`, `find_top_menu`, `find_action` live in `tests/ui/_menu_helpers.py` (separators render as `"―"`).
- `QKeySequence(...).toString()` was verified during this plan's authoring to return exactly: `"Ctrl+F"`, `"F3"`, `"Ctrl+Shift+F"`, `"Ctrl+R"`, `"Ctrl+Alt+Return"` for the five shortcuts used here (no normalization surprises).
- Tests use `qtbot` (pytest-qt), `qtbot.addWidget(...)`; the offscreen Qt platform is already configured for the suite.

---

## File Structure

- **Create** `pgtp_editor/ui/search.py` — pure Qt-free search core: `Match`, `find_next`, `find_all_matches` (Task 1).
- **Create** `pgtp_editor/ui/find_replace_bar.py` — `FindReplaceBar(QWidget)` (Tasks 3–4).
- **Modify** `pgtp_editor/ui/xml_editor.py` — add `replace_current_selection(text)` only (Task 2).
- **Modify** `pgtp_editor/ui/center_stage.py` — Raw XML tab container (Task 5).
- **Modify** `pgtp_editor/ui/main_window.py` — Edit-menu rewiring + Audit-panel Find All wiring (Tasks 6–7).
- **Modify** `tests/ui/test_menus.py` and `tests/ui/test_center_stage.py` — update affected assertions (Tasks 6, 5).
- **Create** `tests/ui/test_search.py`, `tests/ui/test_find_replace_bar.py`; **extend** `tests/ui/test_main_window.py`.

---

## Task 1: Qt-free search core (`search.py`)

**Files:**
- Create: `pgtp_editor/ui/search.py`
- Test: `tests/ui/test_search.py` (new file — Qt-free)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_search.py`:

```python
from pgtp_editor.ui.search import Match, find_all_matches, find_next


# -- find_next -------------------------------------------------------------

def test_find_next_first_occurrence_at_or_after_from_pos():
    assert find_next("the Page and a Page", "page", 0) == 4


def test_find_next_case_insensitive():
    assert find_next("Hello PAGE world", "page", 0) == 6


def test_find_next_skips_earlier_occurrence():
    # from_pos past the first match -> returns the second.
    assert find_next("page and page", "page", 1) == 9


def test_find_next_wraps_when_none_after_from_pos():
    # Only match is before from_pos; wrap brings us back to it.
    assert find_next("page then nothing", "page", 5, wrap=True) == 0


def test_find_next_no_wrap_returns_none_when_none_after_from_pos():
    assert find_next("page then nothing", "page", 5, wrap=False) is None


def test_find_next_no_match_returns_none():
    assert find_next("nothing here", "zzz", 0) is None


def test_find_next_empty_term_returns_none():
    assert find_next("anything", "", 0) is None


# -- find_all_matches ------------------------------------------------------

def test_find_all_matches_multiple_hits_in_order():
    matches = find_all_matches("page PAGE page", "page")
    assert [m.start for m in matches] == [0, 5, 10]


def test_find_all_matches_no_match_returns_empty():
    assert find_all_matches("nothing", "zzz") == []


def test_find_all_matches_empty_term_returns_empty():
    assert find_all_matches("anything", "") == []


def test_find_all_matches_adjacent_matches_all_found():
    assert [m.start for m in find_all_matches("abab", "ab")] == [0, 2]
    assert [m.start for m in find_all_matches("aa", "a")] == [0, 1]


def test_find_all_matches_overlapping_not_all_found():
    # Non-overlapping left-to-right scan advancing by len(term): "aaa"/"aa"
    # yields ONE match at 0 (resumes at index 2), not two at 0 and 1.
    assert [m.start for m in find_all_matches("aaa", "aa")] == [0]


def test_find_all_matches_line_numbers_are_one_based():
    text = "line one\nline two\nhere is page\nline four"
    matches = find_all_matches(text, "page")
    assert len(matches) == 1
    assert matches[0].line == 3


def test_find_all_matches_preview_is_trimmed_whole_line():
    text = "a\n    indented page here    \nb"
    matches = find_all_matches(text, "page")
    assert len(matches) == 1
    assert matches[0].preview == "indented page here"


def test_match_is_frozen_dataclass():
    m = Match(start=0, line=1, preview="x")
    assert (m.start, m.line, m.preview) == (0, 1, "x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.ui.search'`

- [ ] **Step 3: Create `search.py`**

Create `pgtp_editor/ui/search.py`:

```python
# pgtp_editor/ui/search.py
"""Pure, Qt-free case-insensitive substring search over plain text.

Serves the FindReplaceBar UI widget (pgtp_editor/ui/find_replace_bar.py) but
has no Qt dependency itself, so it is unit-testable without a QApplication.
Matching is always plain case-insensitive substring: no case/word/regex
options exist anywhere in this sub-project.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    """One case-insensitive substring match found by find_all_matches.

    start:   0-based character index of the match within the full text.
    line:    1-based line number the match starts on (matching the
             XmlEditor.navigate_to_line / line_text 1-based convention).
    preview: the whitespace-trimmed text of that whole line.
    """

    start: int
    line: int
    preview: str


def find_next(text: str, term: str, from_pos: int, *, wrap: bool = True) -> int | None:
    """Return the 0-based index of the next case-insensitive occurrence of
    `term` at or after `from_pos`. If none is found at/after `from_pos` and
    `wrap` is True, wrap around and search from the start. Returns None if
    `term` is empty or does not occur in `text` at all.
    """
    if not term:
        return None
    lowered_text = text.lower()
    lowered_term = term.lower()
    start = max(0, from_pos)
    found = lowered_text.find(lowered_term, start)
    if found != -1:
        return found
    if wrap:
        found = lowered_text.find(lowered_term, 0)
        if found != -1:
            return found
    return None


def find_all_matches(text: str, term: str) -> list[Match]:
    """Return every non-overlapping case-insensitive match of `term`,
    scanned left-to-right, advancing by len(term) after each hit (adjacent
    matches all found; overlapping ones not). Empty `term` -> []."""
    if not term:
        return []
    lowered_text = text.lower()
    lowered_term = term.lower()
    term_len = len(term)
    matches: list[Match] = []
    pos = 0
    while True:
        found = lowered_text.find(lowered_term, pos)
        if found == -1:
            break
        line = text.count("\n", 0, found) + 1
        matches.append(Match(start=found, line=line, preview=_line_preview(text, found)))
        pos = found + term_len
    return matches


def _line_preview(text: str, index: int) -> str:
    """The whitespace-trimmed text of the line that character `index`
    falls on."""
    line_start = text.rfind("\n", 0, index) + 1  # -1 -> 0 for the first line
    line_end = text.find("\n", index)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_search.py -v`
Expected: PASS (15 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/search.py tests/ui/test_search.py
git commit -m "feat: add Qt-free case-insensitive search core (find_next/find_all_matches)"
```

---

## Task 2: `XmlEditor.replace_current_selection`

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (add one method to `XmlEditor`)
- Test: `tests/ui/test_xml_editor_replace.py` (new file — `pytest-qt`)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_xml_editor_replace.py`:

```python
from PySide6.QtGui import QTextCursor

from pgtp_editor.ui.xml_editor import XmlEditor


def test_replace_current_selection_replaces_selected_text(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("hello world")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)  # select "hello"
    editor.setTextCursor(cursor)

    editor.replace_current_selection("goodbye")
    assert editor.toPlainText() == "goodbye world"


def test_replace_current_selection_noop_without_selection(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("hello world")
    cursor = editor.textCursor()
    cursor.setPosition(5)  # no selection, just a caret
    editor.setTextCursor(cursor)

    editor.replace_current_selection("XXX")
    assert editor.toPlainText() == "hello world"


def test_replace_current_selection_is_single_undo_step(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("hello world")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    editor.replace_current_selection("goodbye")
    assert editor.toPlainText() == "goodbye world"
    editor.undo()
    assert editor.toPlainText() == "hello world"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor_replace.py -v`
Expected: FAIL — `AttributeError: 'XmlEditor' object has no attribute 'replace_current_selection'`

- [ ] **Step 3: Add the method**

In `pgtp_editor/ui/xml_editor.py`, add this method to the `XmlEditor` class (place it just after `select_range_on_line`, before `set_line_wrap_enabled`):

```python
    def replace_current_selection(self, text: str) -> None:
        """Replace the current selection's text with `text` as a single undo
        step. No-op if there is no selection. Used by FindReplaceBar's
        Replace (Search & Replace sub-project)."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        cursor.insertText(text)  # QTextCursor.insertText replaces the selection
        self.setTextCursor(cursor)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_xml_editor_replace.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor_replace.py
git commit -m "feat: add XmlEditor.replace_current_selection for find/replace"
```

---

## Task 3: `FindReplaceBar` — find mode (show, prefill, Find Next, Esc)

**Files:**
- Create: `pgtp_editor/ui/find_replace_bar.py`
- Test: `tests/ui/test_find_replace_bar.py` (new file — `pytest-qt`, real `XmlEditor`)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_find_replace_bar.py`:

```python
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.find_replace_bar import FindReplaceBar
from pgtp_editor.ui.xml_editor import XmlEditor


def _editor(qtbot, text=""):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    return editor


def _select(editor, start, end):
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def test_show_find_prefills_from_selection(qtbot):
    editor = _editor(qtbot, "alpha beta gamma")
    _select(editor, 6, 10)  # "beta"
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar.show_find()
    assert bar._find_field.text() == "beta"
    assert bar.isVisible() is True


def test_show_find_no_selection_leaves_field_unchanged(qtbot):
    editor = _editor(qtbot, "alpha beta")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("prev")
    bar.show_find()
    assert bar._find_field.text() == "prev"


def test_find_next_selects_the_match(qtbot):
    editor = _editor(qtbot, "one page two page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("page")
    bar.find_next()
    cursor = editor.textCursor()
    assert cursor.selectedText() == "page"
    assert cursor.selectionStart() == 4


def test_find_next_advances_to_second_match(qtbot):
    editor = _editor(qtbot, "one page two page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("page")
    bar.find_next()  # selects match at 4
    bar.find_next()  # advances to match at 13
    assert editor.textCursor().selectionStart() == 13


def test_find_next_wraps_around(qtbot):
    editor = _editor(qtbot, "one page two page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("page")
    bar.find_next()  # 4
    bar.find_next()  # 13
    bar.find_next()  # wraps back to 4
    assert editor.textCursor().selectionStart() == 4


def test_find_next_empty_term_is_noop(qtbot):
    editor = _editor(qtbot, "one page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("")
    bar.find_next()
    assert editor.textCursor().hasSelection() is False


def test_escape_hides_bar_and_refocuses_editor(qtbot):
    editor = _editor(qtbot, "one page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar.show_find()
    QApplication.processEvents()
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    bar.keyPressEvent(event)
    assert bar.isVisible() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_find_replace_bar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.ui.find_replace_bar'`

- [ ] **Step 3: Create `find_replace_bar.py` (find mode only for now)**

Create `pgtp_editor/ui/find_replace_bar.py`:

```python
# pgtp_editor/ui/find_replace_bar.py
"""FindReplaceBar: a modeless find/replace bar shown below the XmlEditor
inside the Raw XML tab. Operates on an injected editor via a small, explicit
interface (toPlainText / textCursor / setTextCursor / setFocus / document /
replace_current_selection) so it stays decoupled from MainWindow. Find All is
delegated to an injected callback."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.ui import search


class FindReplaceBar(QWidget):
    def __init__(self, editor, on_find_all: Callable[[str], None] | None = None, parent=None):
        super().__init__(parent)
        self._editor = editor
        self._on_find_all = on_find_all or (lambda term: None)

        self._find_field = QLineEdit()
        self._find_field.setPlaceholderText("Find")
        self._find_next_button = QPushButton("Find Next")
        self._find_all_button = QPushButton("Find All")

        self._replace_field = QLineEdit()
        self._replace_field.setPlaceholderText("Replace with")
        self._replace_button = QPushButton("Replace")
        self._replace_all_button = QPushButton("Replace All")

        find_row = QHBoxLayout()
        find_row.addWidget(self._find_field)
        find_row.addWidget(self._find_next_button)
        find_row.addWidget(self._find_all_button)

        self._replace_row_widget = QWidget()
        replace_row = QHBoxLayout(self._replace_row_widget)
        replace_row.setContentsMargins(0, 0, 0, 0)
        replace_row.addWidget(self._replace_field)
        replace_row.addWidget(self._replace_button)
        replace_row.addWidget(self._replace_all_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addLayout(find_row)
        layout.addWidget(self._replace_row_widget)

        self._find_next_button.clicked.connect(self.find_next)
        self._find_all_button.clicked.connect(self.find_all)
        self._replace_button.clicked.connect(self.replace)
        self._replace_all_button.clicked.connect(self.replace_all)
        self._find_field.returnPressed.connect(self.find_next)

        self.hide()

    def set_on_find_all(self, callback: Callable[[str], None]) -> None:
        self._on_find_all = callback

    # -- show / hide --------------------------------------------------------

    def show_find(self) -> None:
        self._replace_row_widget.hide()
        self._prefill_from_selection()
        self.show()
        self._find_field.setFocus()
        self._find_field.selectAll()

    def show_replace(self) -> None:
        self._replace_row_widget.show()
        self._prefill_from_selection()
        self.show()
        self._find_field.setFocus()
        self._find_field.selectAll()

    def _prefill_from_selection(self) -> None:
        selected = self._editor.textCursor().selectedText()
        if selected:
            self._find_field.setText(selected)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self._editor.setFocus()
            return
        super().keyPressEvent(event)

    # -- operations ---------------------------------------------------------

    def find_next(self) -> None:
        term = self._find_field.text()
        if not term:
            return
        text = self._editor.toPlainText()
        cursor = self._editor.textCursor()
        from_pos = max(cursor.selectionEnd(), cursor.position())
        index = search.find_next(text, term, from_pos, wrap=True)
        if index is None:
            return
        self._select_span(index, len(term))

    def find_all(self) -> None:
        term = self._find_field.text()
        if not term:
            return
        self._on_find_all(term)

    def replace(self) -> None:
        term = self._find_field.text()
        if not term:
            return
        cursor = self._editor.textCursor()
        selected = cursor.selectedText()
        if selected and selected.lower() == term.lower():
            self._editor.replace_current_selection(self._replace_field.text())
        self.find_next()

    def replace_all(self) -> None:
        term = self._find_field.text()
        if not term:
            return
        replacement = self._replace_field.text()
        text = self._editor.toPlainText()
        matches = search.find_all_matches(text, term)
        if not matches:
            return
        cursor = QTextCursor(self._editor.document())
        cursor.beginEditBlock()
        for match in reversed(matches):
            cursor.setPosition(match.start)
            cursor.setPosition(match.start + len(term), QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)
        cursor.endEditBlock()

    def _select_span(self, index: int, length: int) -> None:
        cursor = self._editor.textCursor()
        cursor.setPosition(index)
        cursor.setPosition(index + length, QTextCursor.MoveMode.KeepAnchor)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()
```

> Note: the full class (including `replace`/`replace_all`) is written now so it does not need to be re-shown in Task 4 — Task 4 only adds tests for the replace behaviors already present here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_find_replace_bar.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/find_replace_bar.py tests/ui/test_find_replace_bar.py
git commit -m "feat: add FindReplaceBar with find/find-next/prefill/esc"
```

---

## Task 4: `FindReplaceBar` — replace and replace-all behavior tests

**Files:**
- Modify: `tests/ui/test_find_replace_bar.py` (add replace tests; no production change — `replace`/`replace_all` already implemented in Task 3)

- [ ] **Step 1: Write the tests**

Append to `tests/ui/test_find_replace_bar.py` (the imports `_editor`, `_select`, `QTextCursor` are already present at the top of the file from Task 3):

```python
def test_replace_replaces_current_matching_selection_then_advances(qtbot):
    editor = _editor(qtbot, "page one page two")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("page")
    bar._replace_field.setText("PAGE")
    _select(editor, 0, 4)  # current selection == "page", a match

    bar.replace()
    # First occurrence replaced, and selection advanced to the next "page".
    assert editor.toPlainText() == "PAGE one page two"
    assert editor.textCursor().selectedText() == "page"


def test_replace_without_matching_selection_only_finds_next(qtbot):
    editor = _editor(qtbot, "page one page two")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)  # no selection
    bar._find_field.setText("page")
    bar._replace_field.setText("PAGE")

    bar.replace()
    # Nothing replaced; just selected the first match.
    assert editor.toPlainText() == "page one page two"
    assert editor.textCursor().selectedText() == "page"


def test_replace_all_replaces_every_occurrence(qtbot):
    editor = _editor(qtbot, "page page PAGE")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("page")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "X X X"


def test_replace_all_is_single_undo_step(qtbot):
    editor = _editor(qtbot, "page page page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("page")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "X X X"
    editor.undo()  # a single undo must revert the entire Replace All
    assert editor.toPlainText() == "page page page"


def test_replace_all_with_longer_replacement_keeps_indices_valid(qtbot):
    editor = _editor(qtbot, "ab ab ab")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("ab")
    bar._replace_field.setText("LONGER")
    bar.replace_all()
    assert editor.toPlainText() == "LONGER LONGER LONGER"


def test_replace_all_no_matches_is_noop(qtbot):
    editor = _editor(qtbot, "nothing here")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("zzz")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "nothing here"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_find_replace_bar.py -v`
Expected: PASS (all, including the 6 new replace tests). These pass immediately because `replace`/`replace_all` were implemented in Task 3; if any fail, fix `replace`/`replace_all` in `find_replace_bar.py` and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_find_replace_bar.py
git commit -m "test: cover FindReplaceBar replace and single-undo replace-all"
```

---

## Task 5: Raw XML tab container in `CenterStage`

**Files:**
- Modify: `pgtp_editor/ui/center_stage.py`
- Modify: `tests/ui/test_center_stage.py` (update `test_raw_xml_tab_holds_a_real_xml_editor`)

- [ ] **Step 1: Update the affected existing test to the new container shape**

Replace the body of `test_raw_xml_tab_holds_a_real_xml_editor` in `tests/ui/test_center_stage.py` with:

```python
def test_raw_xml_tab_holds_a_real_xml_editor(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.xml_editor, XmlEditor)
    # The Raw XML tab now hosts a container widget (editor + find/replace
    # bar); xml_editor remains the accessor and lives inside that container.
    assert stage.widget(stage.raw_xml_tab_index) is stage.raw_xml_tab
    assert stage.xml_editor.parent() is stage.raw_xml_tab
```

Then add a new test after it:

```python
from pgtp_editor.ui.find_replace_bar import FindReplaceBar


def test_raw_xml_tab_container_holds_find_replace_bar(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.find_replace_bar, FindReplaceBar)
    assert stage.find_replace_bar.parent() is stage.raw_xml_tab
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_center_stage.py -v`
Expected: FAIL — `test_raw_xml_tab_holds_a_real_xml_editor` fails on `stage.raw_xml_tab` (no such attribute) and the new test fails on `stage.find_replace_bar` (no such attribute).

- [ ] **Step 3: Refactor `CenterStage` to the container**

Replace the full contents of `pgtp_editor/ui/center_stage.py` with:

```python
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from pgtp_editor.ui.diff_merge_panel import DiffMergePanel
from pgtp_editor.ui.find_replace_bar import FindReplaceBar
from pgtp_editor.ui.xml_editor import XmlEditor


class CenterStage(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.diff_merge_panel = DiffMergePanel()
        self.diff_merge_tab_index = self.addTab(self.diff_merge_panel, "Diff / Merge")
        self.caption_management_tab_index = self.addTab(QWidget(), "Caption Management")

        self.xml_editor = XmlEditor()
        self.find_replace_bar = FindReplaceBar(self.xml_editor)
        self.raw_xml_tab = QWidget()
        raw_layout = QVBoxLayout(self.raw_xml_tab)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(0)
        raw_layout.addWidget(self.xml_editor)
        raw_layout.addWidget(self.find_replace_bar)
        self.raw_xml_tab_index = self.addTab(self.raw_xml_tab, "Raw XML")
        self.setTabVisible(self.raw_xml_tab_index, False)

    def set_raw_xml_tab_visible(self, visible):
        self.setTabVisible(self.raw_xml_tab_index, visible)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_center_stage.py -v`
Expected: PASS (all, including the updated + new tests). `xml_editor.parent()` is the container because adding a widget to a layout reparents it to the layout's widget (`raw_xml_tab`).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass (in particular `tests/ui/test_menus.py::test_toggling_wrap_raw_xml_lines_changes_editor_line_wrap_mode`, which still reads `center_stage.xml_editor`, and `test_main_window.py`'s existing raw-tab tests).

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/center_stage.py tests/ui/test_center_stage.py
git commit -m "refactor: host XmlEditor + FindReplaceBar in a Raw XML tab container"
```

---

## Task 6: Edit-menu rewiring in `MainWindow`

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (`_build_edit_menu` + five handlers + `_reveal_raw_xml_tab`)
- Modify: `tests/ui/test_menus.py` (update Edit-menu assertions)

- [ ] **Step 1: Update the Edit-menu tests**

In `tests/ui/test_menus.py`, replace the body of `test_edit_menu_contents` with:

```python
def test_edit_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    assert action_labels(edit_menu) == [
        "Undo", "Redo", "―",
        "Cut", "Copy", "Paste", "Delete", "―",
        "Find...", "Find Next", "Find All", "Replace...", "Replace All", "―",
        "Preferences...",
    ]
```

Delete `test_find_and_replace_has_ctrl_h_shortcut` entirely and add in its place:

```python
def test_edit_menu_search_shortcuts(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    expected = {
        "Find...": "Ctrl+F",
        "Find Next": "F3",
        "Find All": "Ctrl+Shift+F",
        "Replace...": "Ctrl+R",
        "Replace All": "Ctrl+Alt+Return",
    }
    for label, combo in expected.items():
        action = find_action(edit_menu, label)
        assert action is not None
        assert action.shortcut().toString() == combo
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_menus.py -v -k "edit_menu"`
Expected: FAIL — `test_edit_menu_contents` fails on the label list (still has `"Find & Replace..."`); `test_edit_menu_search_shortcuts` fails because `find_action(edit_menu, "Find...")` has no shortcut set yet (`toString()` returns `""`).

- [ ] **Step 3: Rewrite `_build_edit_menu` and add the handlers**

In `pgtp_editor/ui/main_window.py`, replace `_build_edit_menu` with:

```python
    def _build_edit_menu(self):
        menu = self.menuBar().addMenu("Edit")
        self._add_stub_action(menu, "Undo")
        self._add_stub_action(menu, "Redo")
        menu.addSeparator()
        self._add_stub_action(menu, "Cut")
        self._add_stub_action(menu, "Copy")
        self._add_stub_action(menu, "Paste")
        self._add_stub_action(menu, "Delete")
        menu.addSeparator()

        find_action = menu.addAction("Find...")
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self._show_find_bar)

        find_next_action = menu.addAction("Find Next")
        find_next_action.setShortcut("F3")
        find_next_action.triggered.connect(self._find_next)

        find_all_action = menu.addAction("Find All")
        find_all_action.setShortcut("Ctrl+Shift+F")
        find_all_action.triggered.connect(self._find_all)

        replace_action = menu.addAction("Replace...")
        replace_action.setShortcut("Ctrl+R")
        replace_action.triggered.connect(self._show_replace_bar)

        replace_all_action = menu.addAction("Replace All")
        replace_all_action.setShortcut("Ctrl+Alt+Return")
        replace_all_action.triggered.connect(self._replace_all)

        menu.addSeparator()
        self._add_stub_action(menu, "Preferences...")
```

Add these handler methods to `MainWindow` (place them right after `_add_stub_action`):

```python
    def _reveal_raw_xml_tab(self):
        self.center_stage.set_raw_xml_tab_visible(True)
        self._raw_xml_panel_action.setChecked(True)
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)

    def _show_find_bar(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.show_find()

    def _show_replace_bar(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.show_replace()

    def _find_next(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.find_next()

    def _find_all(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.find_all()

    def _replace_all(self):
        self._reveal_raw_xml_tab()
        self.center_stage.find_replace_bar.replace_all()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_menus.py -v`
Expected: PASS (all, including the updated `test_edit_menu_contents` and the new `test_edit_menu_search_shortcuts`). `_raw_xml_panel_action` exists because `_build_view_menu` runs before `_build_edit_menu` inside `_build_menu_bar`.

- [ ] **Step 5: Add a menu-triggers-bar behavior test**

Append to `tests/ui/test_menus.py`:

```python
def test_find_menu_action_shows_bar_and_raw_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    find_action(edit_menu, "Find...").trigger()
    assert window.center_stage.find_replace_bar.isVisible() is True
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index


def test_replace_menu_action_shows_replace_row(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    find_action(edit_menu, "Replace...").trigger()
    bar = window.center_stage.find_replace_bar
    assert bar.isVisible() is True
    assert bar._replace_row_widget.isVisible() is True
```

Run: `python -m pytest tests/ui/test_menus.py -v -k "menu_action"`
Expected: PASS (2 passed). (These require `window.show()` is NOT needed; `isVisible()` on a shown child of an unshown window returns the widget's own show state, which `show_find`/`show_replace` set via `self.show()`.)

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_menus.py
git commit -m "feat: wire real Find/Replace Edit-menu actions to the find/replace bar"
```

---

## Task 7: Find All → Audit-panel wiring in `MainWindow`

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (imports, `_FIND_RESULT_PREFIX`, wiring in `__init__`, three methods)
- Test: `tests/ui/test_main_window.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_main_window.py`:

```python
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor


def test_find_all_populates_audit_panel_with_line_items_and_summary(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("first page\nsecond line\nthird page here")
    window._populate_find_all_results("page")

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert texts == [
        "[Find] line 1: first page",
        "[Find] line 3: third page here",
        '[Find] 2 match(es) for "page"',
    ]
    # Line data stored on result items, None on the summary line.
    assert window.audit_panel.item(0).data(Qt.ItemDataRole.UserRole) == 1
    assert window.audit_panel.item(1).data(Qt.ItemDataRole.UserRole) == 3
    assert window.audit_panel.item(2).data(Qt.ItemDataRole.UserRole) is None


def test_find_all_clears_only_prior_find_entries(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.audit_panel.addItem("[Schema] seeded entry")
    window.center_stage.xml_editor.setPlainText("page here")

    window._populate_find_all_results("page")
    window._populate_find_all_results("page")  # run again

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    # The seeded [Schema] entry survives exactly once; only ONE generation of
    # [Find] entries is present (result line + summary).
    assert texts.count("[Schema] seeded entry") == 1
    assert texts == [
        "[Schema] seeded entry",
        "[Find] line 1: page here",
        '[Find] 1 match(es) for "page"',
    ]


def test_clicking_find_result_navigates_editor_to_line(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("a\nb\npage on line 3\nd")
    window._populate_find_all_results("page")

    result_item = window.audit_panel.item(0)
    assert result_item.data(Qt.ItemDataRole.UserRole) == 3
    window._on_audit_item_clicked(result_item)

    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index
    # navigate_to_line moved the cursor to that block (1-based line 3).
    assert window.center_stage.xml_editor.textCursor().blockNumber() + 1 == 3


def test_clicking_non_find_entry_is_a_noop(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("a\nb\nc")
    # Put the cursor on line 1 and record it.
    window.center_stage.xml_editor.moveCursor(QTextCursor.MoveOperation.Start)
    before = window.center_stage.xml_editor.textCursor().blockNumber()

    window.audit_panel.addItem("[Schema] not clickable to navigate")
    schema_item = window.audit_panel.item(window.audit_panel.count() - 1)
    window._on_audit_item_clicked(schema_item)  # no line data -> no-op

    after = window.center_stage.xml_editor.textCursor().blockNumber()
    assert after == before


def test_clicking_summary_line_is_a_noop(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("page\npage")
    window._populate_find_all_results("page")
    window.center_stage.xml_editor.moveCursor(QTextCursor.MoveOperation.Start)
    before = window.center_stage.xml_editor.textCursor().blockNumber()

    summary_item = window.audit_panel.item(window.audit_panel.count() - 1)
    assert summary_item.data(Qt.ItemDataRole.UserRole) is None
    window._on_audit_item_clicked(summary_item)

    after = window.center_stage.xml_editor.textCursor().blockNumber()
    assert after == before


def test_find_all_via_menu_populates_audit_panel(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("alpha page beta")
    window.center_stage.find_replace_bar._find_field.setText("page")
    find_action(find_top_menu(window, "Edit"), "Find All").trigger()

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert "[Find] line 1: alpha page beta" in texts
    assert '[Find] 1 match(es) for "page"' in texts
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "find_all or audit or find_result or non_find or summary_line"`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_populate_find_all_results'` (and `_on_audit_item_clicked`).

- [ ] **Step 3: Add the imports and the `_FIND_RESULT_PREFIX` constant**

In `pgtp_editor/ui/main_window.py`:

1. Add `QListWidgetItem` to the existing `from PySide6.QtWidgets import (...)` block (it currently imports `QDockWidget, QFileDialog, QListWidget, QMainWindow, QMessageBox, QWidget` — add `QListWidgetItem`).
2. Add the search import next to the other `pgtp_editor.ui` imports:

```python
from pgtp_editor.ui import search
```

3. Add the module-level constant near `_SCHEMA_REPORT_TEMPLATES`:

```python
_FIND_RESULT_PREFIX = "[Find] "
```

(`Qt` is already imported from `PySide6.QtCore` at the top of the file — no change needed for it.)

- [ ] **Step 4: Wire the callback and the itemClicked connection in `__init__`**

In `MainWindow.__init__`, immediately after `self.setCentralWidget(self.center_stage)` (i.e. once `self.center_stage` and `self.audit_panel` both exist), add:

```python
        self.center_stage.find_replace_bar.set_on_find_all(self._populate_find_all_results)
        self.audit_panel.itemClicked.connect(self._on_audit_item_clicked)
```

- [ ] **Step 5: Add the three methods**

Add to `MainWindow` (place them after `_report_schema_events`, keeping the search-related methods grouped):

```python
    def _populate_find_all_results(self, term: str) -> None:
        self._clear_find_results()
        text = self.center_stage.xml_editor.toPlainText()
        matches = search.find_all_matches(text, term)
        for match in matches:
            item = QListWidgetItem(f"{_FIND_RESULT_PREFIX}line {match.line}: {match.preview}")
            item.setData(Qt.ItemDataRole.UserRole, match.line)
            self.audit_panel.addItem(item)
        summary = QListWidgetItem(
            f'{_FIND_RESULT_PREFIX}{len(matches)} match(es) for "{term}"'
        )
        self.audit_panel.addItem(summary)  # no line data -> clicking is a no-op

    def _clear_find_results(self) -> None:
        """Remove only prior [Find]-prefixed entries, leaving schema-learning
        / validation entries intact. Iterates from the bottom so removals
        don't shift not-yet-visited indices."""
        for row in range(self.audit_panel.count() - 1, -1, -1):
            item = self.audit_panel.item(row)
            if item.text().startswith(_FIND_RESULT_PREFIX):
                self.audit_panel.takeItem(row)

    def _on_audit_item_clicked(self, item) -> None:
        line = item.data(Qt.ItemDataRole.UserRole)
        if line is None:
            return  # schema entry or the [Find] summary line: no-op
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
        self.center_stage.xml_editor.navigate_to_line(line)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "find_all or audit or find_result or non_find or summary_line"`
Expected: PASS (6 passed).

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_main_window.py
git commit -m "feat: report Find All results into the Audit panel with click-to-navigate"
```

---

## Task 8: Full-suite verification and Replace-All-via-menu integration check

**Files:**
- Test: `tests/ui/test_main_window.py` (one integration test tying the menu, bar fields, and document together)

- [ ] **Step 1: Write the integration test**

Append to `tests/ui/test_main_window.py`:

```python
def test_replace_all_via_menu_mutates_document(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("page page page")
    bar = window.center_stage.find_replace_bar
    bar._find_field.setText("page")
    bar._replace_field.setText("X")

    find_action(find_top_menu(window, "Edit"), "Replace All").trigger()
    assert window.center_stage.xml_editor.toPlainText() == "X X X"
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "replace_all_via_menu"`
Expected: PASS (1 passed) — the menu action reuses the bar's `replace_all`, so no new production code is needed.

- [ ] **Step 3: Run the entire suite**

Run: `python -m pytest -q`
Expected: all tests pass — the untouched Diff/Merge, model, schema-learning, project-tree, and Properties-panel tests, plus every new test added in Tasks 1–8.

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_main_window.py
git commit -m "test: end-to-end Replace All via the Edit menu"
```

---

## Requirement → task traceability (self-review)

- Search core `find_next`/`find_all_matches`/`Match`, empty-term/wrap/overlap/1-based lines/previews → **Task 1** (spec §3.2, §4.1).
- Module location `pgtp_editor/ui/search.py` → **Task 1** (spec §3.1).
- `XmlEditor.replace_current_selection` (only edit to `xml_editor.py`) → **Task 2** (spec §3.4, §1.1).
- `FindReplaceBar` show/prefill/Find Next/wrap/Esc/decoupling/`on_find_all` callback → **Task 3** (spec §3.3).
- Replace / Replace All (single undo step) → **Tasks 3–4** (spec §3.3, §4.2).
- Raw XML tab container preserving `xml_editor`/`raw_xml_tab_index`; `test_center_stage.py` update → **Task 5** (spec §3.5).
- Edit-menu five real actions with visible shortcuts sharing the bar's code path; `test_menus.py` update; `Ctrl+H` removed → **Task 6** (spec §3.6, §4.4).
- Find All → Audit panel `[Find] line N: preview` items + summary + clear-only-`[Find]` + `itemClicked` navigate/no-op → **Task 7** (spec §3.7, §4.3).
- Full-suite green + Replace-All-via-menu integration → **Task 8** (spec §4.5).
- Out-of-scope (case/word/regex toggles; cross-file/tree search; D's `Ctrl+Shift+B/A` menu entries) → intentionally **not** built (spec §2.2).

## Blocked / follow-up work (not part of this plan)

- Adding Edit-menu entries for sub-project D's structural-selection commands (`Ctrl+Shift+B` / `Ctrl+Shift+A`) — owned by sub-project D, added when D merges (spec §1.1, §2.2).
- This branch must be merged **after** sub-project D (structural selection) and the editor↔tree-sync branch; expect a conflict in the Edit-menu block of `main_window.py`/`test_menus.py` (take this sub-project's Find/Replace group, and let D add its structural entries on top) and in `xml_editor.py` (this sub-project's only addition is `replace_current_selection`) and `center_stage.py` (the container refactor) — resolve by keeping both sides' additive changes (spec §1.1).
