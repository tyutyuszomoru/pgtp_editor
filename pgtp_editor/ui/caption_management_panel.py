# pgtp_editor/ui/caption_management_panel.py
"""CaptionManagementPanel: an Excel-style, filterable grid of every
caption-like attribute in the frozen Raw XML. Built on a QAbstractTableModel
fed through a multi-column QSortFilterProxyModel.

Editing is non-destructive: the scanned Value column is read-only and a
separate New Value column holds the user's edit. A row is *changed* iff its
New Value is non-empty; the literal sentinel ``<NULL>`` resolves to an empty
caption. Changed rows show a "*" marker and a cool background tint. The panel
is decoupled from MainWindow via injected callbacks (on_apply/on_close/
on_go_to_line)."""
from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.ui.caption_scan import CaptionEntry, apply_caption_edits

_COLUMNS = (
    "Changed",
    "Line",
    "Breadcrumb",
    "Element",
    "Anchor",
    "Attribute",
    "Value",
    "New Value",
)
_CHANGED_COLUMN = 0
_LINE_COLUMN = 1
_BREADCRUMB_COLUMN = 2
_ELEMENT_COLUMN = 3
_ANCHOR_COLUMN = 4
_ATTRIBUTE_COLUMN = 5
_VALUE_COLUMN = 6
_NEW_VALUE_COLUMN = 7

# The literal New Value sentinel that resolves to an empty caption.
NULL_SENTINEL = "<NULL>"

# Warm tint for rows whose (anchor, attribute) group has divergent values.
_INCONSISTENT_BACKGROUND = QColor("#3a2f1d")
# Cool tint for changed rows (New Value non-empty). Wins over inconsistency.
_CHANGED_BACKGROUND = QColor("#26343a")


