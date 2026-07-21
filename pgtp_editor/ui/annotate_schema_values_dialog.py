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

"""AnnotateSchemaValuesDialog: the intern's two-pane labeling tool over
the shared per-user schema model
(pgtp_editor.schema_learning.model.Model).

Left pane: one row per enum-candidate ``(path, attribute)`` with an
editable **Kind** combo (Unclassified / Setting / Content). Right pane:
when the selected attribute is a *setting*, its observed values with an
editable **Label** each.

This module writes ONLY the `kind` and `labels` keys on each attribute
entry. `type`, `values`, `overflowed`, and `attr_seen_count` are owned by
the Schema Learning Engine sub-project
(pgtp_editor/schema_learning/model.py) and are never written here.
"""
from __future__ import annotations

from pgtp_editor.schema_learning.settings_index import (
    attribute_kind,
    is_enum_candidate,
)


def _build_attribute_rows(model):
    """One row per enum-candidate ``(path, attribute)`` in ``model``.

    Each row: ``{"path", "attribute", "kind", "num_values", "num_labeled"}``
    where ``kind`` is via ``attribute_kind`` (so unclassified attributes
    read as ``"unclassified"``), ``num_values`` is the count of observed
    values, and ``num_labeled`` is how many of those values already appear
    as keys in ``labels``. Content-kind attributes are still emitted as
    rows (they are filtered out later, not here). Sorted by
    ``(path, attribute)``.
    """
    rows = []
    for path in sorted(model.paths):
        attributes = model.paths[path]["attributes"]
        for attr_name in sorted(attributes):
            entry = attributes[attr_name]
            if not is_enum_candidate(entry):
                continue
            values = entry["values"]
            labels = entry.get("labels", {})
            num_labeled = sum(1 for value in values if value in labels)
            rows.append({
                "path": path,
                "attribute": attr_name,
                "kind": attribute_kind(entry),
                "num_values": len(values),
                "num_labeled": num_labeled,
            })
    return rows


def _filter_attribute_rows(rows, kind_filter, text):
    """Filter ``rows`` by ``kind_filter`` and ``text``.

    ``kind_filter`` is one of ``"all"`` / ``"unclassified"`` /
    ``"setting"`` / ``"content"``; ``"all"`` includes everything
    (content too). ``text`` matches ``path`` or ``attribute``
    case-insensitively.
    """
    lowered = text.lower()
    result = []
    for row in rows:
        if kind_filter != "all" and row["kind"] != kind_filter:
            continue
        if lowered and lowered not in row["path"].lower() and lowered not in row["attribute"].lower():
            continue
        result.append(row)
    return result


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path

# Left (attribute) table columns.
PATH_COLUMN = 0
ATTRIBUTE_COLUMN = 1
KIND_COLUMN = 2
NUM_VALUES_COLUMN = 3
NUM_LABELED_COLUMN = 4
_ATTRIBUTE_HEADERS = ["Element Path", "Attribute", "Kind", "#values", "#labeled"]

# Right (value) table columns.
VALUE_VALUE_COLUMN = 0
VALUE_LABEL_COLUMN = 1
_VALUE_HEADERS = ["Value", "Label"]

# Kind combo entries: display label paired with the stored kind string.
_KIND_CHOICES = [
    ("Unclassified", "unclassified"),
    ("Setting", "setting"),
    ("Content", "content"),
]
# Kind filter combo: display label paired with the filter key.
_KIND_FILTERS = [
    ("Unclassified + Settings", None),  # default: excludes content
    ("All", "all"),
    ("Unclassified", "unclassified"),
    ("Settings", "setting"),
    ("Content", "content"),
]

_EMPTY_STATE_TEXT = (
    "No schema data yet. Open a .pgtp file to begin learning the schema, "
    "then come back here to annotate it."
)
_PLACEHOLDER_TEXT = "Mark this attribute as a Setting to label its values."


