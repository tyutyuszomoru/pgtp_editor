# pgtp_editor/ui/caption_management_panel.py
"""CaptionManagementPanel: an Excel-style, filterable grid of every
caption-like attribute in the frozen Raw XML. Built on a QAbstractTableModel
fed through a multi-column QSortFilterProxyModel. Only the Value column is
editable; edited rows are tracked and emitted to apply_caption_edits. The
panel is decoupled from MainWindow via injected callbacks (the FindReplaceBar
pattern)."""
from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.ui.caption_scan import CaptionEntry, apply_caption_edits

_COLUMNS = ("Line", "Element", "Anchor", "Attribute", "Value")
_VALUE_COLUMN = 4

# Subtle tint for rows whose (anchor, attribute) group has divergent values.
_INCONSISTENT_BACKGROUND = QColor("#3a2f1d")


class _CaptionTableModel(QAbstractTableModel):
    """Holds the scanned entries and the current (possibly edited) value per
    row. Only the Value column is editable; edits update `_current_values`
    and mark the row dirty. Rows whose (anchor, attribute) group has more than
    one distinct current value are flagged inconsistent (background tint)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[CaptionEntry] = []
        self._current_values: list[str] = []

    # -- population ---------------------------------------------------------

    def set_entries(self, entries: Sequence[CaptionEntry]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self._current_values = [entry.value for entry in self._entries]
        self.endResetModel()

    def entries(self) -> list[CaptionEntry]:
        return self._entries

    def changed_edits(self) -> list[tuple[CaptionEntry, str]]:
        """(entry, new_value) for every row whose current value differs from
        the originally-scanned value."""
        return [
            (entry, current)
            for entry, current in zip(self._entries, self._current_values)
            if current != entry.value
        ]

    # -- QAbstractTableModel ------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        column = index.column()
        # The proxy's sortRole is EditRole; return the Line as an int there so
        # clicking the Line header sorts document-order (2, 3, 10) rather than
        # lexicographically (10, 2, 3). DisplayRole stays str for rendering and
        # for the substring filter (which reads DisplayRole).
        if role == Qt.ItemDataRole.EditRole and column == 0:
            return entry.line
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if column == 0:
                return str(entry.line)
            if column == 1:
                return entry.element_tag
            if column == 2:
                return entry.anchor
            if column == 3:
                return entry.attribute
            if column == _VALUE_COLUMN:
                return self._current_values[index.row()]
        if role == Qt.ItemDataRole.BackgroundRole and self._is_inconsistent(index.row()):
            return _INCONSISTENT_BACKGROUND
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == _VALUE_COLUMN:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != _VALUE_COLUMN:
            return False
        self._current_values[index.row()] = value
        # Value change can flip inconsistency for the whole (anchor, attribute)
        # group, so repaint the Value column of every row.
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.EditRole])
        top = self.index(0, _VALUE_COLUMN)
        bottom = self.index(self.rowCount() - 1, _VALUE_COLUMN)
        self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.BackgroundRole])
        return True

    # -- inconsistency ------------------------------------------------------

    def _is_inconsistent(self, row: int) -> bool:
        entry = self._entries[row]
        key = (entry.anchor, entry.attribute)
        values = {
            self._current_values[i]
            for i, other in enumerate(self._entries)
            if (other.anchor, other.attribute) == key
        }
        return len(values) > 1


class _CaptionFilterProxyModel(QSortFilterProxyModel):
    """Multi-column filter: a per-column case-insensitive substring filter,
    ANDed across all columns. Empty filters match everything."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_filters: dict[int, str] = {}

    def set_column_filter(self, column: int, text: str) -> None:
        self._column_filters[column] = text.lower()
        # Re-run the filter. Both invalidateFilter() and invalidateRowsFilter()
        # are deprecated in this PySide6 version; invalidate() is the
        # non-deprecated call (it also re-sorts, negligible for our row counts).
        self.invalidate()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        model = self.sourceModel()
        for column, needle in self._column_filters.items():
            if not needle:
                continue
            index = model.index(source_row, column, source_parent)
            haystack = (index.data(Qt.ItemDataRole.DisplayRole) or "").lower()
            if needle not in haystack:
                return False
        return True


class CaptionManagementPanel(QWidget):
    def __init__(
        self,
        on_apply: Callable[[str], None] | None = None,
        on_close: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._on_apply = on_apply or (lambda edited_text: None)
        self._on_close = on_close or (lambda: None)
        self._snapshot_text = ""

        self._model = _CaptionTableModel(self)
        self._proxy = _CaptionFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        # Sort on EditRole so the Line column sorts numerically (see model.data).
        self._proxy.setSortRole(Qt.ItemDataRole.EditRole)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )

        # One filter QLineEdit per column.
        self._filter_row = QWidget()
        filter_layout = QHBoxLayout(self._filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_fields: list[QLineEdit] = []
        for column in range(self._model.columnCount()):
            field = QLineEdit()
            field.setPlaceholderText(f"Filter {_COLUMNS[column]}")
            field.textChanged.connect(
                lambda text, col=column: self._proxy.set_column_filter(col, text)
            )
            filter_layout.addWidget(field)
            self._filter_fields.append(field)

        self._apply_button = QPushButton("Apply")
        self._close_button = QPushButton("Close")
        self._apply_button.clicked.connect(self.apply)
        self._close_button.clicked.connect(self.close_panel)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._apply_button)
        button_row.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._filter_row)
        layout.addWidget(self._table)
        layout.addLayout(button_row)

    # -- API ----------------------------------------------------------------

    def load_entries(self, entries: Sequence[CaptionEntry], snapshot_text: str = "") -> None:
        """Populate the grid from a scan. `snapshot_text` is the frozen Raw
        XML the entries were scanned from; apply() writes edits back into it."""
        self._snapshot_text = snapshot_text
        self._model.set_entries(entries)

    def changed_edits(self) -> list[tuple[CaptionEntry, str]]:
        return self._model.changed_edits()

    def apply(self) -> None:
        """Compute the edited text from the snapshot + changed rows and invoke
        the injected on_apply callback with it."""
        edited_text = apply_caption_edits(self._snapshot_text, self._model.changed_edits())
        self._on_apply(edited_text)

    def close_panel(self) -> None:
        self._on_close()