class _CaptionTableModel(QAbstractTableModel):
    """Holds the scanned entries and a parallel New Value per row. The Value
    column is read-only; only New Value is editable. A row is changed iff its
    New Value is non-empty. Rows whose (anchor, attribute) group has more than
    one distinct value are flagged inconsistent (warm tint) unless changed
    (cool tint wins)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[CaptionEntry] = []
        self._new_values: list[str] = []

    # -- population ---------------------------------------------------------

    def set_entries(self, entries: Sequence[CaptionEntry]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self._new_values = ["" for _ in self._entries]
        self.endResetModel()

    def entries(self) -> list[CaptionEntry]:
        return self._entries

    def changed_edits(self) -> list[tuple[CaptionEntry, str]]:
        """(entry, resolved_new_value) for every row whose New Value is
        non-empty. `<NULL>` resolves to "" (caption set empty)."""
        result: list[tuple[CaptionEntry, str]] = []
        for entry, new_value in zip(self._entries, self._new_values):
            if new_value:
                resolved = "" if new_value == NULL_SENTINEL else new_value
                result.append((entry, resolved))
        return result

    def set_new_value(self, row: int, text: str) -> None:
        """Set the New Value of a source-model row (used by menu actions and
        paste). Repaints the row and refreshes coloring."""
        if not (0 <= row < len(self._new_values)):
            return
        self._new_values[row] = text
        self._emit_row_changed(row)

    def new_value_at(self, row: int) -> str:
        return self._new_values[row]

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
        row = index.row()
        entry = self._entries[row]
        column = index.column()
        # Sort on EditRole: return Line as an int so the Line header sorts
        # numerically (2, 3, 10) rather than lexicographically (10, 2, 3).
        if role == Qt.ItemDataRole.EditRole and column == _LINE_COLUMN:
            return entry.line
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if column == _CHANGED_COLUMN:
                return "*" if self._new_values[row] else ""
            if column == _LINE_COLUMN:
                return str(entry.line)
            if column == _BREADCRUMB_COLUMN:
                return entry.breadcrumb
            if column == _ELEMENT_COLUMN:
                return entry.element_tag
            if column == _ANCHOR_COLUMN:
                return entry.anchor
            if column == _ATTRIBUTE_COLUMN:
                return entry.attribute
            if column == _VALUE_COLUMN:
                return entry.value
            if column == _NEW_VALUE_COLUMN:
                return self._new_values[row]
        if role == Qt.ItemDataRole.BackgroundRole:
            if self._new_values[row]:
                return _CHANGED_BACKGROUND  # changed wins over inconsistency
            if self._is_inconsistent(row):
                return _INCONSISTENT_BACKGROUND
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == _NEW_VALUE_COLUMN:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != _NEW_VALUE_COLUMN:
            return False
        self._new_values[index.row()] = value
        self._emit_row_changed(index.row())
        return True

    def _emit_row_changed(self, row: int) -> None:
        # The New Value + Changed marker of this row changed; also repaint the
        # whole grid's background (inconsistency can flip for the group and the
        # changed tint spans the row).
        left = self.index(row, _CHANGED_COLUMN)
        right = self.index(row, _NEW_VALUE_COLUMN)
        self.dataChanged.emit(left, right, [Qt.ItemDataRole.DisplayRole])
        top = self.index(0, 0)
        bottom = self.index(self.rowCount() - 1, self.columnCount() - 1)
        self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.BackgroundRole])

    # -- inconsistency ------------------------------------------------------

    def _is_inconsistent(self, row: int) -> bool:
        entry = self._entries[row]
        key = (entry.anchor, entry.attribute)
        values = {
            other.value
            for other in self._entries
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
        on_go_to_line: Callable[[int], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._on_apply = on_apply or (lambda edited_text: None)
        self._on_close = on_close or (lambda: None)
        self.on_go_to_line = on_go_to_line or (lambda line: None)
        self._snapshot_text = ""

        self._model = _CaptionTableModel(self)
        self._proxy = _CaptionFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        # Sort on EditRole so the Line column sorts numerically (see model.data).
        self._proxy.setSortRole(Qt.ItemDataRole.EditRole)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )

        # One filter QLineEdit per column (removed by Phase 4).
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

        # Shortcuts scoped to the table.
        QShortcut(QKeySequence.StandardKey.Copy, self._table, self.copy_selection)
        QShortcut(QKeySequence.StandardKey.Paste, self._table, self.paste_into_new_value)
        QShortcut(QKeySequence("Ctrl+G"), self._table, self.go_to_line_current)

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

    # -- selection helpers --------------------------------------------------

    def _selected_source_rows(self) -> list[int]:
        """Distinct source-model rows of the current selection, in visual
        (proxy) order."""
        rows: list[int] = []
        seen: set[int] = set()
        for proxy_index in self._table.selectionModel().selectedIndexes():
            source_row = self._proxy.mapToSource(proxy_index).row()
            if source_row not in seen:
                seen.add(source_row)
                rows.append(source_row)
        # Order by the proxy row so paste line i -> visual row i.
        rows.sort(
            key=lambda sr: self._proxy.mapFromSource(self._model.index(sr, 0)).row()
        )
        return rows

    def _current_source_row(self) -> int | None:
        current = self._table.selectionModel().currentIndex()
        if not current.isValid():
            return None
        return self._proxy.mapToSource(current).row()

    # -- Insert NULL --------------------------------------------------------

    def insert_null_into_selection(self) -> None:
        """Set the New Value of every selected row to the NULL sentinel."""
        for source_row in self._selected_source_rows():
            self._model.set_new_value(source_row, NULL_SENTINEL)

    # -- Go to line ---------------------------------------------------------

    def go_to_line_current(self) -> None:
        source_row = self._current_source_row()
        if source_row is None:
            return
        line = self._model.entries()[source_row].line
        self.on_go_to_line(line)

    # -- Copy / Paste -------------------------------------------------------

    def copy_selection(self) -> None:
        """Copy the selected cells to the clipboard as TSV (tab between
        columns, newline between rows)."""
        indexes = self._table.selectionModel().selectedIndexes()
        if not indexes:
            return
        cells: dict[tuple[int, int], str] = {}
        rows: set[int] = set()
        cols: set[int] = set()
        for proxy_index in indexes:
            r, c = proxy_index.row(), proxy_index.column()
            rows.add(r)
            cols.add(c)
            cells[(r, c)] = proxy_index.data(Qt.ItemDataRole.DisplayRole) or ""
        lines: list[str] = []
        for r in sorted(rows):
            line = "\t".join(cells.get((r, c), "") for c in sorted(cols))
            lines.append(line)
        QGuiApplication.clipboard().setText("\n".join(lines))

    def paste_into_new_value(self) -> None:
        """Paste clipboard lines into the New Value of the selected rows.
        Line i -> selected row i; a single clipboard line fills all selected
        rows."""
        target_rows = self._selected_source_rows()
        if not target_rows:
            return
        clipboard_lines = QGuiApplication.clipboard().text().split("\n")
        if len(clipboard_lines) == 1:
            for source_row in target_rows:
                self._model.set_new_value(source_row, clipboard_lines[0])
            return
        for source_row, value in zip(target_rows, clipboard_lines):
            self._model.set_new_value(source_row, value)

    # -- context menu -------------------------------------------------------

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self._table)
        menu.addAction("Insert NULL to empty field", self.insert_null_into_selection)
        menu.addAction("Go to line in XML", self.go_to_line_current)
        menu.exec(self._table.viewport().mapToGlobal(pos))
