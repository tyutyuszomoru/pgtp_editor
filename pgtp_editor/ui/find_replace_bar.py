# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# pgtp_editor/ui/find_replace_bar.py
"""FindReplaceBar: a modeless find/replace bar shown below the XmlEditor
inside the Raw XML tab. Operates on an injected editor via a small, explicit
interface (toPlainText / textCursor / setTextCursor / setFocus / document /
replace_current_selection) so it stays decoupled from MainWindow. Find All is
delegated to an injected callback.

**The bar is PERMANENTLY VISIBLE, in its expanded form** (FQ-016, §8/§15/§27).
It no longer hides itself on construction, there is no `show_find`/`show_replace`
split (the replace row is always shown), and `Escape` returns focus to the
editor instead of hiding anything. `Ctrl+F`/`Ctrl+R` are **focus** gestures:
:meth:`focus_find` / :meth:`focus_replace`, hosted by
:func:`install_focus_shortcuts` on the widget that owns the editor *and* the bar
-- see that function for why they are not window-level.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut, QTextCursor
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
        self._on_stop_find_all: Callable[[], None] = lambda: None
        self._on_status: Callable[[str], None] = lambda msg: None
        self._find_all_running = False

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

        # NO `self.hide()` here (FQ-016): the bar is visible from construction,
        # in its expanded form (both rows), in every editor. Deleted, not left
        # inert -- there is no hideable state left to restore.

    def set_on_find_all(self, callback: Callable[[str], None]) -> None:
        self._on_find_all = callback

    def set_on_stop_find_all(self, callback: Callable[[], None]) -> None:
        self._on_stop_find_all = callback

    def set_on_status(self, callback: Callable[[str], None]) -> None:
        self._on_status = callback

    def set_find_all_running(self, running: bool) -> None:
        """Driven by the Find All controller: flips the button between
        'Find All' (idle) and 'Stop' (a streaming run is active)."""
        self._find_all_running = running
        self._find_all_button.setText("Stop" if running else "Find All")

    # -- focus (the bar is never hidden) ------------------------------------

    def focus_find(self) -> None:
        """``Ctrl+F``: put the cursor in the Find field.

        This is all `Ctrl+F` does since FQ-016 — the bar is already visible, so
        there is nothing to show. The old `show_find` additionally hid the
        replace row; that mode is gone.
        """
        self._prefill_from_selection()
        self._find_field.setFocus()
        self._find_field.selectAll()

    def focus_replace(self) -> None:
        """``Ctrl+R``: put the cursor in the Replace-with field.

        Prefills Find from the editor selection on the same terms as
        :meth:`focus_find`, so "select a word, press Ctrl+R" still arms the
        search — but the caret lands where the user is about to type.
        """
        self._prefill_from_selection()
        self._replace_field.setFocus()
        self._replace_field.selectAll()

    def set_find_text(self, text: str) -> None:
        """Set the Find field's text (used by the editor's right-click
        "Find" path, which prefills from the selection and then runs
        find_next). Distinct from _prefill_from_selection, which fills only
        from a live editor selection and only into an EMPTY field."""
        self._find_field.setText(text)

    def _prefill_from_selection(self) -> None:
        """Seed Find from the editor's selection — **only when the field is
        empty** (FQ-016, following FQ-017's precedent on the caption bar).

        It used to run on every `show_find`/`show_replace`, where clobbering was
        harmless because the bar had just appeared. On the *focus* path it would
        overwrite a term the user typed a moment ago every time they pressed
        Ctrl+F with an incidental selection still live in the editor — hostile
        for a gesture whose whole job is "put my cursor there". `set_find_text`
        stays unconditional; it is an explicit "search for this" command.
        """
        if self._find_field.text():
            return
        selected = self._editor.textCursor().selectedText()
        if selected:
            self._find_field.setText(selected)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            # FQ-016: Escape returns focus to the document. It does NOT hide the
            # bar — there is no hidden state any more.
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
        if self._find_all_running:
            self._on_stop_find_all()
            return
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
        if matches:
            cursor = QTextCursor(self._editor.document())
            cursor.beginEditBlock()
            for match in reversed(matches):
                cursor.setPosition(match.start)
                cursor.setPosition(match.start + len(term), QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(replacement)
            cursor.endEditBlock()
        self._on_status(f'{len(matches)} replacement(s) for "{term}"')

    def _select_span(self, index: int, length: int) -> None:
        cursor = self._editor.textCursor()
        cursor.setPosition(index)
        cursor.setPosition(index + length, QTextCursor.MoveMode.KeepAnchor)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()


def install_focus_shortcuts(host: QWidget, bar: FindReplaceBar) -> tuple:
    """Give `host` the two `Ctrl+F` / `Ctrl+R` **focus** shortcuts for `bar`.

    `host` must be the widget that owns BOTH the editor and the bar (the tab
    container / panel), because the context is
    ``WidgetWithChildrenShortcut``: the keys have to fire while the caret is in
    the **editor**, not only once the bar already has focus.

    **Why per-host and not one window-level shortcut** — the thing a reader will
    otherwise "simplify" away. FQ-017 gave the Caption Management panel its own
    panel-scoped ``Ctrl+F``/``Ctrl+R`` (`caption_management_panel.py`), and Qt
    does **not** prefer a narrower context over a wider one: two enabled
    shortcuts matching the same key press are *ambiguous*, and neither fires
    (only `activatedAmbiguously` does). A window-level `Ctrl+F` would therefore
    break caption find/replace — the very conflict the old
    `set_find_actions_enabled` gate existed to avoid, and which FQ-016 was able
    to delete precisely because the keys became per-surface. Each editor tab
    owning its own pair keeps exactly one match live for any focus location, and
    makes `Ctrl+F` a **no-op on tabs with no bar** (Manual, Diff/Merge) rather
    than yanking the user to Raw XML (§29).

    `F3` is deliberately NOT here: it is a single window-level action routed
    through `FindValidateController.active_find_bar()` (§27), because nothing
    competes for it.

    Returns the two `QShortcut`s so the caller can retain them (a `QShortcut`
    parented to `host` is owned by it, but returning them keeps them
    inspectable from tests).
    """
    find_shortcut = QShortcut(QKeySequence("Ctrl+F"), host)
    find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    find_shortcut.activated.connect(bar.focus_find)
    replace_shortcut = QShortcut(QKeySequence("Ctrl+R"), host)
    replace_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    replace_shortcut.activated.connect(bar.focus_replace)
    return find_shortcut, replace_shortcut
