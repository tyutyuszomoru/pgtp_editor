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
