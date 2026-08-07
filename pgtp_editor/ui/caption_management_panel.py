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
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
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

#: Search-mode labels, in display order, paired with the ``caption_scan`` mode.
#: All THREE modes are offered: ``extended`` is the only way escape sequences
#: (``\n``, ``\t``, ``\0``, ``\xNN``) in caption text can be matched, and the
#: grid is the only surface where those occur, so dropping it would be a
#: capability removal (FQ-017 (f)). Lived in the deleted
#: ``caption_find_replace_dialog`` module until FQ-017; the bar is now the only
#: consumer, so it owns the labels.
MODE_LABELS: tuple[tuple[str, str], ...] = (
    ("Normal (plain string)", "normal"),
    ("Extended (\\n \\t \\0 \\xNN)", "extended"),
    ("Regular expression", "regular"),
)

#: Replace-All scope labels, in display order, paired with the internal scope
#: key. ``filtered`` is the default and is what the LIVE preview always uses;
#: ``project`` is inert until Replace All is pressed, so no keystroke can ever
#: rewrite every caption in the project (FQ-017 (c)).
SCOPE_LABELS: tuple[tuple[str, str], ...] = (
    ("in filtered results", "filtered"),
    ("in all project", "project"),
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
_INCONSISTENT_FOREGROUND = QColor("#f0e6d2")
# Cool tint for changed rows (New Value non-empty). Wins over inconsistency.
_CHANGED_BACKGROUND = QColor("#26343a")
_CHANGED_FOREGROUND = QColor("#dceaf0")
# Both backgrounds are dark regardless of app theme (BUG-005): they are paired
# with an explicit near-white foreground rather than left to the palette's
# default text role, which is near-black under Light Theme and would be
# unreadable against these tints.


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

    def entry_at(self, source_row: int) -> CaptionEntry:
        """The CaptionEntry backing `source_row` (used by the proxy's row
        predicate to filter on the entry's exact table_name/field_name/etc.)."""
        return self._entries[source_row]

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
                Qt.ItemDataRole.ForegroundRole,
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
        if role == Qt.ItemDataRole.ForegroundRole:
            if self._new_values[row]:
                return _CHANGED_FOREGROUND
            if self._is_inconsistent(row):
                return _INCONSISTENT_FOREGROUND
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
        self.dataChanged.emit(
            top, bottom, [Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole]
        )

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
        # Preset row predicate (Phase C.2): fn(entry: CaptionEntry) -> bool, or
        # None for no predicate. ANDed with the find + value filters. Reads the
        # source CaptionEntry via the model's entry_at accessor.
        self._row_predicate: Callable[[CaptionEntry], bool] | None = None
        # Human-readable description of the active row predicate, e.g.
        # "Field = wbs_id" (BUG-020). Empty when no predicate is active. Kept
        # alongside the predicate so the two can never drift out of sync.
        self._row_predicate_label: str = ""

    def set_row_predicate(
        self,
        predicate: Callable[[CaptionEntry], bool] | None,
        label: str = "",
    ) -> None:
        """Set a preset row predicate over the source ``CaptionEntry`` (Phase
        C.2). A row passes iff ``predicate(entry)`` is True; ``None`` clears it
        (and resets the label to ``""`` regardless of what was passed).
        ANDed with the find + value filters.

        ``label`` is a human-readable description of what the predicate
        narrows to (e.g. "Field = wbs_id"), surfaced by the panel's
        active-filter banner (BUG-020) so a preset filter is never invisible.
        """
        self._row_predicate = predicate
        self._row_predicate_label = label if predicate is not None else ""
        self.invalidate()

    def row_predicate(self) -> Callable[[CaptionEntry], bool] | None:
        return self._row_predicate

    def row_predicate_label(self) -> str:
        return self._row_predicate_label

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

    def find_mode(self) -> str:
        """Search mode of the active find filter (one of
        ``caption_scan.SEARCH_MODES``). Exposed so the panel's active-filter
        banner can describe the filter without reading private attrs
        (BUG-028)."""
        return self._find_mode

    def find_case(self) -> bool:
        """Case-sensitivity flag of the active find filter (BUG-028)."""
        return self._find_case

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

    def is_any_filter_active(self) -> bool:
        """True iff any of the three filter mechanisms (preset row predicate,
        find filter, or a header value filter) currently narrows the grid.
        Used by Unify (BUG-023) to decide whether to prompt for scope."""
        return bool(
            self._row_predicate is not None
            or self._find_pattern
            or self._value_filters
        )

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

    def _passes_row_predicate(self, source_row) -> bool:
        """True iff the preset row predicate accepts the source row's entry (or
        no predicate is active)."""
        if self._row_predicate is None:
            return True
        model = self.sourceModel()
        getter = getattr(model, "entry_at", None)
        if getter is None:
            return True
        return bool(self._row_predicate(getter(source_row)))

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        if not self._passes_row_predicate(source_row):
            return False
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


class CaptionFindReplaceBar(QWidget):
    """The Caption grid's own **permanently visible** Find/Replace bar — a
    sibling of ``find_replace_bar.FindReplaceBar``, but for a *grid* rather than
    a text document, and with a **live** Replace.

    "Live" is what separates it from an ordinary Replace All: every keystroke in
    the Find or Replace-with field, and every change of Search Mode / Match
    case, immediately re-computes the proposal for the in-scope rows and writes
    it into the grid's **New Value** column via the injected
    ``on_live_replace(find, replacement, mode, case)``. The XML is never touched
    — New Value is, as always, only a proposal that a separate explicit Apply
    turns into text (§13).

    Because the preview is recomputed rather than accumulated, it is fully
    reversible: clearing the Find field puts every row's previous New Value
    back. The panel owns that bookkeeping.

    **Never hidden, never shown (FQ-017).** The bar replaced a modal Caption
    Filter dialog and its two mode-gated ``Ctrl+F``/``Ctrl+R`` window
    shortcuts, so there is nothing left to reveal: ``Ctrl+F`` / ``Ctrl+R``
    **focus** the Find / Replace-with field (:meth:`focus_find` /
    :meth:`focus_replace`) and ``Escape`` hands focus **back to the grid**
    (``on_escape``) instead of hiding anything. There is consequently no Close
    button.

    **"Active" means the Find field is non-empty.** With no show/close
    lifecycle, "the bar is driving a preview" can only mean "there is a pattern
    in the Find field" — see :meth:`is_active`, which the panel's
    ``_refresh_live_replace`` guard reads.

    **Replace All is the commit gesture** the deleted Close button used to be:
    it hands the live preview over to the panel as ordinary, hand-editable New
    Values (the panel forgets the rollback baseline). The other release gesture
    is emptying the Find field, which rolls the preview back cleanly.

    **The scope dropdown selects Replace All's scope only.** ``"in filtered
    results"`` (the default) is what the live preview already does
    continuously; ``"in all project"`` is inert until the button is pressed, so
    a keystroke can never rewrite every caption in the project.

    **Filter is deliberately NOT live.** It stays behind the Filter button, so
    the set of rows the live Replace acts on only ever changes on an explicit
    gesture — a live filter racing a live replace would make the proposal
    scope unreadable.

    Invalid regex is reported in the inline ``error_label`` (never a modal, and
    never an exception out of a keystroke handler); the panel guarantees the
    preview has already been rolled back when it raises."""

    def __init__(
        self,
        on_live_replace: Callable[[str, str, str, bool], int],
        on_filter: Callable[[str, str, bool], None],
        on_replace_all: Callable[[str, str, str, bool, bool], int] | None = None,
        on_clear_filter: Callable[[], None] | None = None,
        on_escape: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._on_live_replace = on_live_replace
        self._on_filter = on_filter
        self._on_replace_all = on_replace_all or (lambda f, r, m, c, p: 0)
        self._on_clear_filter = on_clear_filter or (lambda: None)
        self._on_escape = on_escape or (lambda: None)
        # Guards the live re-run while the bar itself is programmatically
        # rewriting its own fields (set_find_text / reset), so a caller cannot
        # trigger a half-configured preview.
        self._suspended = False
        # True once Replace All has handed the preview over as ordinary
        # proposals, until the user next touches a field. See is_active().
        self._committed = False

        self.find_field = QLineEdit()
        self.find_field.setPlaceholderText("Find")
        self.replace_field = QLineEdit()
        self.replace_field.setPlaceholderText("Replace with (live)")

        self.mode_combo = QComboBox()
        for label, mode in MODE_LABELS:
            self.mode_combo.addItem(label, mode)
        self.match_case_checkbox = QCheckBox("Match case")
        self.filter_button = QPushButton("Filter")
        # Bound to the panel's single existing clear path, ``clear_all_filters``
        # — which clears the find filter, every header value filter AND the
        # tree-set row predicate. The label is singular because that is the one
        # the owner specified; the tooltip spells out the real reach, since the
        # retained active-filter banner is the only surface that shows the row
        # predicates this button also drops (FQ-017 (e)).
        self.clear_filter_button = QPushButton("Clear filter")
        self.clear_filter_button.setToolTip(
            "Clear the find filter, every column filter and the active row filter"
        )

        # Scope for Replace All, immediately before the button. NOT wired to the
        # live preview: see the class docstring.
        self.scope_combo = QComboBox()
        for label, scope in SCOPE_LABELS:
            self.scope_combo.addItem(label, scope)
        self.replace_all_button = QPushButton("Replace All")

        self.status_label = QLabel("")
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #d05050;")
        self.error_label.setWordWrap(True)

        find_row = QHBoxLayout()
        find_row.addWidget(self.find_field)
        find_row.addWidget(self.mode_combo)
        find_row.addWidget(self.match_case_checkbox)
        find_row.addWidget(self.filter_button)
        find_row.addWidget(self.clear_filter_button)

        replace_row = QHBoxLayout()
        replace_row.addWidget(self.replace_field)
        replace_row.addWidget(self.scope_combo)
        replace_row.addWidget(self.replace_all_button)
        replace_row.addWidget(self.status_label)
        replace_row.addWidget(self.error_label, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addLayout(find_row)
        layout.addLayout(replace_row)

        self.find_field.textChanged.connect(self.run_live_replace)
        self.replace_field.textChanged.connect(self.run_live_replace)
        self.mode_combo.currentIndexChanged.connect(self.run_live_replace)
        self.match_case_checkbox.toggled.connect(self.run_live_replace)
        self.filter_button.clicked.connect(self.apply_filter)
        self.clear_filter_button.clicked.connect(self.clear_filter)
        self.replace_all_button.clicked.connect(self.replace_all)
        # Deliberately NOT connected to run_live_replace: the scope only takes
        # effect when Replace All is pressed.

    # -- field getters ------------------------------------------------------

    def selected_mode(self) -> str:
        return self.mode_combo.currentData()

    def set_mode(self, mode: str) -> None:
        index = self.mode_combo.findData(mode)
        if index < 0:
            raise ValueError(f"Unknown search mode: {mode!r}")
        self.mode_combo.setCurrentIndex(index)

    def match_case(self) -> bool:
        return self.match_case_checkbox.isChecked()

    def set_find_text(self, text: str) -> None:
        """Set the Find field without re-running the live replace (the caller
        typically follows up with its own explicit run)."""
        self._suspended = True
        try:
            self.find_field.setText(text)
        finally:
            self._suspended = False

    def selected_scope(self) -> str:
        """``"filtered"`` or ``"project"`` — the scope Replace All will use."""
        return self.scope_combo.currentData()

    def set_scope(self, scope: str) -> None:
        index = self.scope_combo.findData(scope)
        if index < 0:
            raise ValueError(f"Unknown replace scope: {scope!r}")
        self.scope_combo.setCurrentIndex(index)

    # -- focus (the bar is never hidden) ------------------------------------

    def focus_find(self, initial_find: str = "") -> None:
        """Put the cursor in the Find field. The bar is already visible, so this
        is what ``Ctrl+F`` does now — there is nothing to show.

        ``initial_find`` seeds Find-what from the grid's active filter pattern
        (the old ``show_bar`` seeding, so Filter-then-Replace reuse still
        works), but ONLY when the field is empty: clobbering text the user has
        already typed would be a hostile thing for a focus gesture to do."""
        if initial_find and not self.find_field.text():
            self.set_find_text(initial_find)
        self.find_field.setFocus()
        self.find_field.selectAll()

    def focus_replace(self) -> None:
        """Put the cursor in the Replace-with field (``Ctrl+R``)."""
        self.replace_field.setFocus()
        self.replace_field.selectAll()

    def is_active(self) -> bool:
        """True while this bar is driving a live preview — i.e. **the Find field
        is non-empty** and Replace All has not committed since it was last
        typed in.

        This replaced a "True between show_bar and close_bar" flag: with a
        permanently visible bar there is no show and no close, and a pattern in
        the Find field is exactly the condition under which a re-run has
        something to propose. An empty Find field makes
        ``live_replace_preview`` roll everything back and propose nothing, so
        treating it as inactive is accurate, not merely convenient.

        ⚠️ **The committed half is load-bearing, not decoration.** ``Close``
        used to end the preview by clearing BOTH the rollback baseline and the
        "active" flag, which together stopped ``_refresh_live_replace`` from
        ever re-running. Forgetting only the baseline is not enough: with a
        non-empty Find field still reading as active, the next re-run (a filter
        change, ``run_live_replace``) would recompute the proposal from each
        row's Value and **overwrite a hand-edited New Value — permanently,
        because the baseline that used to restore it is gone.** That is exactly
        the silent-reversion failure this design must not have, so a successful
        ``replace_all`` marks the preview committed and any subsequent edit to
        the bar's fields re-arms it (see :meth:`run_live_replace`)."""
        return bool(self.find_field.text()) and not self._committed

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            # Return focus to the grid; the bar stays visible (FQ-017).
            self._on_escape()
            return
        super().keyPressEvent(event)

    # -- operations ---------------------------------------------------------

    def _clear_error(self) -> None:
        self.error_label.setText("")

    def _show_error(self, message: str) -> None:
        # Non-blocking: inline label only, never a modal.
        self.error_label.setText(message)
        self.status_label.setText("")

    def run_live_replace(self, *_args) -> None:
        """Recompute the live proposal from the current field state. Wired to
        every field's change signal, so it runs on each keystroke; it is also
        safe to call directly (the panel does, after the filter scope moves).

        ``*_args`` swallows whatever the emitting signal passes (the new text,
        the combo index, the checkbox state) — none of it is read, the fields
        are.

        A user-driven run **re-arms** a committed preview: touching a field says
        the pattern is being worked on again, so the new proposal becomes
        reversible once more (its baseline is whatever the committed values
        were). ``set_find_text``'s suspended writes deliberately do not re-arm —
        seeding Find-what on a focus gesture must not restart a preview."""
        if self._suspended:
            return
        self._committed = False
        self._clear_error()
        try:
            count = self._on_live_replace(
                self.find_field.text(),
                self.replace_field.text(),
                self.selected_mode(),
                self.match_case(),
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.status_label.setText(
            f"{count} row(s) proposed" if count else ""
        )

    def apply_filter(self) -> None:
        """Push the Find-what to the grid's whole-row find filter (explicit, on
        the button — see the class docstring on why filtering is not live).
        Catches the invalid-regex ValueError and shows it inline."""
        self._clear_error()
        try:
            self._on_filter(
                self.find_field.text(), self.selected_mode(), self.match_case()
            )
        except ValueError as exc:
            self._show_error(str(exc))

    def clear_filter(self) -> None:
        """Drop the grid's filters via the panel's single ``clear_all_filters``
        path. The Find field is left alone — it is the Replace pattern too, and
        emptying it would silently roll the live preview back."""
        self._clear_error()
        self._on_clear_filter()

    def replace_all(self) -> None:
        """Write the replacement into the New Value of every row in the selected
        scope, then **commit** the live preview (the panel forgets its rollback
        baseline, so those New Values become ordinary hand-editable proposals).

        This is the handoff the deleted Close button used to perform. It is the
        only way ``"in all project"`` ever takes effect. Invalid regex is
        reported inline and commits nothing."""
        self._clear_error()
        try:
            count = self._on_replace_all(
                self.find_field.text(),
                self.replace_field.text(),
                self.selected_mode(),
                self.match_case(),
                self.selected_scope() == "project",
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return
        # Only a SUCCESSFUL write ends the reversible phase.
        self._committed = True
        self.status_label.setText(f"{count} row(s) replaced")


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

        # Active-filter banner (BUG-020): the preset row-predicate filters
        # (filter_to_table / filter_to_table_details / filter_to_field) are
        # otherwise entirely invisible -- unlike header value filters (▼
        # indicator) and the find filter, a preset predicate has no on-screen
        # representation at all. This banner surfaces it: a short label built
        # alongside the predicate (see filter_to_* / set_row_predicate) plus a
        # "showing N of M" row count, with a Clear button wired to the single
        # clear_all_filters() path. Hidden whenever no preset predicate is
        # active.
        self._filter_banner_label = QLabel()
        self._filter_banner_label.setStyleSheet(
            f"font-weight: bold; color: {_FILTER_HEADER_FOREGROUND.name()};"
        )
        self._filter_banner_clear_button = QPushButton("Clear")
        self._filter_banner_clear_button.clicked.connect(self.clear_all_filters)
        self._filter_banner = QWidget()
        banner_row = QHBoxLayout(self._filter_banner)
        banner_row.setContentsMargins(0, 0, 0, 0)
        banner_row.addWidget(self._filter_banner_label)
        banner_row.addStretch(1)
        banner_row.addWidget(self._filter_banner_clear_button)
        self._filter_banner.setVisible(False)

        # The grid's own live Find/Replace bar (§13/§7's per-tab bar idiom).
        # Named `find_replace_bar` to match the sibling surfaces MainWindow's
        # _active_find_bar() already routes to (stage.find_replace_bar,
        # stage.xsd_find_replace_bar, ddl_editor_panel.find_replace_bar).
        # PERMANENTLY VISIBLE (FQ-017): the Caption Filter modal it duplicated is
        # gone, so there is no second surface and nothing to show or hide.
        self.find_replace_bar = CaptionFindReplaceBar(
            on_live_replace=self.live_replace_preview,
            on_filter=self.apply_find_filter,
            on_replace_all=self.replace_all_from_bar,
            on_clear_filter=self.clear_all_filters,
            on_escape=self.focus_grid,
            parent=self,
        )
        # Rows the live preview overwrote -> the New Value each had before it.
        # Restored (and re-derived) on every recompute, so the preview is a
        # replacement of itself rather than an accumulation. Emptied by
        # commit_live_replace, which Replace All calls (the bar has no Close
        # button to call it any more), and by emptying the Find field.
        self._live_replace_baseline: dict[int, str] = {}
        # Re-entrancy guard: writing New Values can move rows in and out of the
        # find filter, which must never recursively re-run the preview.
        self._live_replace_running = False

        layout = QVBoxLayout(self)
        layout.addWidget(self._filter_banner)
        layout.addWidget(self._table)
        layout.addWidget(self.find_replace_bar)
        layout.addLayout(button_row)

        # Shortcuts scoped to the table.
        QShortcut(QKeySequence.StandardKey.Copy, self._table, self.copy_selection)
        QShortcut(QKeySequence.StandardKey.Paste, self._table, self.paste_into_new_value)
        QShortcut(QKeySequence("Ctrl+G"), self._table, self.go_to_line_current)

        # Ctrl+F / Ctrl+R FOCUS the permanent bar's Find / Replace-with field
        # (FQ-017). They used to be window-scoped, mode-gated MainWindow
        # shortcuts opening the deleted Caption Filter modal; with the modal gone
        # the bar owns them, scoped to this panel and its children so they are
        # live wherever the caption grid or the bar has focus and inert
        # everywhere else. (Caption Mode disables the Edit-menu Find…/Replace…
        # actions, so there is no ambiguous-shortcut conflict.)
        self._focus_find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._focus_find_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._focus_find_shortcut.activated.connect(self.focus_find_replace_bar)
        self._focus_replace_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self._focus_replace_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._focus_replace_shortcut.activated.connect(self.focus_replace_field)

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

    def focus_grid(self) -> None:
        """Put focus back on the caption grid — what Escape in the permanent
        Find/Replace bar does instead of hiding it (FQ-017)."""
        self._table.setFocus()

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
        # Only reached when set_regex_filter returned normally (an invalid
        # regex propagates out before this), so the banner never advertises a
        # filter that was rejected. BUG-028. The live replace is re-scoped
        # BEFORE the banner refresh so the banner's "showing N of M" counts the
        # rows the user actually ends up looking at.
        self._refresh_live_replace()
        self._refresh_filter_banner()

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
        result into that row's New Value (non-destructive). Scope:
        ``in_selection=True`` = currently-visible/filtered rows (the bar's
        default ``"in filtered results"``); ``False`` = all source rows (``"in
        all project"``). Returns the number of rows changed. Raises ValueError on
        invalid regex.

        Note the parameter name is historical (the deleted modal scoped by grid
        *selection*); the only caller now scopes by *filter*."""
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

    # -- live replace bar (§13) ---------------------------------------------

    def focus_find_replace_bar(self) -> None:
        """``Ctrl+F`` / the context-menu entry: focus the permanently visible
        bar's Find field, seeding it from the currently active find pattern when
        it is empty (so Filter-then-Replace reuse still works). The bar is a
        plain child widget — never a modal, never ``.exec()``, and never
        hidden."""
        self.find_replace_bar.focus_find(self.current_filter_pattern())

    def focus_replace_field(self) -> None:
        """``Ctrl+R``: focus the permanently visible bar's Replace-with field."""
        self.find_replace_bar.focus_replace()

    def replace_all_from_bar(
        self, find: str, replacement: str, mode: str, case: bool, in_all_project: bool
    ) -> int:
        """The bar's Replace All: write the replacement into the New Value of
        every row in the chosen scope, then **commit** the live preview.

        The commit is the point of this method. ``commit_live_replace`` used to
        be reached only from the bar's Close button; with the bar permanent,
        Replace All is the explicit, deliberate write that ends the reversible
        phase — after it, the proposed New Values are ordinary hand-editable
        ones and a later re-run (a filter change, another keystroke) will NOT
        roll a hand edit back. The other release gesture is emptying the Find
        field, which rolls the preview back cleanly.

        Order matters: on an invalid regex ``replace_all_find`` raises before the
        commit, so a broken pattern leaves the reversible preview intact."""
        count = self.replace_all_find(
            find, replacement, mode, case, in_selection=not in_all_project
        )
        self.commit_live_replace()
        return count

    def live_replace_preview(
        self, find: str, replacement: str, mode: str, case: bool
    ) -> int:
        """Recompute the bar's live proposal and return the number of rows it
        proposes a new value for.

        Every run first **rolls back** the previous run (each touched row gets
        the New Value it held before the preview claimed it), then applies the
        fresh proposal on top — so the preview always reflects the pattern as
        it stands now, and never accumulates the debris of half-typed ones. An
        empty ``find`` therefore restores the grid exactly.

        **Scope is the currently-visible (filtered) rows.** The proposal is
        never written into a row the active filters hide: a live edit the user
        cannot see contradicts §13's visible-state discipline, and it matches
        the modal's default "In selection (filtered rows)" scope. The modal
        keeps the Global option — going project-wide stays an explicit,
        button-pressed gesture rather than something a keystroke can do.

        Raises ``ValueError`` on an invalid regex (the bar shows it inline);
        the rollback has already happened when it raises, so a broken pattern
        leaves no stale preview behind. The pattern is validated up front so a
        bad regex is reported even when the scope is empty."""
        if self._live_replace_running:
            return len(self._live_replace_baseline)
        self._live_replace_running = True
        try:
            if self._live_replace_baseline:
                self._model.set_new_values(dict(self._live_replace_baseline))
                self._live_replace_baseline = {}
            if not find:
                return 0
            # Compile-check before touching any row (mirrors set_regex_filter).
            matches("", find, mode, case)
            entries = self._model.entries()
            updates: dict[int, str] = {}
            for source_row in self._visible_source_rows():
                proposed = apply_find_replace(
                    entries[source_row].value, find, replacement, mode, case
                )
                if proposed is not None:
                    updates[source_row] = proposed
            self._live_replace_baseline = {
                row: self._model.new_value_at(row) for row in updates
            }
            self._model.set_new_values(updates)
            return len(updates)
        finally:
            self._live_replace_running = False

    def commit_live_replace(self) -> None:
        """Stop tracking the live preview: whatever it proposed becomes an
        ordinary, hand-editable New Value. It does not write anything, it only
        forgets the rollback baseline.

        Called by ``replace_all_from_bar`` (FQ-017). It used to be the bar's
        ``on_close``; the permanent bar has no Close button, so Replace All is
        the handoff from reversible preview to ordinary proposal."""
        self._live_replace_baseline = {}

    def _refresh_live_replace(self) -> None:
        """Re-run the live preview against the *new* filter scope. Called after
        every gesture that changes which rows are visible, so rows that just
        left the visible set get their previous New Value back and rows that
        just entered it pick the proposal up. A no-op when the bar is inactive
        (empty Find field) and nothing is currently previewed — which, after
        Replace All committed the baseline, is exactly the state that stops a
        filter change from reverting a hand-edited New Value."""
        if not self.find_replace_bar.is_active() and not self._live_replace_baseline:
            return
        self.find_replace_bar.run_live_replace()

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

    def unify_from_row(
        self, source_row: int, restrict_to: Sequence[int] | None = None
    ) -> None:
        """Set the New Value of every OTHER row sharing this row's
        ``(anchor, attribute)`` whose effective current value differs from the
        source row's target, to that target. The target is the source row's New
        Value if set, else its Value. A row's effective current value is its New
        Value if set, else its Value; rows already matching are left
        untouched.

        ``restrict_to`` (BUG-023), when given, limits which sibling rows are
        eligible for the update to that collection of source-model row
        indices (typically the currently-visible/filtered rows via
        ``_visible_source_rows()``) — "Filtered rows only" scope. ``None``
        (the default) keeps the original project-wide behavior."""
        if not (0 <= source_row < self._model.rowCount()):
            return
        entries = self._model.entries()
        source_entry = entries[source_row]
        source_new = self._model.new_value_at(source_row)
        target = source_new if source_new else source_entry.value
        key = (source_entry.anchor, source_entry.attribute)
        eligible_rows = range(len(entries)) if restrict_to is None else restrict_to
        updates: dict[int, str] = {}
        for row in eligible_rows:
            if row == source_row:
                continue
            entry = entries[row]
            if (entry.anchor, entry.attribute) != key:
                continue
            row_new = self._model.new_value_at(row)
            effective = row_new if row_new else entry.value
            if effective != target:
                updates[row] = target
        self._model.set_new_values(updates)

    def unify_current(self) -> None:
        """Unify the current row's inconsistent siblings. When a filter is
        currently active (BUG-023), first ask whether to restrict the unify to
        the filtered/visible rows or run it project-wide, via
        ``_confirm_unify_scope`` (monkeypatched in tests — never a live
        modal). When no filter is active, behavior is unchanged (no prompt,
        project-wide)."""
        source_row = self._current_source_row()
        if source_row is None:
            return
        if not self._proxy.is_any_filter_active():
            self.unify_from_row(source_row)
            return
        choice = self._confirm_unify_scope()
        if choice == "cancel":
            return
        if choice == "filtered":
            self.unify_from_row(source_row, restrict_to=self._visible_source_rows())
        else:  # "project"
            self.unify_from_row(source_row)

    def _confirm_unify_scope(self) -> str:
        """Ask the user whether Unify should apply to the filtered rows only
        or project-wide. Returns "filtered", "project", or "cancel". Split out
        (mirroring MainWindow's ``_confirm_close_xsd``) so tests can
        monkeypatch it instead of ever driving a real modal."""
        box = QMessageBox(self)
        box.setWindowTitle("Unify Scope")
        box.setText(
            "A filter is currently active. Apply Unify to the filtered rows "
            "only, or to the entire project?"
        )
        filtered_button = box.addButton(
            "Filtered rows only", QMessageBox.ButtonRole.AcceptRole
        )
        project_button = box.addButton(
            "Entire project", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is filtered_button:
            return "filtered"
        if clicked is project_button:
            return "project"
        return "cancel"

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
            on_apply=self._apply_header_value_filter,
            parent=self,
        )
        header = self._table.horizontalHeader()
        pos = header.mapToGlobal(header.rect().bottomLeft())
        popup.move(pos)
        popup.show()
        return popup

    def _apply_header_value_filter(self, column: int, allowed: set[str] | None) -> None:
        """The header popup's OK target: set the column's value filter, then
        re-scope the live replace preview to the rows that are now visible.
        Deliberately does NOT touch the active-filter banner — header value
        filters keep their own exclusive ▼ marker and stay out of it
        (BUG-020)."""
        self._proxy.set_value_filter(column, allowed)
        self._refresh_live_replace()

    # -- preset filters (Phase C.2) -----------------------------------------

    def filter_to_table(self, table_name: str) -> None:
        """Show only rows whose owning page/detail table is `table_name`."""
        label = f"Table = {table_name}"
        self._proxy.set_row_predicate(lambda e: e.table_name == table_name, label)
        self._refresh_live_replace()
        self._refresh_filter_banner()

    def filter_to_table_details(self, table_name: str) -> None:
        """Show only rows whose owning table is `table_name` AND that live
        within a <Detail> embed (so you see how a DB table is captioned across
        its Detail embeds)."""
        label = f"Table = {table_name}  (Detail embeds)"
        self._proxy.set_row_predicate(
            lambda e: e.table_name == table_name and e.in_detail, label
        )
        self._refresh_live_replace()
        self._refresh_filter_banner()

    def filter_to_field(self, field_name: str, table_name: str | None = None) -> None:
        """Show only rows whose column `field_name` matches (optionally also
        `table_name`), then SELECT + scroll to the first matching row so the
        specific column line is highlighted."""
        if table_name is None:
            label = f"Field = {field_name}"
            self._proxy.set_row_predicate(lambda e: e.field_name == field_name, label)
        else:
            label = f"Field = {field_name}  ·  Table = {table_name}"
            self._proxy.set_row_predicate(
                lambda e: e.field_name == field_name and e.table_name == table_name,
                label,
            )
        self._refresh_live_replace()
        self._select_first_visible_row()
        self._refresh_filter_banner()

    def _select_first_visible_row(self) -> None:
        """Select and scroll to the first row visible through the proxy.

        Drives the selection model directly rather than `QTableView.selectRow`,
        which interprets a *user gesture* via the process-global keyboard
        modifiers (`QGuiApplication.keyboardModifiers()`) -- if Shift happens
        to be latched (e.g. from an unrelated prior Ctrl+Shift+... action),
        `selectRow` builds an invalid anchor-relative range and silently
        selects nothing. See BUG-018."""
        if self._proxy.rowCount() == 0:
            return
        first = self._proxy.index(0, 0)
        last = self._proxy.index(0, self._proxy.columnCount() - 1)
        selection_model = self._table.selectionModel()
        selection_model.setCurrentIndex(
            first, QItemSelectionModel.SelectionFlag.NoUpdate
        )
        selection_model.select(
            QItemSelection(first, last),
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        self._table.scrollTo(first)

    def _source_row_to_proxy_row(self, source_row: int) -> int:
        """Proxy (visual) row index for a source-model row, or -1 if filtered
        out."""
        proxy_index = self._proxy.mapFromSource(self._model.index(source_row, 0))
        return proxy_index.row() if proxy_index.isValid() else -1

    def _proxy_row_to_source_row(self, proxy_row: int) -> int:
        """Source-model row index for a proxy (visual) row."""
        return self._proxy.mapToSource(self._proxy.index(proxy_row, 0)).row()

    # -- active-filter banner (BUG-020) --------------------------------------

    def _find_filter_descriptor(self) -> str:
        """Human-readable description of the active whole-row find filter, or
        "" when no find pattern is set (BUG-028).

        The find filter matches against every displayed column, so the scope is
        always stated as "all columns" -- unlike header value filters, it has
        no per-column header marker, making the banner its only surface.
        Non-default mode/case are named explicitly; a plain case-insensitive
        Normal search stays terse."""
        pattern = self._proxy.find_pattern()
        if not pattern:
            return ""
        qualifiers: list[str] = []
        mode = self._proxy.find_mode()
        if mode == "regular":
            qualifiers.append("regex")
        elif mode == "extended":
            qualifiers.append("extended")
        if self._proxy.find_case():
            qualifiers.append("case-sensitive")
        qualifiers.append("all columns")
        return f'Find "{pattern}" ({", ".join(qualifiers)})'

    def _refresh_filter_banner(self) -> None:
        """Show/hide the active-filter banner and refresh its text to reflect
        the current preset row-predicate label AND the whole-row find filter,
        plus visible/total row counts. Called after every preset filter setter,
        after apply_find_filter (BUG-028), and after clear_all_filters (the
        single path that can deactivate everything) so the banner is never out
        of sync with the proxy. Computed AFTER the proxy has already been
        invalidated by the caller so the "showing N of M" count reflects the
        new filters.

        Header value filters are deliberately NOT represented here -- they
        carry their own per-column header marker (BUG-020)."""
        descriptors = [
            d
            for d in (self._proxy.row_predicate_label(), self._find_filter_descriptor())
            if d
        ]
        if not descriptors:
            self._filter_banner.setVisible(False)
            return
        label = "  ·  ".join(descriptors)
        visible = self._proxy.rowCount()
        total = self._model.rowCount()
        self._filter_banner_label.setText(
            f"Filtered: {label} — showing {visible} of {total} rows"
        )
        self._filter_banner.setVisible(True)

    # -- clear all filters (Phase C.3) --------------------------------------

    def clear_all_filters(self) -> None:
        """Clear the find filter, every header value filter, and the preset row
        predicate; refresh the header indicators and hide the active-filter
        banner (this is the single path that hides it, BUG-020)."""
        self._proxy.set_regex_filter(
            "", self._proxy.find_mode(), self._proxy.find_case()
        )
        for column in list(self._proxy.filtered_columns()):
            self._proxy.set_value_filter(column, None)
        self._proxy.set_row_predicate(None)
        self._refresh_live_replace()
        self._refresh_filter_banner()

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
        menu.addSeparator()
        menu.addAction("Focus Find / Replace bar", self.focus_find_replace_bar)
        menu.addAction("Clear all filters", self.clear_all_filters)
        menu.exec(self._table.viewport().mapToGlobal(pos))
