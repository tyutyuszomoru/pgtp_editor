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

"""TableReferencesPanel: the left-dock "Table references" tree.

Renders the grouped output of
:func:`pgtp_editor.analysis.reused_tables.collect_table_usages`: top-level rows
are table/view names with a usage count; child rows are individual references
carrying their :class:`TableReference` (node, kind, line) as item data.

Non-modal and test-driven: selecting a reference emits ``selection_changed`` so
MainWindow can drive the Properties panel, and double-clicking a reference emits
``jump_requested`` with the line to navigate the Raw XML editor to.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

_REF_ROLE = Qt.ItemDataRole.UserRole


class TableReferencesPanel(QWidget):
    selection_changed = Signal(object, object)  # (node | None, kind:str | None)
    jump_requested = Signal(object)             # (line:int | None)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

    def set_usages(self, usages) -> None:
        self.tree.clear()
        for usage in usages:
            top = QTreeWidgetItem([f"{usage.name}  ({len(usage.references)})"])
            for ref in usage.references:
                child = QTreeWidgetItem([ref.breadcrumb])
                child.setData(0, _REF_ROLE, ref)
                top.addChild(child)
            self.tree.addTopLevelItem(top)

    def _on_current_changed(self, current, _previous) -> None:
        ref = current.data(0, _REF_ROLE) if current is not None else None
        if ref is None:
            self.selection_changed.emit(None, None)
        else:
            self.selection_changed.emit(ref.node, ref.kind)

    def _on_double_click(self, item, _column) -> None:
        ref = item.data(0, _REF_ROLE)
        if ref is not None:
            self.jump_requested.emit(ref.line)