class AnnotateSchemaValuesDialog(QDialog):
    def __init__(self, parent=None, schema_storage_dir=None):
        super().__init__(parent)
        self.setWindowTitle("Annotate Schema Values")
        self._populating = False
        self._model = None
        self._model_path = None
        self._all_rows = []
        # Rows currently shown in the left table, in display order — maps
        # a left-table row index to its (path, attribute) dict.
        self._visible_rows = []

        self.empty_state_label = QLabel(_EMPTY_STATE_TEXT)
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setVisible(False)

        # --- filter bar -----------------------------------------------
        self.kind_filter_combo = QComboBox()
        for display, _key in _KIND_FILTERS:
            self.kind_filter_combo.addItem(display)
        self.kind_filter_combo.setCurrentIndex(0)  # Unclassified + Settings
        self.kind_filter_combo.currentIndexChanged.connect(self._refresh_visible_rows)

        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filter by element path or attribute...")
        self.filter_box.textChanged.connect(self._refresh_visible_rows)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Show:"))
        filter_row.addWidget(self.kind_filter_combo)
        filter_row.addWidget(QLabel("Filter:"))
        filter_row.addWidget(self.filter_box)

        # --- left pane: attribute table -------------------------------
        self.attribute_table = QTableWidget(0, len(_ATTRIBUTE_HEADERS))
        self.attribute_table.setHorizontalHeaderLabels(_ATTRIBUTE_HEADERS)
        self.attribute_table.setSortingEnabled(True)
        self.attribute_table.itemSelectionChanged.connect(self._on_attribute_selection_changed)

        # --- right pane: value table + placeholder --------------------
        self.value_placeholder = QLabel(_PLACEHOLDER_TEXT)
        self.value_placeholder.setWordWrap(True)
        self.value_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_table = QTableWidget(0, len(_VALUE_HEADERS))
        self.value_table.setHorizontalHeaderLabels(_VALUE_HEADERS)
        self.value_table.itemChanged.connect(self._on_value_item_changed)
        self.value_table.setVisible(False)

        right_pane = QWidget()
        right_layout = QVBoxLayout(right_pane)
        right_layout.addWidget(self.value_placeholder)
        right_layout.addWidget(self.value_table)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.attribute_table)
        self.splitter.addWidget(right_pane)

        layout = QVBoxLayout(self)
        layout.addWidget(self.empty_state_label)
        layout.addLayout(filter_row)
        layout.addWidget(self.splitter)

        self._filter_row_widgets = [self.kind_filter_combo, self.filter_box]

        model_path = schema_model_path(schema_storage_dir)
        if not model_path.exists():
            self._show_empty_state()
            return

        try:
            model = Model.load(model_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Failed to Load Schema Model",
                f"Could not load '{model_path}':\n\n{exc}",
            )
            self._show_empty_state()
            return

        self._load_model_and_populate(model, model_path)

    def _show_empty_state(self):
        self.empty_state_label.setVisible(True)
        self.splitter.setVisible(False)
        for widget in self._filter_row_widgets:
            widget.setVisible(False)

    @classmethod
    def _for_testing(cls, model, model_path, parent=None):
        """Constructs the dialog directly against an in-memory Model and a
        model_path, bypassing disk-based load and any modal — used by
        tests that drive the dialog's tables/filters/edits against a
        synthetic Model."""
        dialog = cls(parent)
        dialog._load_model_and_populate(model, model_path)
        return dialog

    def _load_model_and_populate(self, model, model_path):
        self._model = model
        self._model_path = model_path
        self._all_rows = _build_attribute_rows(model)
        self._refresh_visible_rows()

    # --- filter / left-table population -------------------------------

    def _current_kind_filter(self):
        _display, key = _KIND_FILTERS[self.kind_filter_combo.currentIndex()]
        return key

    def set_kind_filter(self, key):
        """Programmatic setter used by tests. ``key`` is one of ``None``
        (the default: unclassified+settings), ``"all"``, ``"unclassified"``,
        ``"setting"``, ``"content"``."""
        for index, (_display, filter_key) in enumerate(_KIND_FILTERS):
            if filter_key == key:
                self.kind_filter_combo.setCurrentIndex(index)
                return
        raise ValueError(f"unknown kind filter: {key!r}")

    def _visible_attribute_rows(self):
        key = self._current_kind_filter()
        text = self.filter_box.text()
        if key is None:
            # Default view: unclassified + settings (content hidden).
            rows = _filter_attribute_rows(self._all_rows, "all", text)
            return [r for r in rows if r["kind"] != "content"]
        return _filter_attribute_rows(self._all_rows, key, text)

    def _refresh_visible_rows(self):
        self._populate_attribute_table(self._visible_attribute_rows())

    def _populate_attribute_table(self, rows):
        self._populating = True
        was_sorting_enabled = self.attribute_table.isSortingEnabled()
        self.attribute_table.setSortingEnabled(False)
        try:
            self._visible_rows = list(rows)
            self.attribute_table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                self._set_readonly_item(row_index, PATH_COLUMN, row["path"])
                self._set_readonly_item(row_index, ATTRIBUTE_COLUMN, row["attribute"])
                self._set_readonly_item(row_index, NUM_VALUES_COLUMN, str(row["num_values"]))
                self._set_readonly_item(row_index, NUM_LABELED_COLUMN, str(row["num_labeled"]))

                # Kind cell is a placeholder item plus a combo cell widget.
                self.attribute_table.setItem(row_index, KIND_COLUMN, QTableWidgetItem())
                combo = QComboBox()
                for display, _key in _KIND_CHOICES:
                    combo.addItem(display)
                combo.setCurrentIndex(self._kind_choice_index(row["kind"]))
                # Bind the (path, attribute) identity onto the combo so the
                # write-back handler resolves the acting row by identity —
                # NOT by a captured visual index, which goes stale the moment
                # the user sorts the table (QTableWidget moves cell widgets to
                # new visual rows but our index would not follow).
                combo.setProperty("row_key", (row["path"], row["attribute"]))
                combo.currentIndexChanged.connect(self._on_kind_combo_changed)
                self.attribute_table.setCellWidget(row_index, KIND_COLUMN, combo)
        finally:
            self.attribute_table.setSortingEnabled(was_sorting_enabled)
            self._populating = False
        # Reset the right pane after a repopulation (selection cleared).
        self._show_value_placeholder()

    def _set_readonly_item(self, row_index, column, text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.attribute_table.setItem(row_index, column, item)

    @staticmethod
    def _kind_choice_index(kind):
        for index, (_display, key) in enumerate(_KIND_CHOICES):
            if key == kind:
                return index
        return 0

    # --- kind write-back ----------------------------------------------

    def set_row_kind(self, row_index, kind):
        """Programmatic entry point (also used by tests) that sets the
        kind for the attribute at ``row_index`` and persists. ``kind`` is
        one of ``"unclassified"`` / ``"setting"`` / ``"content"``."""
        combo = self.attribute_table.cellWidget(row_index, KIND_COLUMN)
        target = self._kind_choice_index(kind)
        if combo.currentIndex() == target:
            # Combo already at the target; apply the write directly using the
            # combo's own identity (never a visual index).
            path, attribute = combo.property("row_key")
            self._apply_kind(path, attribute, kind)
        else:
            combo.setCurrentIndex(target)  # triggers _on_kind_combo_changed

    def _on_kind_combo_changed(self, _index):
        if self._populating:
            return
        combo = self.sender()
        if combo is None:
            return
        path, attribute = combo.property("row_key")
        _display, kind = _KIND_CHOICES[combo.currentIndex()]
        self._apply_kind(path, attribute, kind)

    def _apply_kind(self, path, attribute, kind):
        entry = self._model.paths[path]["attributes"][attribute]
        if kind == "unclassified":
            entry.pop("kind", None)
        else:
            entry["kind"] = kind
        # Keep both the visible and master row lists in sync so re-filtering
        # reflects the new kind.
        for candidate in self._all_rows:
            if candidate["path"] == path and candidate["attribute"] == attribute:
                candidate["kind"] = kind
                break
        for candidate in self._visible_rows:
            if candidate["path"] == path and candidate["attribute"] == attribute:
                candidate["kind"] = kind
                break
        self._model.save(self._model_path)
        # Re-filter + repopulate so a row whose new kind falls outside the
        # active filter (e.g. Content in the default content-hidden view)
        # leaves the list immediately. Repopulation resets the right pane to
        # the placeholder, which is the sensible state when the previously
        # selected row may have just disappeared.
        self._refresh_visible_rows()

    # --- selection / right pane ---------------------------------------

    def select_attribute_row(self, row_index):
        """Programmatic selection (also used by tests)."""
        self.attribute_table.selectRow(row_index)
        # selectRow emits itemSelectionChanged, but call directly too so
        # the right pane updates deterministically in headless tests.
        self._on_attribute_selection_changed()

    def _selected_row_index(self):
        rows = self.attribute_table.selectionModel().selectedRows()
        if rows:
            return rows[0].row()
        current = self.attribute_table.currentRow()
        return current if current >= 0 else None

    def _on_attribute_selection_changed(self):
        row_index = self._selected_row_index()
        if row_index is None or row_index >= len(self._visible_rows):
            self._show_value_placeholder()
            return
        self._show_values_for_row(row_index)

    def _show_value_placeholder(self):
        self._populating = True
        try:
            self.value_table.setRowCount(0)
        finally:
            self._populating = False
        self.value_table.setVisible(False)
        self.value_placeholder.setVisible(True)

    def _show_values_for_row(self, row_index):
        row = self._visible_rows[row_index]
        if row["kind"] != "setting":
            self._show_value_placeholder()
            return
        entry = self._model.paths[row["path"]]["attributes"][row["attribute"]]
        values = sorted(entry["values"])
        labels = entry.get("labels", {})

        self._populating = True
        try:
            self.value_table.setRowCount(len(values))
            for i, value in enumerate(values):
                value_item = QTableWidgetItem(value)
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.value_table.setItem(i, VALUE_VALUE_COLUMN, value_item)

                label_item = QTableWidgetItem(labels.get(value, ""))
                label_item.setFlags(label_item.flags() | Qt.ItemFlag.ItemIsEditable)
                self.value_table.setItem(i, VALUE_LABEL_COLUMN, label_item)
        finally:
            self._populating = False

        self.value_placeholder.setVisible(False)
        self.value_table.setVisible(True)
        # Remember which attribute the value table currently reflects.
        self._current_value_path = row["path"]
        self._current_value_attribute = row["attribute"]

    def _on_value_item_changed(self, item):
        if self._populating or item.column() != VALUE_LABEL_COLUMN:
            return
        value = self.value_table.item(item.row(), VALUE_VALUE_COLUMN).text()
        new_label = item.text()
        path = self._current_value_path
        attribute = self._current_value_attribute
        entry = self._model.paths[path]["attributes"][attribute]
        entry.setdefault("labels", {})
        if new_label:
            entry["labels"][value] = new_label
        else:
            entry["labels"].pop(value, None)
        self._model.save(self._model_path)
        self._refresh_labeled_count(path, attribute)

    def _refresh_labeled_count(self, path, attribute):
        """Recompute the ``#labeled`` count for ``(path, attribute)`` and
        update both the row model and the left-table cell in place so the
        left pane stays accurate without a full re-filter."""
        entry = self._model.paths[path]["attributes"][attribute]
        values = entry.get("values") or []
        labels = entry.get("labels", {})
        num_labeled = sum(1 for value in values if value in labels)
        for candidate in self._all_rows:
            if candidate["path"] == path and candidate["attribute"] == attribute:
                candidate["num_labeled"] = num_labeled
                break
        for candidate in self._visible_rows:
            if candidate["path"] == path and candidate["attribute"] == attribute:
                candidate["num_labeled"] = num_labeled
                break
        # Locate the cell by its visible path/attribute text — the visual row
        # order may differ from ``_visible_rows`` after the user sorts.
        for visual_row in range(self.attribute_table.rowCount()):
            path_item = self.attribute_table.item(visual_row, PATH_COLUMN)
            attr_item = self.attribute_table.item(visual_row, ATTRIBUTE_COLUMN)
            if (
                path_item is not None
                and attr_item is not None
                and path_item.text() == path
                and attr_item.text() == attribute
            ):
                self._set_readonly_item(visual_row, NUM_LABELED_COLUMN, str(num_labeled))
                break
