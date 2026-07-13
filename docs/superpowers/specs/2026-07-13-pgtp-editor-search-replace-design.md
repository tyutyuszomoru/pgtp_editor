# PGTP Editor — Search & Replace (XML Editor Sub-project C) Design Specification

**Date:** 2026-07-13
**Status:** Approved for planning
**Depends on:** the merged XML Editor Foundation work now on `main` (`pgtp_editor/ui/xml_editor.py`'s real `XmlEditor(QPlainTextEdit)`, with `navigate_to_line(line)`, `line_text(line)`, `select_range_on_line(line, start, end)`, `set_line_wrap_enabled(enabled)`, and a `keyPressEvent` override), the `CenterStage` tab host (`pgtp_editor/ui/center_stage.py`), the `MainWindow` menu bar and Audit panel (`pgtp_editor/ui/main_window.py`), and the stub-action convention (`pgtp_editor/ui/_stub_action.py`).

## 1. Context and scope

This is sub-project **C** of the XML Editor feature area. Its siblings, all branching off the same `main`:

- **Sub-project D — structural selection** (not yet merged): adds `Ctrl+Shift+B` / `Ctrl+Shift+A` structural-selection commands, editing `pgtp_editor/ui/xml_editor.py` (and adding Edit-menu entries for those commands).
- **Editor↔Tree sync** (not yet merged): keeps the Project Tree and the Raw XML editor selection in sync, also editing `pgtp_editor/ui/xml_editor.py`.
- **Sub-project C — Search & Replace** (this document): Find, Replace, Find All over the Raw XML editor's text.

This document covers only sub-project C.

The current `MainWindow._build_edit_menu` already contains two **stub** actions this sub-project makes real: `"Find..."` (no shortcut) and `"Find & Replace..."` (with `Ctrl+H`). The Audit panel (`MainWindow.audit_panel`, a `QListWidget`) is currently populated only with plain-text schema-learning entries (all prefixed `"[Schema] "`, see `_report_schema_events`/`_enrich_schema_from_file`). This sub-project adds clickable `"[Find] ..."` entries to that same panel and wires `audit_panel.itemClicked`.

### 1.1 Merge / sequencing note (important)

This sub-project branches off `main` and edits four files that sub-project D (structural selection) and the editor↔tree-sync branch also touch:

- `pgtp_editor/ui/xml_editor.py`
- `pgtp_editor/ui/center_stage.py`
- `pgtp_editor/ui/main_window.py`
- `tests/ui/test_menus.py`

Because those two other branches are not yet merged, this sub-project **must be merged carefully after them**, and its edits to shared files must be kept **minimal and localized**:

- **`xml_editor.py`:** this sub-project adds at most one small, self-contained method — `replace_current_selection(text)` (§3.4) — and nothing else. The bulk of the search/replace logic lives in **new** files (`pgtp_editor/ui/search.py`, `pgtp_editor/ui/find_replace_bar.py`), specifically so this sub-project does not bloat `xml_editor.py` and does not collide with D's and the sync branch's larger edits to it. `navigate_to_line`, `line_text`, `select_range_on_line`, `toPlainText`, `textCursor`, and `setTextCursor` are consumed **as they exist today** — this sub-project does not modify them.
- **`center_stage.py`:** the Raw XML tab becomes a small container widget (editor + bar), but `center_stage.xml_editor` remains the `XmlEditor` accessor exactly as today (§3.5), so the surface other branches depend on is unchanged.
- **`main_window.py`:** edits are confined to `_build_edit_menu` (rewiring two stubs, adding three actions) plus a new Audit-panel wiring block and the handler methods that back the Edit-menu actions.
- **`test_menus.py`:** the Edit-menu assertions change (§4.4); the conflict there is expected and is resolved by taking this sub-project's version of the Edit-menu block (D will add its own structural-selection Edit entries on top — see §2.2).

The **deliberate follow-up** (NOT built here): adding Edit-menu entries for sub-project D's structural-selection commands (`Ctrl+Shift+B` / `Ctrl+Shift+A`). Those belong to D and are added once D merges; this document mentions them only to make the merge ordering explicit.

## 2. Scope

### 2.1 In scope

- New Qt-free search core module `pgtp_editor/ui/search.py` (§3.2): `find_next(text, term, from_pos, *, wrap=True)` and `find_all_matches(text, term)` returning `list[Match]`, with a `Match` dataclass. Plain **case-insensitive substring** matching only.
- New widget `pgtp_editor/ui/find_replace_bar.py` (§3.3): a modeless `FindReplaceBar(QWidget)` shown *below* the `XmlEditor` inside the Raw XML tab, with Find and Replace modes, operating on the injected editor via a small, well-defined interface.
- One small new method on `XmlEditor` (§3.4): `replace_current_selection(text)`.
- Raw XML tab container refactor (§3.5): the Raw XML tab hosts a container widget holding the editor plus the `FindReplaceBar`, while preserving `center_stage.xml_editor` as the editor accessor and `center_stage.raw_xml_tab_index`.
- Edit-menu rewiring (§3.6, §4.4): the two Find stubs become real, three new items are added, each `QAction` carries a visible shortcut and triggers the same handler as its bar-button counterpart.
- Find All → Audit-panel wiring (§3.7): `find_all_matches` results appended as clickable `"[Find] line {n}: {preview}"` items plus a summary line; clicking a `[Find]` item navigates the editor; a fresh Find All clears only prior `[Find]` entries.
- Tests (§4): Qt-free unit tests for the search core; `pytest-qt` tests for the bar, the Find All / Audit wiring, and the Edit menu.

### 2.2 Explicitly out of scope

- **Case / whole-word / regex toggles.** Matching is always plain case-insensitive substring. No options UI, no match-case checkbox, no regex.
- **Searching the tree/model or across files.** Search operates only on the Raw XML editor's own text (`editor.toPlainText()`), for the currently-open document.
- **Edit-menu entries for the structural-selection commands (`Ctrl+Shift+B` / `Ctrl+Shift+A`).** Deliberately deferred to sub-project D (§1.1). This document neither adds them nor reserves menu space for them beyond noting they will be inserted later.
- **Any change to `XmlEditor`'s existing navigation/highlight/fold/auto-close behavior.** This sub-project only *calls* the existing public methods and adds the single new `replace_current_selection` method.
- **Incremental / find-as-you-type highlighting of all matches in the editor viewport.** Find Next selects one match at a time; Find All reports into the Audit panel. There is no live all-matches highlight overlay in the editor.

## 3. Architecture

### 3.1 Module placement decision

The search core (`find_next`, `find_all_matches`, `Match`) is **pure string logic with no Qt dependency**. It is placed at **`pgtp_editor/ui/search.py`** rather than under `pgtp_editor/model/`.

**Justification:** although it is Qt-free (and is unit-tested without a `QApplication`, §4.1), it exists *solely* to serve the `FindReplaceBar` UI widget — it operates on the editor's already-extracted plain text, has no relationship to the `.pgtp` domain model (`PageNode`/`DetailNode`/etc.), and would be misleading under `model/`, which is reserved for the parsed-project domain model. Co-locating it with its only consumer (`find_replace_bar.py`, both under `pgtp_editor/ui/`) follows the plan-writing guidance that *files that change together should live together, split by responsibility not technical layer*. Being Qt-free is a **testability** property, not a reason to relocate it into the model layer.

### 3.2 The Qt-free search core (`pgtp_editor/ui/search.py`)

```python
# pgtp_editor/ui/search.py
"""Pure, Qt-free case-insensitive substring search over plain text.

Serves the FindReplaceBar UI widget (pgtp_editor/ui/find_replace_bar.py) but
has no Qt dependency itself, so it is unit-testable without a QApplication.
Matching is always plain case-insensitive substring: no case/word/regex
options exist anywhere in this sub-project (see design spec sec 2.2).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    """One case-insensitive substring match found by find_all_matches.

    start:   0-based character index of the match within the full text.
    line:    1-based line number the match starts on (matching the
             XmlEditor.navigate_to_line / line_text 1-based convention).
    preview: the whitespace-trimmed text of that whole line, for display
             in the Audit panel entry.
    """
    start: int
    line: int
    preview: str


def find_next(text: str, term: str, from_pos: int, *, wrap: bool = True) -> int | None:
    """Return the 0-based index of the next case-insensitive occurrence of
    `term` at or after `from_pos`. If none is found at/after `from_pos` and
    `wrap` is True, wrap around and search from the start of `text`. Returns
    None if `term` is empty or does not occur in `text` at all.
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
    """Return every non-overlapping case-insensitive match of `term` in
    `text`, scanned left-to-right, advancing by len(term) after each hit
    (so adjacent matches are all found but overlapping ones are not — see
    the overlap policy in design spec sec 3.2). Empty `term` -> []."""
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
        preview = _line_preview(text, found)
        matches.append(Match(start=found, line=line, preview=preview))
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

**Overlap / adjacency policy (documented):** `find_all_matches` performs a **non-overlapping left-to-right scan advancing by `len(term)`** after each hit. Consequence, stated explicitly:

- **Adjacent** matches are all found — e.g. `find_all_matches("aa", "a")` yields two matches at indices 0 and 1; `find_all_matches("abab", "ab")` yields two matches at 0 and 2.
- **Overlapping** matches are not all found — e.g. `find_all_matches("aaa", "aa")` yields a single match at index 0 (the scan resumes at index 2 after consuming `len("aa") == 2`), not two matches at 0 and 1. This is the intended, documented behavior, matching what a user reading a linear list of results expects (no doubled-up highlights of the same characters).

`find_next` uses `str.find` and therefore locates the **next** occurrence at or after `from_pos` regardless of overlap with any prior selection — it does not itself apply the non-overlapping-advance rule (that rule is specific to enumerating a complete list in `find_all_matches`). The `FindReplaceBar` advances `from_pos` past the current selection between calls (§3.3), so repeated Find Next never re-finds the same span in place.

**1-based line numbers:** `line = text.count("\n", 0, found) + 1` — the number of newlines before the match index, plus one. This matches `XmlEditor.navigate_to_line`/`line_text`'s 1-based convention exactly (verified against `xml_editor.py`: `navigate_to_line(line)` does `findBlockByNumber(line - 1)`).

### 3.3 `FindReplaceBar` (`pgtp_editor/ui/find_replace_bar.py`)

A modeless `QWidget` displayed **below** the `XmlEditor` inside the Raw XML tab (§3.5). It never blocks — the user can keep editing while it is visible.

**Editor interface it depends on (small and explicit).** The bar is constructed with an `editor` object and uses only these members, all of which the real `XmlEditor` already provides (except `replace_current_selection`, added in §3.4):

- `editor.toPlainText() -> str`
- `editor.textCursor() -> QTextCursor`
- `editor.setTextCursor(cursor: QTextCursor)`
- `editor.setFocus()`
- `editor.document()` (only to construct a `QTextCursor(editor.document())` for Replace All's single edit block)
- `editor.replace_current_selection(text: str)` (§3.4)

The bar is **decoupled from `MainWindow`** — it holds no reference to the window; Find All is delegated to an injected callback (§3.7) rather than the bar reaching into `MainWindow.audit_panel` directly.

```python
# pgtp_editor/ui/find_replace_bar.py
"""FindReplaceBar: a modeless find/replace bar shown below the XmlEditor
inside the Raw XML tab. Operates on an injected editor via a small, explicit
interface (toPlainText / textCursor / setTextCursor / setFocus / document /
replace_current_selection) so it stays decoupled from MainWindow. Find All is
delegated to an injected callback (see design spec sec 3.7)."""
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
        # Search from the end of the current selection so repeated Find Next
        # advances instead of re-finding the current span in place.
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
        if selected.lower() == term.lower() and selected:
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
        # Replace right-to-left so earlier indices stay valid as later
        # spans are rewritten (replacement may differ in length from term).
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

**Behavior details, mapped to the requirements:**

- **Find / Find Next (`find_next`):** reads the term from the find field, extracts the editor text, computes `from_pos` as the end of the current selection (`max(selectionEnd(), position())`, so a Find Next after a prior match advances past it), calls `search.find_next(..., wrap=True)`, and on a hit selects the span via a `QTextCursor` anchor+position and calls `ensureCursorVisible()`. On no hit (term absent entirely, since wrap is on), it is a no-op. `returnPressed` in the find field is wired to `find_next` so Enter triggers it.
- **Find All (`find_all`):** delegates to the injected `on_find_all(term)` callback (§3.7) — the bar does not touch the Audit panel itself.
- **Replace (`replace`):** if the editor's current selection equals a match of the term (compared **case-insensitively**, and only when the selection is non-empty), it calls `editor.replace_current_selection(replacement)`, then calls `find_next` to advance. Otherwise it just calls `find_next`. (This means the first Replace click after opening the bar, with no matching selection, simply finds the next match; a second click then replaces it — the standard find-then-replace rhythm.)
- **Replace All (`replace_all`):** enumerates every match via `search.find_all_matches`, then rewrites them in a **single `QTextCursor` edit block** (`beginEditBlock()`/`endEditBlock()`) so the whole operation is **one undo step**. Spans are rewritten **right-to-left** so that replacing a span never invalidates the indices of not-yet-processed earlier spans (the replacement text may differ in length from the term). A single `Ctrl+Z` reverts the entire Replace All (asserted in §4.2).
- **Esc:** the `keyPressEvent` override hides the bar and returns focus to the editor.
- **Selection pre-fill on show:** both `show_find` and `show_replace` call `_prefill_from_selection`, which copies `editor.textCursor().selectedText()` into the find field when it is non-empty. (Note: `QTextCursor.selectedText()` uses U+2029 as its line separator for multi-line selections; a search term is realistically single-line, so this is not special-cased.)

### 3.4 The one new `XmlEditor` method: `replace_current_selection`

To keep the bar decoupled from `QTextCursor` mechanics and to keep the edit atomic, `XmlEditor` gains one small, self-contained method. This is the **only** edit this sub-project makes to `xml_editor.py` (§1.1).

```python
# pgtp_editor/ui/xml_editor.py  (new method on XmlEditor)
    def replace_current_selection(self, text: str) -> None:
        """Replace the current selection's text with `text` as a single undo
        step. No-op if there is no selection. Used by FindReplaceBar's
        Replace (see design spec sub-project C, sec 3.3/3.4)."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        cursor.insertText(text)  # QTextCursor.insertText replaces the selection
        self.setTextCursor(cursor)
```

`QTextCursor.insertText` on a cursor with a selection replaces that selection in one operation (already a single undo step). Placing this on `XmlEditor` (rather than in the bar) keeps the bar's editor interface small and lets the editor own its own document mutation.

### 3.5 Raw XML tab container refactor (`center_stage.py`)

Today the Raw XML tab's widget **is** the `XmlEditor`:

```python
self.xml_editor = XmlEditor()
self.raw_xml_tab_index = self.addTab(self.xml_editor, "Raw XML")
```

The `FindReplaceBar` must sit *below* the editor within that tab, so the tab's widget becomes a small container (editor on top, bar underneath). Crucially, **`center_stage.xml_editor` must remain the `XmlEditor` accessor** (§1.1) and **`center_stage.raw_xml_tab_index` must remain valid**, because existing code and tests depend on both (`main_window.py` uses `self.center_stage.xml_editor` in ~5 places; `tests/ui/test_center_stage.py` and `tests/ui/test_menus.py` assert on both).

```python
# pgtp_editor/ui/center_stage.py
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

**Test-impact note (called out, resolved in the plan).** `tests/ui/test_center_stage.py::test_raw_xml_tab_holds_a_real_xml_editor` currently asserts **both**:

```python
assert isinstance(stage.xml_editor, XmlEditor)
assert stage.widget(stage.raw_xml_tab_index) is stage.xml_editor
```

The first assertion still holds. The **second no longer holds** once the tab widget is the container, not the editor itself. This test is updated (in the plan) to assert the container relationship instead — that `stage.widget(stage.raw_xml_tab_index)` is the container and that the container *contains* `stage.xml_editor`:

```python
def test_raw_xml_tab_holds_a_real_xml_editor(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.xml_editor, XmlEditor)
    # The tab now hosts a container (editor + find/replace bar); xml_editor
    # remains the accessor and lives inside that container.
    assert stage.widget(stage.raw_xml_tab_index) is stage.raw_xml_tab
    assert stage.xml_editor.parent() is stage.raw_xml_tab
```

The other three `test_center_stage.py` tests (`test_three_tabs_in_order`, `test_raw_xml_tab_hidden_by_default`, `test_set_raw_xml_tab_visible`) reference `raw_xml_tab_index`/`tabText`/`isTabVisible` only and continue to pass unchanged. `test_menus.py`'s `test_toggling_wrap_raw_xml_lines_changes_editor_line_wrap_mode` reads `window.center_stage.xml_editor.lineWrapMode()` — still valid, since `xml_editor` is preserved.

### 3.6 Edit-menu rewiring (`main_window.py`)

`_build_edit_menu` is rewritten so the Find/Replace items are **real `QAction`s** with visible shortcuts. Each menu action triggers the **same handler** as the corresponding bar button, so behavior is defined in exactly one place per operation.

The five handlers live on `MainWindow` and each (a) makes the Raw XML tab current + visible, and (b) delegates to the bar / core:

```python
# pgtp_editor/ui/main_window.py

    # -- Search & Replace: menu handlers (mirror the FindReplaceBar buttons) --

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

    def _reveal_raw_xml_tab(self):
        self.center_stage.set_raw_xml_tab_visible(True)
        self._raw_xml_panel_action.setChecked(True)
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
```

`_reveal_raw_xml_tab` reuses the exact same reveal sequence already used by `_handle_parse_failure` (`set_raw_xml_tab_visible(True)` + `self._raw_xml_panel_action.setChecked(True)` + `setCurrentIndex(raw_xml_tab_index)`), so the tab is always visible and focused before the bar is shown or an operation runs. (`_build_edit_menu` runs during `_build_menu_bar`, which is the last statement of `__init__`, after `self._raw_xml_panel_action` is created in `_build_view_menu` — ordering confirmed against the current `main_window.py`.)

The rewritten `_build_edit_menu`:

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

The old `"Find & Replace..."` stub and its `Ctrl+H` shortcut are **removed**; Replace is now `"Replace..."` at `Ctrl+R`. `QAction.setShortcut(...)` makes Qt render the accelerator on the right-hand side of the menu item automatically, satisfying "every function explicit, with its shortcut shown."

### 3.7 Find All → Audit-panel wiring (`main_window.py`)

The bar's `on_find_all` callback is wired, in `MainWindow`, to a method that computes matches and populates the Audit panel. `MainWindow` injects this callback into the already-constructed `FindReplaceBar` (which `CenterStage` created without one) via a setter or by re-wiring; the cleanest approach, given `CenterStage` builds the bar, is for `MainWindow` to assign the callback onto the existing bar after `self.center_stage` is constructed:

```python
# pgtp_editor/ui/main_window.py, in __init__ after self.center_stage is built
        self.center_stage.find_replace_bar.set_on_find_all(self._populate_find_all_results)
        self.audit_panel.itemClicked.connect(self._on_audit_item_clicked)
```

`FindReplaceBar` therefore exposes a tiny setter:

```python
# pgtp_editor/ui/find_replace_bar.py
    def set_on_find_all(self, callback: Callable[[str], None]) -> None:
        self._on_find_all = callback
```

The Audit-panel population and click handling (constants + methods) on `MainWindow`:

```python
# pgtp_editor/ui/main_window.py
from PySide6.QtCore import Qt  # already imported today
from PySide6.QtWidgets import QListWidgetItem  # add to the existing QtWidgets import

from pgtp_editor.ui import search  # add

_FIND_RESULT_PREFIX = "[Find] "


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
        # The summary line carries no line data, so clicking it is a no-op.
        self.audit_panel.addItem(summary)

    def _clear_find_results(self) -> None:
        """Remove only prior [Find]-prefixed entries, leaving schema-learning
        / validation entries intact. Iterates from the bottom so row removals
        don't shift not-yet-checked indices."""
        for row in range(self.audit_panel.count() - 1, -1, -1):
            item = self.audit_panel.item(row)
            if item.text().startswith(_FIND_RESULT_PREFIX):
                self.audit_panel.takeItem(row)

    def _on_audit_item_clicked(self, item) -> None:
        line = item.data(Qt.ItemDataRole.UserRole)
        if line is None:
            return  # schema entry, or the [Find] summary line: no-op
        self.center_stage.setCurrentIndex(self.center_stage.raw_xml_tab_index)
        self.center_stage.xml_editor.navigate_to_line(line)
```

**Requirement mapping:**

- Each result item text is exactly `"[Find] line {n}: {preview}"`; the line number is stored via `setData(Qt.ItemDataRole.UserRole, line)`.
- A trailing summary item reads `'[Find] {count} match(es) for "{term}"'` and carries **no** line data (so clicking it is a no-op).
- A fresh Find All first removes **only** prior `[Find]`-prefixed entries via `_clear_find_results`, leaving `[Schema]`/validation entries in place, then adds the new ones.
- `audit_panel.itemClicked` → `_on_audit_item_clicked`: an item carrying a line makes the Raw XML tab current and calls `editor.navigate_to_line(line)`; an item with no line data (schema entry, or the summary) returns without doing anything.

Note that `_on_audit_item_clicked` deliberately does **not** call `_reveal_raw_xml_tab` (it does not force the tab *visible* via the View-menu checkbox); it only makes the tab current and navigates. If the Raw XML tab is hidden, `setCurrentIndex` on a hidden tab is harmless, and navigation still positions the cursor for when the user shows it. (Find All is normally invoked through `_find_all`, which already revealed the tab.)

## 4. Testing strategy

### 4.1 Qt-free unit tests for the search core (`tests/ui/test_search.py`)

No `QApplication` needed. Covers, at minimum:

- **Multiple hits:** `find_all_matches` over text with several occurrences returns them all, in left-to-right order, with correct 0-based `start` indices.
- **Wrap-around:** `find_next(text, term, from_pos)` where the only match is *before* `from_pos` returns that earlier index when `wrap=True`, and `None` when `wrap=False`.
- **No match:** `find_next` returns `None`; `find_all_matches` returns `[]`.
- **Case-insensitivity:** searching `"page"` matches `"Page"`/`"PAGE"`; both functions.
- **Empty term:** `find_next(..., "", ...)` returns `None`; `find_all_matches(text, "")` returns `[]`.
- **Adjacent matches:** `find_all_matches("abab", "ab")` → two matches at 0 and 2; `find_all_matches("aa", "a")` → two matches at 0 and 1.
- **Overlap policy:** `find_all_matches("aaa", "aa")` → exactly one match at index 0 (documents the non-overlapping advance).
- **1-based line numbers and previews:** a multi-line text where a match is on line 3 yields `Match.line == 3` and `Match.preview` equal to that line's `.strip()`ped text (asserting leading indentation is trimmed).

### 4.2 `pytest-qt` tests for `FindReplaceBar` (`tests/ui/test_find_replace_bar.py`)

Constructed with a **real `XmlEditor`** (it exists on `main`), so `replace_current_selection`, `toPlainText`, cursor selection, and undo are all exercised against the genuine widget:

- **Selection pre-fill on show:** set a selection in the editor, call `show_find()`, assert the find field text equals the selection.
- **Find Next selects the correct span and wraps:** load known text, put the cursor at the top, `set find field`, call `find_next()`, assert the editor's selected text equals the term and the selection starts at the expected index; call `find_next()` repeatedly to reach the last match, then once more and assert it wrapped to the first.
- **Replace replaces current match then advances:** with the current selection equal to a match, `find field`=term, `replace field`=replacement, call `replace()`; assert the document text has that one occurrence replaced and the selection has advanced to the next match.
- **Replace All is one undo step:** load text with N occurrences, `replace_all()`, assert all N replaced; then call `editor.undo()` **once** and assert the document is back to the exact original (proving the single `beginEditBlock`/`endEditBlock`).
- **Esc hides and refocuses editor:** show the bar, send a `Qt.Key.Key_Escape` key event, assert `bar.isVisible()` is False and `editor.hasFocus()` is True.
- **Empty term is a no-op:** with an empty find field, `find_next()`/`replace()`/`replace_all()` do not change the document or selection and do not raise.

### 4.3 `pytest-qt` tests for Find All + Audit wiring (`tests/ui/test_main_window.py`)

Driven through a real `MainWindow` (which builds the real `CenterStage`, `FindReplaceBar`, and `audit_panel`):

- **Correct `[Find] line N: ...` items with line data:** set the editor text, call `window._populate_find_all_results(term)` (or trigger via the bar), assert each result item's `.text()` matches `"[Find] line {n}: {preview}"` and `item.data(Qt.ItemDataRole.UserRole)` equals the 1-based line.
- **Summary line:** the last added item reads `'[Find] {count} match(es) for "{term}"'` and its `UserRole` data is `None`.
- **Re-running clears only prior `[Find]` entries:** seed a non-Find item (`audit_panel.addItem("[Schema] seeded entry")`), run Find All twice, and assert the seeded `[Schema]` item still exists exactly once while only one generation of `[Find]` items is present.
- **Clicking a result navigates:** emit/trigger `_on_audit_item_clicked(item)` for a result item and assert (a) `center_stage.currentIndex() == raw_xml_tab_index` and (b) the editor's cursor is now on the expected line (assert via `editor.textCursor().blockNumber() + 1 == line`, i.e. by the editor's resulting cursor line, since `navigate_to_line` moves the cursor to that block).
- **Clicking a non-Find entry is a no-op:** click the seeded `[Schema]` item (and, separately, the summary item) and assert the editor cursor did **not** move and no exception is raised.

### 4.4 Edit-menu tests (`tests/ui/test_menus.py`)

The existing `test_edit_menu_contents` and `test_find_and_replace_has_ctrl_h_shortcut` are **updated** (the `Ctrl+H`/`"Find & Replace..."` stub no longer exists). New/updated assertions:

- **Updated `test_edit_menu_contents`** expects the new label list and order:

  ```python
  assert action_labels(edit_menu) == [
      "Undo", "Redo", "―",
      "Cut", "Copy", "Paste", "Delete", "―",
      "Find...", "Find Next", "Find All", "Replace...", "Replace All", "―",
      "Preferences...",
  ]
  ```

- **Remove** `test_find_and_replace_has_ctrl_h_shortcut` (the action it targets is gone) and **replace** it with a shortcut check over all five items:

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

  (`QKeySequence.toString()` normalizes `"Ctrl+Alt+Return"` to `"Ctrl+Alt+Return"`; the plan verifies the exact normalized string during authoring and pins the asserted value to whatever `toString()` actually returns, e.g. `"Ctrl+Alt+Return"` vs `"Ctrl+Alt+Enter"` — see §5 decision on finalizing that string.)

- **Behavior wiring per item:** triggering each Edit-menu action invokes the same behavior as its bar counterpart. Concretely: triggering `"Find..."` shows the bar (`window.center_stage.find_replace_bar.isVisible()` becomes True and the Raw XML tab is current); triggering `"Replace..."` additionally shows the replace row; triggering `"Find All"` (after setting editor text and a find term) populates `[Find]` items in the Audit panel; triggering `"Replace All"` (after setting text + terms in the bar fields) mutates the document. These reuse the real handlers, asserting the menu and the bar share one code path.

All other `test_menus.py` assertions (File/View/Diff/Schema/Tools/Generation/Help menu contents, menu order, `_raw_xml_panel_action`, wrap toggle) are **unchanged** and must continue to pass.

### 4.5 Full-suite verification

After every task the plan runs the targeted tests; the final task runs the entire suite (`python -m pytest -q`) and requires all tests green, including the untouched Diff/Merge, model, schema-learning, and Properties-panel tests.

## 5. Summary of decisions

- **Matching is plain case-insensitive substring only** — no case/word/regex toggles anywhere (scope decision governing every design choice here).
- **Search-core module location:** `pgtp_editor/ui/search.py`, not `pgtp_editor/model/`. It is Qt-free for testability, but it serves only the Find/Replace UI and has no relationship to the parsed-project domain model, so it lives next to its sole consumer under `ui/`. (Judgment call.)
- **`Match` dataclass:** `frozen`, fields `start` (0-based char index), `line` (1-based, matching `navigate_to_line`/`line_text`), `preview` (the match's whole line, `.strip()`ped).
- **Overlap policy:** `find_all_matches` scans non-overlapping left-to-right, advancing by `len(term)` — adjacent matches are all found, overlapping ones are not. Documented and tested. `find_next` uses plain `str.find` and advances via the bar moving `from_pos` past the current selection.
- **Only one new `XmlEditor` method** (`replace_current_selection`), to keep edits to the concurrently-edited `xml_editor.py` minimal; all other search/replace logic lives in new files (`search.py`, `find_replace_bar.py`). (Merge-risk mitigation, §1.1.)
- **Raw XML tab container refactor:** the tab widget becomes a small `QWidget` container (editor + bar); `center_stage.xml_editor` and `center_stage.raw_xml_tab_index` are preserved so dependent code/tests keep working. The one `test_center_stage.py` assertion that checked `widget(raw_xml_tab_index) is xml_editor` is updated to assert the container relationship. (Judgment call on refactor approach.)
- **Edit-menu ordering:** the two Find stubs are replaced in place and the three new items are inserted adjacent, forming one contiguous group between the Cut/Copy/Paste/Delete separator and the Preferences separator: `Find... (Ctrl+F)`, `Find Next (F3)`, `Find All (Ctrl+Shift+F)`, `Replace... (Ctrl+R)`, `Replace All (Ctrl+Alt+Return)`. `Ctrl+H` is removed. (Judgment call on placement.)
- **`Ctrl+Alt+Return` shortcut:** set via `QAction.setShortcut("Ctrl+Alt+Return")`; the exact string asserted in tests is whatever `QKeySequence("Ctrl+Alt+Return").toString()` normalizes to (the plan pins this during authoring). Chosen (over, e.g., `Ctrl+Alt+Enter`) because `Return` is the canonical Qt key name and normalizes predictably. (Finalized shortcut.)
- **Bar decoupled from `MainWindow`:** the bar operates on the injected `XmlEditor` via a small explicit interface and delegates Find All to an injected `on_find_all(term)` callback (set by `MainWindow`), so it never references the window or the Audit panel directly.
- **Find All → Audit panel:** clickable `"[Find] line {n}: {preview}"` items with the line stored on `UserRole`, a trailing `'[Find] {count} match(es) for "{term}"'` summary with no line data, a fresh run clearing only prior `[Find]` entries, and `audit_panel.itemClicked` navigating on line-bearing items / no-op otherwise.
- **Menu handlers and bar buttons share one code path** — each Edit-menu action calls the same `FindReplaceBar` method its button does (after revealing the Raw XML tab), so there is exactly one implementation per operation.
- **Merge sequencing:** branch off `main`; merge **after** sub-project D (structural selection) and the editor↔tree-sync branch; keep edits to the four shared files (`xml_editor.py`, `center_stage.py`, `main_window.py`, `test_menus.py`) minimal. Edit-menu entries for D's `Ctrl+Shift+B`/`Ctrl+Shift+A` are a deliberate follow-up owned by D, not built here.
