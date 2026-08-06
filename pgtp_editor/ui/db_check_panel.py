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

# pgtp_editor/ui/db_check_panel.py
"""DbCheckPanel: the left-dock "Database Check" results tree.

Renders one direction's `TableCheck`/`ColumnCheck` list: table rows carry a
``(T|V|M)`` kind prefix and a reference count — ``(×N)`` in the XML → Database
direction, role-split ``(P# D# L#)`` (page / detail / lookup, BUG-026) in the
Database → XML direction; column rows show the
DB datatype, PK underline, ``(fk)``, ``NOT NULL`` and ``DEFAULT`` metadata. A
green ``✓`` / red ``✗`` marker (glyph + colored foreground so it reads in both
themes) flags each row; calculated XML columns (``isCalculated="true"``,
BUG-006) get an orange ``~`` instead — they legitimately have no physical DB
counterpart, so they are never counted or filtered as mismatches. A "Show only
mismatches" checkbox re-filters to ``ok=False`` (non-calculated) rows; the
header's mismatch count is independent of the filter.

Non-modal and test-driven: the tree, header label and checkbox are exposed, and
`contextual_rename` / the double-click handler emit the two signals directly (no
`.exec()`).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

_OK_COLOR = QColor("#1a9e1a")
_BAD_COLOR = QColor("#d02020")
_CALC_COLOR = QColor("#d08a1a")
_KIND_PREFIX = {"table": "(T) ", "view": "(V) ", "matview": "(M) "}
_DIRECTION_LABEL = {
    "xml_to_db": "XML → Database",
    "db_to_xml": "Database → XML",
}


class DbCheckPanel(QWidget):
    rename_requested = Signal(str, str)  # (kind, old_name)
    jump_requested = Signal(str, str)  # (kind, name)
    create_requested = Signal(str, str)  # (what: page|detail|lookup, table_name)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._direction = ""
        self._table_checks: list = []
        self._connection_summary = ""

        from PySide6.QtWidgets import QLabel

        self.header_label = QLabel("")
        self.header_label.setWordWrap(True)

        self.filter_checkbox = QCheckBox("Show only mismatches")
        self.filter_checkbox.toggled.connect(self._rebuild)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        layout = QVBoxLayout(self)
        layout.addWidget(self.header_label)
        layout.addWidget(self.filter_checkbox)
        layout.addWidget(self.tree, 1)

    # -- population ----------------------------------------------------------

    def set_result(self, direction: str, table_checks: list, connection_summary: str) -> None:
        self._direction = direction
        self._table_checks = list(table_checks)
        self._connection_summary = connection_summary
        self._update_header()
        self._rebuild()

    def _mismatch_count(self) -> int:
        count = 0
        for table in self._table_checks:
            if not table.ok:
                count += 1
            count += sum(
                1 for column in table.columns
                if not column.ok and not column.is_calculated
            )
        return count

    def _update_header(self) -> None:
        label = _DIRECTION_LABEL.get(self._direction, self._direction)
        count = self._mismatch_count()
        noun = "mismatch" if count == 1 else "mismatches"
        self.header_label.setText(
            f"{label}   {self._connection_summary}   —   {count} {noun}"
        )

    def _rebuild(self) -> None:
        only_mismatches = self.filter_checkbox.isChecked()
        self.tree.clear()
        for table in self._table_checks:
            # Calculated columns are never mismatches (BUG-006): excluded from
            # the mismatch-only view entirely, matching the header count.
            mismatch_columns = [
                c for c in table.columns if not c.ok and not c.is_calculated
            ]
            if only_mismatches and table.ok and not mismatch_columns:
                continue
            visible_columns = mismatch_columns if only_mismatches else table.columns
            top = self._make_table_item(table)
            for column in visible_columns:
                top.addChild(self._make_column_item(column))
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)

    # -- item builders -------------------------------------------------------

    def _make_table_item(self, table) -> QTreeWidgetItem:
        marker = "✓" if table.ok else "✗"
        prefix = _KIND_PREFIX.get(table.kind, "")
        # BUG-026: the Database → XML direction splits the reference count by
        # role — page binding / detail binding / column lookup — so a table
        # used only as a lookup target reads as referenced rather than as a
        # bare "(×N) but red" contradiction. XML → Database keeps the
        # aggregate form (its checks do not populate the role fields).
        if self._direction == "db_to_xml":
            count_text = (
                f"(P{table.page_count} D{table.detail_count} L{table.lookup_count})"
            )
        else:
            count_text = f"(×{table.invocations})"
        text = f"{marker} {prefix}{table.name} {count_text}"
        item = QTreeWidgetItem([text])
        item.setForeground(0, QBrush(_OK_COLOR if table.ok else _BAD_COLOR))
        # Uniform (kind, name, ok, is_calculated) 4-tuple with the column
        # items so every unpack site reads one shape; tables are never
        # calculated.
        item.setData(0, Qt.ItemDataRole.UserRole, ("table", table.name, table.ok, False))
        return item

    def _make_column_item(self, column) -> QTreeWidgetItem:
        # Three-way state (BUG-006): calculated overrides ok for display —
        # a calculated column has no physical DB counterpart by design, so
        # it is orange-informational, never a red mismatch.
        if column.is_calculated:
            marker, color = "~", _CALC_COLOR
        elif column.ok:
            marker, color = "✓", _OK_COLOR
        else:
            marker, color = "✗", _BAD_COLOR
        parts = [marker, column.name]
        info = column.info
        if info is not None:
            if info.is_fk:
                parts.append("(fk)")
            parts.append(info.data_type)
            if not info.is_nullable:
                parts.append("NOT NULL")
            if info.default:
                parts.append(f"DEFAULT {info.default}")
        item = QTreeWidgetItem([" ".join(parts)])
        item.setForeground(0, QBrush(color))
        item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            ("column", column.name, column.ok, column.is_calculated),
        )
        if info is not None and info.is_pk:
            font = item.font(0)
            font.setUnderline(True)
            item.setFont(0, font)
        return item

    # -- interaction ---------------------------------------------------------

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, name, _ok, _is_calculated = data
        self.jump_requested.emit(kind, name)

    def contextual_rename(self, item: QTreeWidgetItem) -> None:
        """Emit `rename_requested` for a not-found node — XML→DB direction only."""
        if self._direction != "xml_to_db" or item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, name, ok, is_calculated = data
        if ok or is_calculated:
            # Calculated columns (BUG-006) have no DB-side name to reconcile —
            # offering "Rename in XML…" for one would be nonsensical.
            return
        self.rename_requested.emit(kind, name)

    # "what" -> menu label, for the Database → XML create actions on a table node.
    _CREATE_ACTIONS = (
        ("page", "Create new page from this table"),
        ("detail", "Create new detail from this table…"),
        ("lookup", "Create new lookup from this table…"),
    )

    def create_menu_items(self, item: QTreeWidgetItem | None) -> list[tuple[str, str]]:
        """The (what, label) create actions available for `item` in the
        Database → XML direction. Only table/view nodes (not columns) qualify;
        empty in the XML → Database direction. Pure — no popup — so tests can
        assert the menu contents without a modal."""
        if item is None or self._direction != "db_to_xml":
            return []
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return []
        kind, _name, _ok, _is_calculated = data
        if kind != "table":
            return []
        return list(self._CREATE_ACTIONS)

    def request_create(self, what: str, item: QTreeWidgetItem) -> None:
        """Emit `create_requested(what, table_name)` for a table node."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        _kind, name, _ok, _is_calculated = data
        self.create_requested.emit(what, name)

    def _on_context_menu(self, pos) -> None:  # pragma: no cover - GUI popup
        item = self.tree.itemAt(pos)
        if item is None:
            return
        create_items = self.create_menu_items(item)
        if create_items:
            menu = QMenu(self.tree)
            for what, label in create_items:
                action = menu.addAction(label)
                action.triggered.connect(
                    lambda _checked=False, w=what: self.request_create(w, item)
                )
            menu.exec(self.tree.viewport().mapToGlobal(pos))
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or self._direction != "xml_to_db":
            return
        kind, _name, ok, is_calculated = data
        if ok or is_calculated:
            return
        menu = QMenu(self.tree)
        action = menu.addAction(f"Rename {kind} in XML…")
        action.triggered.connect(lambda: self.contextual_rename(item))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
