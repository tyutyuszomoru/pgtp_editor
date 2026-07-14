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
from PySide6.QtGui import QColor, QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.ui.caption_scan import (
    CaptionEntry,
    apply_caption_edits,
    apply_find_replace,
    matches,
    transform_caption,
)

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

# Suffix appended to a column header when that column has an active value
# filter. Paired with a bold font + highlight foreground (see headerData) so a
# filtered column is unmistakable (issue #6).
_FILTER_INDICATOR = " ▼"
# Foreground color for a filtered column's header text (bright accent).
_FILTER_HEADER_FOREGROUND = QColor("#4fc3f7")

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
        # Columns with an active value filter (for the header ▾ indicator).
        self._filtered_columns: set[int] = set()
        # (anchor, attribute) keys whose group has >1 distinct EFFECTIVE value.
        # Precomputed by _recompute_inconsistency so _is_inconsistent is O(1).
        self._inconsistent_keys: set[tuple[str, str]] = set()

    # -- population ---------------------------------------------------------

    def set_entries(self, entries: Sequence[CaptionEntry]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self._new_values = ["" for _ in self._entries]
        self._recompute_inconsistency()
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
        """Set the New Value of a single source-model row (used by single-cell
        menu actions). Recomputes inconsistency and repaints. For bulk updates
        prefer ``set_new_values`` (one recompute + one dataChanged)."""
        if not (0 <= row < len(self._new_values)):
            return
        self._new_values[row] = text
        self._recompute_inconsistency()
        self._emit_row_changed(row)

    def set_new_values(self, updates: dict[int, str]) -> None:
        """Batched setter for bulk operations: write every New Value in
        ``updates`` (row -> text), recompute inconsistency ONCE, then emit a
        SINGLE dataChanged spanning the whole grid — rather than one recompute
        + emit per row. Out-of-range rows are ignored."""
        if not updates:
            return
        for row, text in updates.items():
            if 0 <= row < len(self._new_values):
                self._new_values[row] = text
        self._recompute_inconsistency()
        top = self.index(0, 0)
        bottom = self.index(self.rowCount() - 1, self.columnCount() - 1)
        self.dataChanged.emit(
            top,
            bottom,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.EditRole,
                Qt.ItemDataRole.BackgroundRole,
            ],
        )

    def new_value_at(self, row: int) -> str:
        return self._new_values[row]

    # -- QAbstractTableModel ------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    def set_filtered_columns(self, columns: set[int]) -> None:
        """Record which columns have an active value filter so their headers
        show the ▾ indicator. Repaints the horizontal header."""
        if columns == self._filtered_columns:
            return
        self._filtered_columns = set(columns)
        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal, 0, len(_COLUMNS) - 1
        )

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        is_filtered = section in self._filtered_columns
        if role == Qt.ItemDataRole.DisplayRole:
            label = _COLUMNS[section]
            if is_filtered:
                label += _FILTER_INDICATOR
            return label
        # A filtered column's header is signalled unmistakably (issue #6): bold
        # font AND a bright accent foreground, on top of the ▼ marker.
        if is_filtered and role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setBold(True)
            return font
        if is_filtered and role == Qt.ItemDataRole.ForegroundRole:
            return _FILTER_HEADER_FOREGROUND
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
        self._recompute_inconsistency()
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

    def _recompute_inconsistency(self) -> None:
        """Scan entries once, grouping by (anchor, attribute) using each row's
        EFFECTIVE value (its New Value if non-empty, else entry.value), and
        store the set of keys whose group has >1 distinct effective value.
        Using the effective value means a group that has been unified/edited
        into agreement drops its inconsistency tint even on unedited siblings.
        Called on populate and after any value mutation so ``_is_inconsistent``
        is an O(1) membership test."""
        groups: dict[tuple[str, str], set[str]] = {}
        for entry, new_value in zip(self._entries, self._new_values):
            key = (entry.anchor, entry.attribute)
            effective = new_value if new_value else entry.value
            groups.setdefault(key, set()).add(effective)
        self._inconsistent_keys = {
            key for key, values in groups.items() if len(values) > 1
        }

    def _is_inconsistent(self, row: int) -> bool:
        entry = self._entries[row]
        return (entry.anchor, entry.attribute) in self._inconsistent_keys


