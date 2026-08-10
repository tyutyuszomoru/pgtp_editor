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

Find All is PUBLISHED when nobody injected a callback (BUG-060)
--------------------------------------------------------------
Find All was born as an injected callback (``on_find_all`` /
:meth:`set_on_find_all`) because the run itself belongs to
``FindValidateController`` and the Audit surface is not the bar's business. That
works for the two bars the host wires by hand -- Raw XML and Edit XSD -- and it
is why Find All was **a dead button on every other bar**: the DDL Explorer
buffer, an editable DDL object tab, a §21 PHP tab and an FQ-006 draft fragment
each build their own bar inside their own panel, and no wiring line reaches
them. Nor could one be added per tab type and stay true: those tabs are created
at runtime, in three different files, and the next tab type would have to
remember.

So an **unwired** bar publishes the request instead
(:func:`add_find_all_observer`, ``callback(bar, term, reason)``), exactly as
``ui/editor_gutter.py`` publishes bookmark changes "without knowing this panel
exists" -- and for the same reason: the producer is per-widget and dynamic, the
consumer is one long-lived lane. `FindValidateController` subscribes once in its
constructor and resolves *which* document a publishing bar searches from the
bar's :attr:`editor`.

A bar with an injected callback does **not** publish: it calls its callback and
returns. That keeps the host's two explicit wirings authoritative (the Raw XML
and Edit XSD bars pass a ``target``) and, more importantly, means a run can
never be started twice for one click.

The weakref plumbing below deliberately mirrors ``editor_gutter``'s rather than
being shared with it: that registry is typed to ``(editor, reason)`` bookmark
events, and widening it into a general-purpose event bus would couple the
gutter to the find lane to save a dozen lines.
"""
from __future__ import annotations

import weakref
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

#: The Find All button was pressed on an unwired bar; `term` is what to search.
FIND_ALL_REQUESTED = "find-all-requested"

#: The same button was pressed while a run was in flight, i.e. it was showing
#: `Stop`. Published with an empty `term`.
FIND_ALL_STOP_REQUESTED = "find-all-stop-requested"

#: Registered Find-All observers. Bound methods are held as `WeakMethod`, so a
#: subscriber's owner (a controller, and through it a window) is never kept
#: alive by this list -- see the module docstring.
_find_all_observers: list = []


def add_find_all_observer(
    callback: Callable[[object, str, str], None],
) -> None:
    """Subscribe `callback` to every **unwired** bar's Find All button; it is
    called as ``callback(bar, term, reason)`` with `reason` one of
    :data:`FIND_ALL_REQUESTED` / :data:`FIND_ALL_STOP_REQUESTED`.

    Idempotent per callback, like `editor_gutter.add_bookmark_observer`: a host
    that re-runs its wiring does not double-start a run."""
    entry = weakref.WeakMethod(callback) if hasattr(callback, "__self__") else callback
    for existing in _find_all_observers:
        if _resolve_observer(existing) == callback:
            return
    _find_all_observers.append(entry)


def remove_find_all_observer(
    callback: Callable[[object, str, str], None],
) -> None:
    """Unsubscribe `callback`; a no-op if it is not registered."""
    for existing in list(_find_all_observers):
        if _resolve_observer(existing) in (callback, None):
            _find_all_observers.remove(existing)


def _resolve_observer(entry):
    """The live callable behind a registry entry, or None once it has died."""
    return entry() if isinstance(entry, weakref.WeakMethod) else entry


def _notify_find_all_observers(bar, term: str, reason: str) -> None:
    """Publish `(bar, term, reason)` to every live observer.

    A dead observer (its owner garbage-collected, or its C++ object destroyed --
    typically a window from an earlier test that was never closed) is dropped
    rather than raised through: this runs inside a button click. Any other
    exception propagates, because that is a real bug in the subscriber and
    swallowing it would make Find All silently do nothing again."""
    for entry in list(_find_all_observers):
        callback = _resolve_observer(entry)
        if callback is None:
            if entry in _find_all_observers:
                _find_all_observers.remove(entry)
            continue
        try:
            callback(bar, term, reason)
        except RuntimeError:
            if entry in _find_all_observers:
                _find_all_observers.remove(entry)


class FindReplaceBar(QWidget):
    def __init__(self, editor, on_find_all: Callable[[str], None] | None = None, parent=None):
        super().__init__(parent)
        self._editor = editor
        #: None means UNWIRED -- the Find All button publishes instead of
        #: calling a callback (BUG-060, see the module docstring). It is
        #: deliberately not a no-op lambda any more: "no callback" and "a
        #: callback that does nothing" have to be distinguishable for the
        #: publish decision, and the no-op default is precisely what made Find
        #: All a dead button on four tab kinds.
        self._on_find_all = on_find_all
        self._on_stop_find_all: Callable[[], None] | None = None
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

    @property
    def editor(self):
        """The editor this bar searches — read-only, and the SAME object that
        was injected.

        Published because a Find-All observer is handed the *bar* and has to
        resolve which document it belongs to (BUG-060). It is resolved by
        editor IDENTITY there, exactly as
        `FindValidateController._bookmark_audit_route` already does, so the
        answer cannot disagree with the bookmark lane's."""
        return self._editor

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
        """The Find All / Stop button. Runs an injected callback if this bar has
        one, and otherwise PUBLISHES the request (BUG-060, see the module
        docstring) -- never both, so one click is never one run twice."""
        if self._find_all_running:
            if self._on_stop_find_all is not None:
                self._on_stop_find_all()
            else:
                _notify_find_all_observers(self, "", FIND_ALL_STOP_REQUESTED)
            return
        term = self._find_field.text()
        if not term:
            return
        if self._on_find_all is not None:
            self._on_find_all(term)
            return
        _notify_find_all_observers(self, term, FIND_ALL_REQUESTED)

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
