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

# pgtp_editor/ui/completion_popup.py
"""`_CompletionPopup`: the one reusable Ctrl+Space completion widget (§11,
generalized onto the DDL object editor by §18.6).

Originally `ui/xml_editor.py`'s private popup for attribute/value completion.
Extracted here, unchanged, so a second `CodeEditor`-hosting consumer
(`ui/ddl_object_editor.py::DdlObjectEditorPanel`, §18.5/§18.6) can reuse the
exact same class -- frameless (`Qt.WindowType.Popup`), non-modal, a
``(key, display)`` master list with a running prefix filter, arrow-key
navigation, Enter/Tab/click to choose, Esc/focus-out to cancel -- instead of a
second bespoke popup implementation. `xml_editor.py` re-exports this name for
backward compatibility (existing imports/tests spell it
``pgtp_editor.ui.xml_editor._CompletionPopup``).

Alongside the widget lives ``CompletionPopupHostMixin`` — the three-method
wiring (``_ensure_completion_popup`` / ``_popup_at_caret`` / ``_rewire_popup``)
that every consumer of the popup used to carry as its own byte-similar copy.
It follows the ``GutterBookmarkFoldMixin`` idiom of ``ui/editor_gutter.py``:
no ``__init__`` of its own, activated from the host's ``__init__`` by calling
``_init_completion_popup()``, with exactly one pluggable hook.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem


class _CompletionPopup(QListWidget):
    """Frameless completion list. Holds a master list of ``(key, display)``
    items and a running filter; arrows navigate, printable chars filter by key
    prefix (case-insensitive), Enter/Tab or a mouse click choose, Esc cancels.
    Emits the chosen *key* (not the display string). Callers pass items
    pre-ordered; filtering preserves that order."""

    chosen = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setUniformItemSizes(True)
        self._items: list[tuple[str, str]] = []
        self._filter = ""
        self.itemClicked.connect(
            lambda item: self.chosen.emit(item.data(Qt.ItemDataRole.UserRole))
        )

    def set_items(self, items) -> None:
        """Replace the master ``(key, display)`` list, reset the filter, and
        select the first row."""
        self._items = list(items)
        self._filter = ""
        self._rebuild()

    def append_filter(self, text: str) -> None:
        self._filter += text
        self._rebuild()

    def backspace_filter(self) -> None:
        self._filter = self._filter[:-1]
        self._rebuild()

    def visible_keys(self) -> list[str]:
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())
        ]

    def current_key(self):
        item = self.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _rebuild(self) -> None:
        prefix = self._filter.lower()
        self.clear()
        for key, display in self._items:
            if key.lower().startswith(prefix):
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.addItem(item)
        if self.count():
            self.setCurrentRow(0)

    def _choose_current(self) -> None:
        key = self.current_key()
        if key is not None:
            self.chosen.emit(key)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            self._choose_current()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Backspace:
            self.backspace_filter()
            event.accept()
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            super().keyPressEvent(event)
            return
        # Ctrl/Meta chords (Ctrl+C, Ctrl+A, ...) still carry a text() payload
        # on some platforms; never swallow them into the filter. Shift stays
        # allowed (uppercase typing filters) and Alt passes through below via
        # the empty/non-printable text check or the fallthrough.
        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            super().keyPressEvent(event)
            return
        text = event.text()
        if text and text.isprintable() and not text.isspace():
            self.append_filter(text)
            event.accept()
            return
        super().keyPressEvent(event)


class CompletionPopupHostMixin:
    """The shared Ctrl+Space popup *wiring* for any widget that hosts a
    `_CompletionPopup` (§11 for `XmlEditor`, §18.6 for the DDL object editor
    and the SQL console).

    Extracted verbatim out of the three hosts (`ui/xml_editor.py`,
    `ui/ddl_object_editor.py`, `ui/sql_console_panel.py`), which each carried
    an identical copy of these three methods. The popup class was already
    shared; only its plumbing was duplicated.

    Requirements on the host:

    - it is a ``QWidget`` (the popup is parented to it, and it is what gets
      focus back once the popup closes);
    - it exposes the text editor the caret lives in via
      ``_completion_editor()`` -- the ONE pluggable piece, see below;
    - it calls ``_init_completion_popup()`` from its ``__init__``.

    Like ``GutterBookmarkFoldMixin`` it deliberately has no ``__init__`` of its
    own, so the host's ``super().__init__(parent)`` still reaches its Qt base
    class unchanged. Mix it in *before* the Qt base class.

    The **only pluggable piece** is ``_completion_editor()``. It exists because
    the hosts differ in whether they *are* the text editor or merely *contain*
    one: ``XmlEditor`` is itself a ``QPlainTextEdit`` (and returns ``self``),
    while ``DdlObjectEditorPanel`` and ``SqlConsolePanel`` are ``QWidget``
    panels wrapping a ``CodeEditor`` in ``self.editor``. Caret geometry must be
    read off that editor, not off the panel -- so the difference is expressed
    as this hook rather than as three copies of ``_popup_at_caret``.
    """

    # --- Setup -------------------------------------------------------------
    def _init_completion_popup(self) -> None:
        """Declare the popup state. Call from the host's ``__init__``."""
        # The shared Ctrl+Space completion popup, created lazily on first use
        # (see _ensure_completion_popup) and then reused for every subsequent
        # completion stage of this host.
        self._completion_popup: _CompletionPopup | None = None
        # True once _rewire_popup has connected the popup's signals at least
        # once; guards the disconnect calls in _rewire_popup so a fresh popup
        # doesn't log a PySide6 RuntimeWarning for disconnecting nothing.
        self._popup_wired = False

    # --- Caret-owning editor (the ONE pluggable piece) ---------------------
    def _completion_editor(self):
        """The text edit whose caret the popup is positioned against. The
        default assumes the host IS that editor; panel hosts override it to
        return their wrapped editor."""
        return self

    # --- Wiring ------------------------------------------------------------
    def _ensure_completion_popup(self) -> _CompletionPopup:
        if self._completion_popup is None:
            self._completion_popup = _CompletionPopup(self)
        return self._completion_popup

    def _popup_at_caret(self, popup: _CompletionPopup) -> None:
        """Show ``popup`` just below the caret and give it focus."""
        editor = self._completion_editor()
        rect = editor.cursorRect()
        point = editor.viewport().mapToGlobal(rect.bottomLeft())
        popup.move(point)
        popup.show()
        popup.setFocus()

    def _rewire_popup(self, popup: _CompletionPopup, on_chosen) -> None:
        """Point the shared popup's signals at the current completion stage.
        Only disconnects previous connections when the popup was actually
        wired before, so a fresh popup's first use does not trigger a
        PySide6 RuntimeWarning for disconnecting an unconnected signal."""
        if self._popup_wired:
            popup.chosen.disconnect()
            popup.cancelled.disconnect()
        popup.chosen.connect(on_chosen)
        popup.cancelled.connect(popup.hide)
        self._popup_wired = True
