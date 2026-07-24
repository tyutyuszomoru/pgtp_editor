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

"""AnnotatePopover: the compact at-caret authoring surface for the schema
model's labeler-owned fields (labels / notes / kind / enum_mode).

Replaces the retired AnnotateSchemaValuesDialog. Pure view: it renders the
current annotation for one (tag_chain, attr, value) and emits `committed`
with the edited payload — persistence (model mutation, save, XSD regen)
belongs to MainWindow (_apply_annotation), keeping this widget stateless
about storage.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
)

# Display label paired with the stored kind string (kind is a labeler-owned
# model field; "unclassified" is stored as an ABSENT key).
_KIND_CHOICES = [
    ("Unclassified", "unclassified"),
    ("Setting", "setting"),
    ("Content", "content"),
]


class AnnotatePopover(QFrame):
    committed = Signal(dict)   # {"label", "note", "kind", "bitflags"}
    cancelled = Signal()

    def __init__(
        self,
        tag_chain: str,
        attr: str,
        value: str,
        label: str = "",
        note: str = "",
        kind: str = "unclassified",
        bitflags: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.header_label = QLabel(f'{tag_chain}\n{attr} = "{value}"')
        self.header_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.label_edit = QLineEdit(label)
        self.label_edit.setPlaceholderText("Meaning — e.g. pdf")
        self.note_edit = QLineEdit(note)
        self.note_edit.setPlaceholderText(
            "Note — e.g. enables the <Watermark> child tag"
        )
        self.bitflags_check = QCheckBox("Bit-flags (values add up: 3 = 1+2)")
        self.bitflags_check.setChecked(bitflags)
        self.kind_combo = QComboBox()
        for display, _key in _KIND_CHOICES:
            self.kind_combo.addItem(display)
        for index, (_display, key) in enumerate(_KIND_CHOICES):
            if key == kind:
                self.kind_combo.setCurrentIndex(index)
                break

        layout = QFormLayout(self)
        layout.addRow(self.header_label)
        layout.addRow("Label:", self.label_edit)
        layout.addRow("Note:", self.note_edit)
        layout.addRow(self.bitflags_check)
        layout.addRow("Kind:", self.kind_combo)

        self.label_edit.returnPressed.connect(self._commit)
        self.note_edit.returnPressed.connect(self._commit)

    def _commit(self) -> None:
        _display, kind = _KIND_CHOICES[self.kind_combo.currentIndex()]
        self.committed.emit({
            "label": self.label_edit.text(),
            "note": self.note_edit.text(),
            "kind": kind,
            "bitflags": self.bitflags_check.isChecked(),
        })
        self.hide()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.hide()
            return
        super().keyPressEvent(event)

    def show_at(self, global_point) -> None:
        """Show as a popup at ``global_point`` with focus in the Label field."""
        self.move(global_point)
        self.show()
        self.label_edit.setFocus()