class _CaptionFilterProxyModel(QSortFilterProxyModel):
    """Multi-mechanism filter combining two independent, ANDed filters:

    * a whole-row **find filter** (Phase 4 shared modal): a row passes iff ANY
      of its displayed cells matches the find pattern under the given search
      mode + case (``set_regex_filter(pattern, mode, case)``; empty pattern =
      no filter). Handles the three ``caption_scan`` modes, incl. regex.
    * a per-column Excel-style **value-set** filter (the header-filter popup):
      ``set_value_filter(column, allowed)`` keeps a row iff its cell text for
      that column is in ``allowed`` (``None`` = no value filter on that
      column).

    A row is accepted iff it passes every active filter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value_filters: dict[int, set[str]] = {}
        # Whole-row find filter (Phase 4). Empty pattern = inactive.
        self._find_pattern: str = ""
        self._find_mode: str = "normal"
        self._find_case: bool = False

    def set_regex_filter(self, pattern: str, mode: str, case: bool) -> None:
        """Set the whole-row find filter. A row passes iff any displayed cell
        matches `pattern` under `mode`/`case` (see caption_scan.matches). An
        empty `pattern` clears the filter. Raises ValueError on invalid regex
        (the caller/dialog catches it and shows an inline error)."""
        # Validate up front so an invalid regex surfaces immediately (via the
        # dialog's ValueError catch) rather than being swallowed per-row.
        matches("", pattern, mode, case)
        self._find_pattern = pattern
        self._find_mode = mode
        self._find_case = case
        self.invalidate()

    def find_pattern(self) -> str:
        return self._find_pattern

    def set_value_filter(self, column: int, allowed: set[str] | None) -> None:
        """Restrict `column` to rows whose DisplayRole text is in `allowed`.
        `None` removes the value filter for that column."""
        if allowed is None:
            self._value_filters.pop(column, None)
        else:
            self._value_filters[column] = set(allowed)
        self._notify_filtered_columns()
        self.invalidate()

    def value_filter(self, column: int) -> set[str] | None:
        allowed = self._value_filters.get(column)
        return set(allowed) if allowed is not None else None

    def filtered_columns(self) -> set[int]:
        return set(self._value_filters)

    def _notify_filtered_columns(self) -> None:
        model = self.sourceModel()
        setter = getattr(model, "set_filtered_columns", None)
        if setter is not None:
            setter(self.filtered_columns())

    def setSourceModel(self, model) -> None:  # noqa: N802 (Qt override)
        super().setSourceModel(model)
        self._notify_filtered_columns()

    def _passes_find_filter(self, source_row, source_parent=QModelIndex()) -> bool:
        """True iff the row passes the whole-row find filter (or none active)."""
        if not self._find_pattern:
            return True
        model = self.sourceModel()
        try:
            return any(
                matches(
                    model.index(source_row, column, source_parent).data(
                        Qt.ItemDataRole.DisplayRole
                    )
                    or "",
                    self._find_pattern,
                    self._find_mode,
                    self._find_case,
                )
                for column in range(model.columnCount())
            )
        except ValueError:
            # Invalid pattern (should have been caught at set time): treat as no
            # match rather than crash the view repaint.
            return False

    def _passes_value_filters(
        self, source_row, source_parent=QModelIndex(), exclude_column: int | None = None
    ) -> bool:
        """True iff the row passes every active per-column value filter, except
        the one on `exclude_column` (used for cascaded distinct values)."""
        model = self.sourceModel()
        for column, allowed in self._value_filters.items():
            if column == exclude_column:
                continue
            cell = model.index(source_row, column, source_parent).data(
                Qt.ItemDataRole.DisplayRole
            ) or ""
            if cell not in allowed:
                return False
        return True

    def row_passes_other_filters(self, source_row, target_column: int) -> bool:
        """True iff `source_row` passes the find filter AND every value filter
        EXCEPT the one on `target_column`. Used to compute cascaded distinct
        values for the header popup of `target_column` (issue #5)."""
        return self._passes_find_filter(source_row) and self._passes_value_filters(
            source_row, exclude_column=target_column
        )

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        if not self._passes_find_filter(source_row, source_parent):
            return False
        return self._passes_value_filters(source_row, source_parent)


class _HeaderFilterPopup(QWidget):
    """Non-blocking Excel-style value-filter popup for one column.

    Lists the column's DISTINCT source-model values as checkable items (all
    checked by default, or reflecting the column's current filter), with
    "Select all" / "Clear" and OK. OK calls ``on_apply(column, allowed)``
    where ``allowed`` is ``None`` when every value is checked (no filter) and
    the checked set otherwise. Built with the ``Qt.Popup`` window flag so it
    dismisses on outside click without a blocking modal loop — tests drive its
    methods directly and never call ``.exec()``."""

    def __init__(
        self,
        column: int,
        values: Sequence[str],
        checked: set[str] | None,
        on_apply: Callable[[int, set[str] | None], None],
        parent=None,
    ):
        super().__init__(parent, Qt.WindowType.Popup)
        self._column = column
        self._values = list(values)
        self._on_apply = on_apply

        self._list = QListWidget()
        for value in self._values:
            # Show the empty distinct value with a readable placeholder while
            # still filtering on the real "" (see checked_values, which maps by
            # index back to self._values, not the displayed label).
            item = QListWidgetItem(value if value != "" else "(empty)")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            initially_checked = checked is None or value in checked
            item.setCheckState(
                Qt.CheckState.Checked if initially_checked else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)

        # Clicking ANYWHERE on a value row toggles its checkbox (issue #4):
        # without this only the small checkbox indicator toggles, so the common
        # "Clear → click a value → OK" gesture would apply an empty checked set
        # (0 rows). itemClicked flips the whole row's check state.
        self._list.itemClicked.connect(self._toggle_item)

        # Excel-style search box at the TOP of the popup. Typing narrows the
        # visible rows to substring matches and (for a non-empty query) checks
        # matches / unchecks non-matches, so OK filters the column to exactly
        # the search matches. Clearing reveals all rows and leaves check state
        # alone so a manual selection is not clobbered.
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.textChanged.connect(self._on_search)

        select_all_btn = QPushButton("Select all")
        clear_btn = QPushButton("Clear")
        ok_btn = QPushButton("OK")
        select_all_btn.clicked.connect(self.select_all)
        clear_btn.clicked.connect(self.clear_all)
        ok_btn.clicked.connect(self._ok)

        top_row = QHBoxLayout()
        top_row.addWidget(select_all_btn)
        top_row.addWidget(clear_btn)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        bottom_row.addWidget(ok_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addLayout(top_row)
        layout.addWidget(self._list)
        layout.addLayout(bottom_row)

    # -- test/drive API -----------------------------------------------------

    def item_labels(self) -> list[str]:
        return list(self._values)

    def is_checked(self, index: int) -> bool:
        return self._list.item(index).checkState() == Qt.CheckState.Checked

    def set_checked(self, index: int, checked: bool) -> None:
        self._list.item(index).setCheckState(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )

    def _toggle_item(self, item: QListWidgetItem) -> None:
        """Flip `item`'s check state. Wired to the list's ``itemClicked`` so a
        click anywhere on a value row toggles its checkbox (issue #4)."""
        now_checked = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(
            Qt.CheckState.Unchecked if now_checked else Qt.CheckState.Checked
        )

    def _on_search(self, text: str) -> None:
        """Narrow the list to substring matches of `text`. For a NON-EMPTY
        query, also check matches and uncheck non-matches so OK filters the
        column to exactly the search results. An EMPTY query reveals every row
        and leaves check states unchanged (don't clobber a manual selection)."""
        query = text.strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            matched = query in self._values[i].lower()
            item.setHidden(not matched)
            if query:
                item.setCheckState(
                    Qt.CheckState.Checked if matched else Qt.CheckState.Unchecked
                )

    def select_all(self) -> None:
        # When a search is active, act only on the currently-visible (matching)
        # rows — "Select all search results".
        for i in range(self._list.count()):
            if not self._list.item(i).isHidden():
                self._list.item(i).setCheckState(Qt.CheckState.Checked)

    def clear_all(self) -> None:
        # When a search is active, act only on the currently-visible (matching)
        # rows — "Clear search results".
        for i in range(self._list.count()):
            if not self._list.item(i).isHidden():
                self._list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def checked_values(self) -> set[str]:
        return {
            self._values[i]
            for i in range(self._list.count())
            if self.is_checked(i)
        }

    def apply_filter(self) -> None:
        """Push the current checkbox state to the proxy via on_apply. When all
        values are checked the column has no filter (``None``)."""
        checked = self.checked_values()
        allowed = None if len(checked) == len(self._values) else checked
        self._on_apply(self._column, allowed)

    def _ok(self) -> None:
        self.apply_filter()
        self.close()


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
        # Callbacks opening the shared caption Find/Filter/Replace dialog in
        # filter vs replace mode (issue #1). MainWindow wires these after
        # construction; the panel's own Ctrl+F / Ctrl+R shortcuts invoke them.
        self.on_open_filter = lambda: None
        self.on_open_replace = lambda: None
        self._snapshot_text = ""

        self._model = _CaptionTableModel(self)
        self._proxy = _CaptionFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        # Sort on EditRole so the Line column sorts numerically (see model.data).
        self._proxy.setSortRole(Qt.ItemDataRole.EditRole)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        # Header-click opens the Excel-style value-filter popup (see
        # open_header_filter). Sorting therefore moves off left-click: it is
        # available programmatically (proxy.sort) and via the header's
        # right-click context menu (Sort ascending / descending). We disable
        # QTableView's built-in click-to-sort so a header click filters rather
        # than sorts, but keep the proxy sortable so sorting still works.
        self._table.setSortingEnabled(False)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self.open_header_filter)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)

        self._apply_button = QPushButton("Apply")
        # Clear, obvious way to leave Caption Mode (issue #2). Wired to on_close
        # → MainWindow._close_caption_mode → leave_caption_mode.
        self._close_button = QPushButton("Exit Caption Mode")
        self._apply_button.clicked.connect(self.apply)
        self._close_button.clicked.connect(self.close_panel)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._apply_button)
        button_row.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(button_row)

        # Shortcuts scoped to the table.
        QShortcut(QKeySequence.StandardKey.Copy, self._table, self.copy_selection)
        QShortcut(QKeySequence.StandardKey.Paste, self._table, self.paste_into_new_value)
        QShortcut(QKeySequence("Ctrl+G"), self._table, self.go_to_line_current)

        # Ctrl+F / Ctrl+R for the caption Filter / Replace dialogs are owned by
        # MainWindow as window-scoped, mode-gated shortcuts (issue #1) so they
        # follow Caption Mode rather than focus. They call this panel's
        # open_filter_dialog / open_replace_dialog methods below, which delegate
        # to the injected on_open_filter / on_open_replace callbacks.

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

    def open_filter_dialog(self) -> None:
        """Panel Ctrl+F: open the shared caption dialog in FILTER mode (issue
        #1). Delegates to the MainWindow-injected callback."""
        self.on_open_filter()

    def open_replace_dialog(self) -> None:
        """Panel Ctrl+R: open the shared caption dialog in REPLACE mode (issue
        #1). Delegates to the MainWindow-injected callback."""
        self.on_open_replace()

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
        updates = {row: NULL_SENTINEL for row in self._selected_source_rows()}
        self._model.set_new_values(updates)

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
            updates = {row: clipboard_lines[0] for row in target_rows}
        else:
            updates = dict(zip(target_rows, clipboard_lines))
        self._model.set_new_values(updates)

    # -- shared find / filter / replace (Phase 4) ---------------------------

    def apply_find_filter(self, pattern: str, mode: str, case: bool) -> None:
        """Apply a whole-row find filter via the proxy. Raises ValueError on an
        invalid regex (caller/dialog shows it inline)."""
        self._proxy.set_regex_filter(pattern, mode, case)

    def current_filter_pattern(self) -> str:
        """The proxy's currently-active find pattern (for pre-loading the
        Replace dialog's Find-what)."""
        return self._proxy.find_pattern()

    def _visible_source_rows(self) -> list[int]:
        """Source-model rows currently visible through the proxy (the
        In-selection / filtered scope for Replace All)."""
        return [
            self._proxy.mapToSource(self._proxy.index(r, 0)).row()
            for r in range(self._proxy.rowCount())
        ]

    def replace_all_find(
        self,
        find: str,
        replacement: str,
        mode: str,
        case: bool,
        in_selection: bool,
    ) -> int:
        """Apply find->replace to the Value of each row in scope, writing the
        result into that row's New Value (non-destructive). Scope: In selection
        = currently-visible/filtered rows; Global = all source rows. Returns the
        number of rows changed. Raises ValueError on invalid regex."""
        if in_selection:
            rows = self._visible_source_rows()
        else:
            rows = list(range(self._model.rowCount()))
        updates: dict[int, str] = {}
        for source_row in rows:
            old_value = self._model.entries()[source_row].value
            new_value = apply_find_replace(old_value, find, replacement, mode, case)
            if new_value is not None:
                updates[source_row] = new_value
        self._model.set_new_values(updates)
        return len(updates)

    # -- bulk transform + unify (Phase 5) -----------------------------------

    def bulk_transform_selection(self, kind: str) -> None:
        """Apply ``transform_caption(seed, kind)`` to every selected row and
        write the result into that row's New Value. For most kinds the seed is
        the row's current New Value if non-empty, else its (read-only) Value —
        a one-click edit that seeds from the original caption. The exception is
        ``"humanize"``, whose whole purpose is to derive a caption *from the
        field name*: it seeds from the row's anchor (the column's fieldName),
        so e.g. `physical_location_id` becomes `Physical Location` regardless of
        the current caption. The Value column is never touched."""
        entries = self._model.entries()
        updates: dict[int, str] = {}
        for source_row in self._selected_source_rows():
            entry = entries[source_row]
            if kind == "humanize":
                seed = entry.anchor
            else:
                new_value = self._model.new_value_at(source_row)
                seed = new_value if new_value else entry.value
            updates[source_row] = transform_caption(seed, kind)
        self._model.set_new_values(updates)

    def unify_from_row(self, source_row: int) -> None:
        """Set the New Value of every OTHER row sharing this row's
        ``(anchor, attribute)`` whose effective current value differs from the
        source row's target, to that target. The target is the source row's New
        Value if set, else its Value. A row's effective current value is its New
        Value if set, else its Value; rows already matching are left
        untouched."""
        if not (0 <= source_row < self._model.rowCount()):
            return
        entries = self._model.entries()
        source_entry = entries[source_row]
        source_new = self._model.new_value_at(source_row)
        target = source_new if source_new else source_entry.value
        key = (source_entry.anchor, source_entry.attribute)
        updates: dict[int, str] = {}
        for row, entry in enumerate(entries):
            if row == source_row:
                continue
            if (entry.anchor, entry.attribute) != key:
                continue
            row_new = self._model.new_value_at(row)
            effective = row_new if row_new else entry.value
            if effective != target:
                updates[row] = target
        self._model.set_new_values(updates)

    def unify_current(self) -> None:
        source_row = self._current_source_row()
        if source_row is None:
            return
        self.unify_from_row(source_row)

    # -- header value filters (Phase 3) -------------------------------------

    def distinct_values(self, column: int) -> list[str]:
        """De-duplicated, sorted DisplayRole values for `column`, read from the
        SOURCE model (all rows), independent of the current filtered view."""
        values = {
            self._model.index(row, column).data(Qt.ItemDataRole.DisplayRole) or ""
            for row in range(self._model.rowCount())
        }
        return sorted(values)

    def cascaded_distinct_values(self, column: int) -> list[str]:
        """Excel-style cascaded distinct values for `column` (issue #5).

        List only the values present in the CURRENTLY-FILTERED set: a source
        row contributes its `column` value only if the row passes every OTHER
        active value-filter AND the active find filter. The target column's own
        value-filter is EXCLUDED from the test, so you can still see and adjust
        its own values. With no other filters active this equals
        ``distinct_values(column)``."""
        values: set[str] = set()
        for row in range(self._model.rowCount()):
            if not self._proxy.row_passes_other_filters(row, column):
                continue
            cell = self._model.index(row, column).data(Qt.ItemDataRole.DisplayRole) or ""
            values.add(cell)
        return sorted(values)

    def open_header_filter(self, column: int) -> _HeaderFilterPopup:
        """Build and show the non-blocking value-filter popup for `column`,
        seeded from the column's CASCADED distinct values (only values present
        in the currently-filtered set, excluding this column's own filter —
        issue #5) and its current filter state. Returns the popup so tests can
        drive it without ``.exec()``."""
        popup = _HeaderFilterPopup(
            column,
            self.cascaded_distinct_values(column),
            self._proxy.value_filter(column),
            on_apply=self._proxy.set_value_filter,
            parent=self,
        )
        header = self._table.horizontalHeader()
        pos = header.mapToGlobal(header.rect().bottomLeft())
        popup.move(pos)
        popup.show()
        return popup

    def _show_header_context_menu(self, pos) -> None:
        header = self._table.horizontalHeader()
        column = header.logicalIndexAt(pos)
        if column < 0:
            return
        menu = QMenu(self._table)
        menu.addAction(
            "Sort ascending",
            lambda: self._proxy.sort(column, Qt.SortOrder.AscendingOrder),
        )
        menu.addAction(
            "Sort descending",
            lambda: self._proxy.sort(column, Qt.SortOrder.DescendingOrder),
        )
        menu.addSeparator()
        menu.addAction("Filter…", lambda: self.open_header_filter(column))
        menu.exec(header.mapToGlobal(pos))

    # -- context menu -------------------------------------------------------

    # Transform ▸ submenu: display label -> transform_caption kind.
    _TRANSFORM_ACTIONS: tuple[tuple[str, str], ...] = (
        ("Title Case", "title"),
        ("UPPERCASE", "upper"),
        ("lowercase", "lower"),
        ("Sentence case", "sentence"),
        ("Trim whitespace", "trim"),
        ("Humanize field name", "humanize"),
    )

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self._table)
        menu.addAction("Insert NULL to empty field", self.insert_null_into_selection)
        menu.addAction("Go to line in XML", self.go_to_line_current)
        menu.addSeparator()
        transform_menu = menu.addMenu("Transform")
        for label, kind in self._TRANSFORM_ACTIONS:
            transform_menu.addAction(
                label, lambda kind=kind: self.bulk_transform_selection(kind)
            )
        menu.addAction(
            "Unify: set all inconsistent siblings to this value",
            self.unify_current,
        )
        menu.exec(self._table.viewport().mapToGlobal(pos))
