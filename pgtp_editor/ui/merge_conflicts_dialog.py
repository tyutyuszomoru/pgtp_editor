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

"""MergeConflictsDialog: the admin's never-silent gate when folding team
models into master.json — one row per (path, attr, field, value) label
conflict, with an explicit keep-master / use-incoming choice per row."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

_HEADERS = ["Element Path", "Attribute", "Field", "Value", "Keep"]
CHOICE_COLUMN = 4


class MergeConflictsDialog(QDialog):
    def __init__(self, conflicts, base_sources=None, incoming_sources=None, parent=None):
        """``base_sources``/``incoming_sources``, when given, are lists
        aligned index-wise with ``conflicts`` naming which user model each
        side of the row actually came from (the base side may be another
        user's just-adopted value rather than master's own pre-existing
        state, when several team models are merged in one pass). Falling
        back to None for either list keeps the plain "master:"/"incoming:"
        labels."""
        super().__init__(parent)
        self.setWindowTitle(f"Merge Conflicts ({len(conflicts)})")
        self._conflicts = list(conflicts)

        self.table = QTableWidget(len(self._conflicts), len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        for row, conflict in enumerate(self._conflicts):
            for column, text in enumerate([
                conflict.path,
                conflict.attr,
                conflict.field,
                conflict.value or "",
            ]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
            base_label = (base_sources[row] if base_sources else None) or "master"
            incoming_label = (
                incoming_sources[row] if incoming_sources else None
            ) or "incoming"
            combo = QComboBox()
            combo.addItem(f"{base_label}: {conflict.base}")
            combo.addItem(f"{incoming_label}: {conflict.incoming}")
            self.table.setCellWidget(row, CHOICE_COLUMN, combo)
        self.table.resizeColumnsToContents()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def choice_combo(self, row):
        return self.table.cellWidget(row, CHOICE_COLUMN)

    def resolutions(self):
        """True per row where the incoming value should replace master's."""
        return [
            self.choice_combo(row).currentIndex() == 1
            for row in range(len(self._conflicts))
        ]
