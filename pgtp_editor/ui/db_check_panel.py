# pgtp_editor/ui/db_check_panel.py
"""DbCheckPanel: the left-dock "Database Check" results tree.

Renders one direction's `TableCheck`/`ColumnCheck` list: table rows carry a
``(T|V|M)`` kind prefix and an ``(×N)`` invocation count; column rows show the
DB datatype, PK underline, ``(fk)``, ``NOT NULL`` and ``DEFAULT`` metadata. A
green ``✓`` / red ``✗`` marker (glyph + colored foreground so it reads in both
themes) flags each row. A "Show only mismatches" checkbox re-filters to
``ok=False`` rows; the header's mismatch count is independent of the filter.

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
_KIND_PREFIX = {"table": "(T) ", "view": "(V) ", "matview": "(M) "}
_DIRECTION_LABEL = {
    "xml_to_db": "XML → Database",
    "db_to_xml": "Database → XML",
}


class DbCheckPanel(QWidget):
    rename_requested = Signal(str, str)  # (kind, old_name)
    jump_requested = Signal(str, str)  # (kind, name)

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
            count += sum(1 for column in table.columns if not column.ok)
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
            mismatch_columns = [c for c in table.columns if not c.ok]
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
        text = f"{marker} {prefix}{table.name} (×{table.invocations})"
        item = QTreeWidgetItem([text])
        item.setForeground(0, QBrush(_OK_COLOR if table.ok else _BAD_COLOR))
        item.setData(0, Qt.ItemDataRole.UserRole, ("table", table.name, table.ok))
        return item

    def _make_column_item(self, column) -> QTreeWidgetItem:
        marker = "✓" if column.ok else "✗"
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
        item.setForeground(0, QBrush(_OK_COLOR if column.ok else _BAD_COLOR))
        item.setData(0, Qt.ItemDataRole.UserRole, ("column", column.name, column.ok))
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
        kind, name, _ok = data
        self.jump_requested.emit(kind, name)

    def contextual_rename(self, item: QTreeWidgetItem) -> None:
        """Emit `rename_requested` for a not-found node — XML→DB direction only."""
        if self._direction != "xml_to_db" or item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, name, ok = data
        if ok:
            return
        self.rename_requested.emit(kind, name)

    def _on_context_menu(self, pos) -> None:  # pragma: no cover - GUI popup
        item = self.tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or self._direction != "xml_to_db":
            return
        kind, _name, ok = data
        if ok:
            return
        menu = QMenu(self.tree)
        action = menu.addAction(f"Rename {kind} in XML…")
        action.triggered.connect(lambda: self.contextual_rename(item))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
