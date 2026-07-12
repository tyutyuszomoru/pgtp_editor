"""AnnotateSchemaValuesDialog: lets a person browse every learned
(path, attribute, value) triple in the shared per-user schema model
(pgtp_editor.schema_learning.model.Model) and attach a human-readable
label to each observed value. See
docs/superpowers/specs/2026-07-12-pgtp-editor-annotate-schema-values-ui-design.md.

This module only ever reads/writes the `labels` dict on each attribute
entry — it never touches `values`, `type`, `overflowed`, or
`attr_seen_count`, which are owned by the Schema Learning Engine
sub-project (pgtp_editor/schema_learning/model.py).
"""
from __future__ import annotations


def _build_rows(model):
    """Flattens `model.paths` into one row per labelable (path, attribute,
    value) triple. A row is only generated for an attribute entry that is
    still a genuine enum candidate (`overflowed is False` and `values` is
    a non-empty list) and whose `type` is not `"boolean"` (see design spec
    §3.5 for the reasoning behind both exclusions).
    """
    rows = []
    for path in sorted(model.paths):
        attributes = model.paths[path]["attributes"]
        for attr_name in sorted(attributes):
            entry = attributes[attr_name]
            if entry["overflowed"] or not entry["values"]:
                continue
            if entry["type"] == "boolean":
                continue
            labels = entry.get("labels", {})
            for value in sorted(entry["values"]):
                rows.append({
                    "path": path,
                    "attribute": attr_name,
                    "value": value,
                    "label": labels.get(value, ""),
                })
    return rows


def _apply_filters(rows, text_filter, unlabeled_only):
    """Re-run on every keystroke in the text filter box and every toggle
    of the "Show only unlabeled" checkbox. `text_filter` matches
    case-insensitively against `path` and `attribute` only — not `value`
    or `label` (see design spec §4.2: matching against values too would
    risk false-positive matches when a value string happens to contain
    the filter text). `unlabeled_only` keeps rows where `label == ""`.
    """
    lowered = text_filter.lower()
    result = []
    for row in rows:
        if lowered and lowered not in row["path"].lower() and lowered not in row["attribute"].lower():
            continue
        if unlabeled_only and row["label"] != "":
            continue
        result.append(row)
    return result


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

PATH_COLUMN = 0
ATTRIBUTE_COLUMN = 1
VALUE_COLUMN = 2
LABEL_COLUMN = 3
_COLUMN_HEADERS = ["Element Path", "Attribute", "Value", "Label"]
_ROW_DATA_ROLE = Qt.ItemDataRole.UserRole


class AnnotateSchemaValuesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Annotate Schema Values")
        self._populating = False
        self._model = None
        self._model_path = None
        self._all_rows = []

        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filter by element path or attribute...")
        self.filter_box.textChanged.connect(self._refresh_visible_rows)

        self.unlabeled_only_checkbox = QCheckBox("Show only unlabeled")
        self.unlabeled_only_checkbox.setChecked(True)
        self.unlabeled_only_checkbox.toggled.connect(self._refresh_visible_rows)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        filter_row.addWidget(self.filter_box)
        filter_row.addWidget(self.unlabeled_only_checkbox)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(_COLUMN_HEADERS)
        self.table.setSortingEnabled(True)
        self.table.itemChanged.connect(self._on_item_changed)

        layout = QVBoxLayout(self)
        layout.addLayout(filter_row)
        layout.addWidget(self.table)

    @classmethod
    def _for_testing(cls, model, model_path, parent=None):
        """Constructs the dialog directly against an in-memory Model and a
        model_path, bypassing disk I/O — used by tests that want to drive
        the dialog's table/filter/edit behavior against a synthetic Model
        without writing a real schema_model.json first. The real
        production path (loading from disk, including the empty-state and
        malformed-JSON cases) is added in a later task."""
        dialog = cls(parent)
        dialog._load_model_and_populate(model, model_path)
        return dialog

    def _load_model_and_populate(self, model, model_path):
        self._model = model
        self._model_path = model_path
        self._all_rows = _build_rows(model)
        self._refresh_visible_rows()

    def _refresh_visible_rows(self):
        visible_rows = _apply_filters(
            self._all_rows,
            text_filter=self.filter_box.text(),
            unlabeled_only=self.unlabeled_only_checkbox.isChecked(),
        )
        self._populate_table(visible_rows)

    def _populate_table(self, rows):
        self._populating = True
        # Sorting must be disabled while rows are being inserted:
        # QTableWidget re-sorts after every setItem() call when sorting is
        # enabled, which reorders not-yet-fully-populated rows mid-loop and
        # leaves stale/None items behind. Restore the previous sorting
        # state once population is complete.
        was_sorting_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        try:
            self.table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                path_item = QTableWidgetItem(row["path"])
                path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_index, PATH_COLUMN, path_item)

                attribute_item = QTableWidgetItem(row["attribute"])
                attribute_item.setFlags(attribute_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_index, ATTRIBUTE_COLUMN, attribute_item)

                value_item = QTableWidgetItem(row["value"])
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_index, VALUE_COLUMN, value_item)

                label_item = QTableWidgetItem(row["label"])
                label_item.setFlags(label_item.flags() | Qt.ItemFlag.ItemIsEditable)
                label_item.setData(_ROW_DATA_ROLE, row)
                self.table.setItem(row_index, LABEL_COLUMN, label_item)
        finally:
            self.table.setSortingEnabled(was_sorting_enabled)
            self._populating = False

    def _on_item_changed(self, item):
        if self._populating or item.column() != LABEL_COLUMN:
            return

        row_key = item.data(_ROW_DATA_ROLE)
        path = row_key["path"]
        attr = row_key["attribute"]
        value = row_key["value"]
        new_label = item.text()

        entry = self._model.paths[path]["attributes"][attr]
        entry.setdefault("labels", {})
        if new_label:
            entry["labels"][value] = new_label
        else:
            entry["labels"].pop(value, None)

        # item.data() round-trips the row dict through QVariant, which
        # deep-copies it — so it is not the same object as the dict held
        # in self._all_rows. Look up the matching row there by identity
        # key (path, attribute, value) and update it in place so that
        # subsequent filter toggles see the new label without needing to
        # rebuild self._all_rows from the model.
        for candidate in self._all_rows:
            if (
                candidate["path"] == path
                and candidate["attribute"] == attr
                and candidate["value"] == value
            ):
                candidate["label"] = new_label
                break

        self._model.save(self._model_path)
