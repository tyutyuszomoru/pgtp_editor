# Annotate Schema Values UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Annotate Schema Values UI sub-project: a new `AnnotateSchemaValuesDialog` reachable from a new top-level **Schema** menu, letting a person browse every learned (path, attribute, value) triple in the shared per-user schema model and attach a human-readable label to each one, with inline editing and autosave.

**Architecture:** A new Qt-free module-level function `_build_rows(model)` in `pgtp_editor/ui/annotate_schema_values_dialog.py` flattens a `schema_learning.model.Model`'s `paths` dict into one row per labelable (path, attribute, value) triple, excluding overflowed and boolean-typed attributes. `AnnotateSchemaValuesDialog(QDialog)` wraps a `QTableWidget` (four columns: Element Path, Attribute, Value, Label) driven by that function's output, with a text filter box and a "Show only unlabeled" checkbox (default checked) that both re-run `_apply_filters`. Editing a Label cell fires `_on_item_changed`, which writes into the in-memory `Model`'s `labels` dict and calls `model.save(...)` immediately (autosave), guarded by a `self._populating` flag so programmatic table population never triggers a spurious save. `main_window.py` gains `_build_schema_menu()` (wired into `_build_menu_bar()` between `_build_diff_merge_menu()` and `_build_tools_menu()`) and `_open_annotate_schema_values()`, with no dependency on `self._current_project`.

**Tech Stack:** Python 3.10+, PySide6 (`QDialog`, `QTableWidget`, `QLineEdit`, `QCheckBox`, `QMessageBox`), the already-implemented `pgtp_editor.schema_learning.model.Model` and `pgtp_editor.schema_learning.storage.schema_model_path`, pytest + pytest-qt.

---

## Before you start

- Work in this worktree, on branch `worktree-pgtp-editor-combined`, exactly as already checked out — do not create a new worktree or branch.
- Run tests with `pytest` from the repo root.
- Commit after every task (not just at the end) — this plan is written so each task leaves the repo in a fully passing state.

**Reconciliation with the design spec (read this before Task 6):** The design spec's §4.2 sketches a dialog-local `_schema_model_path()` helper (`QStandardPaths.writableLocation(...)` + `os.path.join(..., "schema_model.json")`), with a note that if the Schema Learning Engine sub-project (sub-project A) exposes a shared helper, this dialog should use that helper instead of re-deriving the path. Sub-project A is now fully implemented and merged into this worktree, and it does expose exactly that helper:

```python
# pgtp_editor/schema_learning/storage.py (already implemented, confirmed by reading it)
def schema_model_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _MODEL_FILENAME
```

This returns a `pathlib.Path` (not a string), and accepts an optional `base_dir` override — the same override mechanism `MainWindow.__init__(self, schema_storage_dir: Path | None = None)` already uses in `pgtp_editor/ui/main_window.py` so tests can redirect storage to a `tmp_path` instead of the real per-user `AppDataLocation`. Every task below therefore has the dialog **import and call `schema_model_path` from `pgtp_editor.schema_learning.storage` directly** — there is no second, dialog-local path-resolution function anywhere in this plan. `AnnotateSchemaValuesDialog.__init__` accepts an optional `schema_storage_dir: Path | None = None` parameter (mirroring `MainWindow`'s own parameter name and default) purely so tests can pass an isolated `tmp_path`; `_open_annotate_schema_values()` in `main_window.py` forwards `self._schema_storage_dir` to the dialog it constructs, so the whole path stays test-isolatable end to end without ever touching the real user's AppData directory.

---

### Task 1: `_build_rows` — non-overflowed, non-boolean attribute produces one row per value

**Files:**
- Create: `pgtp_editor/ui/annotate_schema_values_dialog.py`
- Test: `tests/ui/test_annotate_schema_values_dialog.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_annotate_schema_values_dialog.py
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.ui.annotate_schema_values_dialog import _build_rows


def _seed_enum_attribute(model, path, attr_name, values, attr_type="integer", labels=None):
    """Directly builds a Model.paths[...] ["attributes"][...] entry shaped
    exactly like Model.merge_element would produce for a non-overflowed,
    non-secret attribute — without going through merge_element/ingestion,
    keeping this sub-project's tests independent of sub-project A's own
    test suite (per design spec §5's stated dependency boundary)."""
    entry, _ = model._get_or_create_path(path)
    entry["attributes"][attr_name] = {
        "type": attr_type,
        "values": list(values),
        "overflowed": False,
        "attr_seen_count": len(values),
        "labels": dict(labels or {}),
    }


def test_build_rows_produces_one_row_per_distinct_value():
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1", "2", "3"])

    rows = _build_rows(model)

    assert len(rows) == 3
    values = sorted(row["value"] for row in rows)
    assert values == ["1", "2", "3"]
    for row in rows:
        assert row["path"] == "Project/Page"
        assert row["attribute"] == "viewAbilityMode"
        assert row["label"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.ui.annotate_schema_values_dialog'`

- [ ] **Step 3: Write minimal implementation**

```python
# pgtp_editor/ui/annotate_schema_values_dialog.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/annotate_schema_values_dialog.py tests/ui/test_annotate_schema_values_dialog.py
git commit -m "feat(ui): add _build_rows for Annotate Schema Values dialog"
```

---

### Task 2: `_build_rows` — overflowed and boolean attributes excluded, labels reflected

**Files:**
- Modify: `tests/ui/test_annotate_schema_values_dialog.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_annotate_schema_values_dialog.py`:

```python
def test_build_rows_excludes_overflowed_attribute():
    model = Model()
    entry, _ = model._get_or_create_path("Project/Page")
    entry["attributes"]["freeform"] = {
        "type": "string",
        "values": None,
        "overflowed": True,
        "attr_seen_count": 11,
        "labels": {},
    }

    rows = _build_rows(model)

    assert rows == []


def test_build_rows_excludes_boolean_attribute_even_when_non_overflowed():
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "isVisible", ["true", "false"], attr_type="boolean")

    rows = _build_rows(model)

    assert rows == []


def test_build_rows_excludes_attribute_with_empty_values_list():
    model = Model()
    entry, _ = model._get_or_create_path("Project/Page")
    entry["attributes"]["neverSeen"] = {
        "type": "string",
        "values": [],
        "overflowed": False,
        "attr_seen_count": 0,
        "labels": {},
    }

    rows = _build_rows(model)

    assert rows == []


def test_build_rows_reflects_existing_labels_per_value():
    model = Model()
    _seed_enum_attribute(
        model, "Project/Page", "viewAbilityMode", ["1", "2", "3"],
        labels={"3": "Modal window"},
    )

    rows = _build_rows(model)

    by_value = {row["value"]: row["label"] for row in rows}
    assert by_value == {"1": "", "2": "", "3": "Modal window"}


def test_build_rows_defaults_missing_labels_key_to_empty_dict():
    model = Model()
    entry, _ = model._get_or_create_path("Project/Page")
    entry["attributes"]["legacy"] = {
        "type": "integer",
        "values": ["1"],
        "overflowed": False,
        "attr_seen_count": 1,
        # No "labels" key at all — simulates a schema_model.json written
        # before the Schema Learning Engine sub-project's `labels` field
        # landed. _build_rows must not raise KeyError here.
    }

    rows = _build_rows(model)

    assert rows == [{
        "path": "Project/Page",
        "attribute": "legacy",
        "value": "1",
        "label": "",
    }]


def test_build_rows_sorts_by_path_then_attribute_then_value():
    model = Model()
    _seed_enum_attribute(model, "Z/Path", "b", ["2", "1"])
    _seed_enum_attribute(model, "A/Path", "z", ["9"])
    _seed_enum_attribute(model, "A/Path", "a", ["1"])

    rows = _build_rows(model)

    keys = [(row["path"], row["attribute"], row["value"]) for row in rows]
    assert keys == [
        ("A/Path", "a", "1"),
        ("A/Path", "z", "9"),
        ("Z/Path", "b", "1"),
        ("Z/Path", "b", "2"),
    ]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: PASS (7 passed) — Task 1's implementation already handles every one of these cases (the `overflowed`/`not values`/`boolean` guards, `.get("labels", {})`, and the `sorted(...)` calls at each level); this task locks each behavior in with its own explicit test.

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_annotate_schema_values_dialog.py
git commit -m "test(ui): cover _build_rows exclusions, label reflection, and sort order"
```

---

### Task 3: `_apply_filters` — text filter against path/attribute only

**Files:**
- Modify: `pgtp_editor/ui/annotate_schema_values_dialog.py`
- Modify: `tests/ui/test_annotate_schema_values_dialog.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_annotate_schema_values_dialog.py`:

```python
from pgtp_editor.ui.annotate_schema_values_dialog import _apply_filters


def test_apply_filters_no_text_no_unlabeled_only_returns_all_rows():
    rows = [
        {"path": "A", "attribute": "x", "value": "1", "label": ""},
        {"path": "B", "attribute": "y", "value": "2", "label": "Two"},
    ]

    result = _apply_filters(rows, text_filter="", unlabeled_only=False)

    assert result == rows


def test_apply_filters_text_matches_path_case_insensitively():
    rows = [
        {"path": "Project/AbilityMode", "attribute": "x", "value": "1", "label": ""},
        {"path": "Project/Other", "attribute": "y", "value": "2", "label": ""},
    ]

    result = _apply_filters(rows, text_filter="abilitymode", unlabeled_only=False)

    assert result == [rows[0]]


def test_apply_filters_text_matches_attribute_case_insensitively():
    rows = [
        {"path": "A", "attribute": "viewAbilityMode", "value": "1", "label": ""},
        {"path": "A", "attribute": "otherAttr", "value": "2", "label": ""},
    ]

    result = _apply_filters(rows, text_filter="ABILITYMODE", unlabeled_only=False)

    assert result == [rows[0]]


def test_apply_filters_text_does_not_match_value_or_label_content():
    rows = [
        {"path": "A", "attribute": "x", "value": "3", "label": ""},
        {"path": "B", "attribute": "y", "value": "9", "label": "value is 3 here"},
    ]

    result = _apply_filters(rows, text_filter="3", unlabeled_only=False)

    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: FAIL with `ImportError: cannot import name '_apply_filters'`

- [ ] **Step 3: Write minimal implementation**

Append to `pgtp_editor/ui/annotate_schema_values_dialog.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/annotate_schema_values_dialog.py tests/ui/test_annotate_schema_values_dialog.py
git commit -m "feat(ui): add _apply_filters text/unlabeled-only filtering logic"
```

---

### Task 4: `_apply_filters` — "Show only unlabeled" behavior

**Files:**
- Modify: `tests/ui/test_annotate_schema_values_dialog.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_annotate_schema_values_dialog.py`:

```python
def test_apply_filters_unlabeled_only_hides_labeled_rows():
    rows = [
        {"path": "A", "attribute": "x", "value": "1", "label": ""},
        {"path": "A", "attribute": "x", "value": "2", "label": "Two"},
    ]

    result = _apply_filters(rows, text_filter="", unlabeled_only=True)

    assert result == [rows[0]]


def test_apply_filters_unlabeled_only_false_shows_labeled_rows_too():
    rows = [
        {"path": "A", "attribute": "x", "value": "1", "label": ""},
        {"path": "A", "attribute": "x", "value": "2", "label": "Two"},
    ]

    result = _apply_filters(rows, text_filter="", unlabeled_only=False)

    assert result == rows


def test_apply_filters_text_and_unlabeled_only_combine_with_and_semantics():
    rows = [
        {"path": "AbilityMode/A", "attribute": "x", "value": "1", "label": ""},
        {"path": "AbilityMode/A", "attribute": "x", "value": "2", "label": "Labeled"},
        {"path": "Other/B", "attribute": "y", "value": "3", "label": ""},
    ]

    result = _apply_filters(rows, text_filter="AbilityMode", unlabeled_only=True)

    assert result == [rows[0]]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: PASS (14 passed) — Task 3's implementation already ANDs the two conditions together; this task locks in the "Show only unlabeled" behavior and their combination with explicit tests.

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_annotate_schema_values_dialog.py
git commit -m "test(ui): cover _apply_filters unlabeled-only and combined filtering"
```

---

### Task 5: `AnnotateSchemaValuesDialog` — table population from `_build_rows`

**Files:**
- Modify: `pgtp_editor/ui/annotate_schema_values_dialog.py`
- Modify: `tests/ui/test_annotate_schema_values_dialog.py`

This task builds the dialog's constructor and its table-population path, deferring text/unlabeled filtering wiring (Task 6) and autosave (Task 7) to later tasks. To keep this task testable in isolation, the dialog is constructed directly against a `Model` instance and a `model_path` (rather than loading from disk), via a small `_build_from_model` construction path; Task 8 adds the disk-loading constructor path used by the real menu action.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_annotate_schema_values_dialog.py`:

```python
from pgtp_editor.ui.annotate_schema_values_dialog import (
    ATTRIBUTE_COLUMN,
    LABEL_COLUMN,
    PATH_COLUMN,
    VALUE_COLUMN,
    AnnotateSchemaValuesDialog,
)


def _dialog_with_model(qtbot, model, tmp_path):
    dialog = AnnotateSchemaValuesDialog._for_testing(model, tmp_path / "schema_model.json")
    qtbot.addWidget(dialog)
    return dialog


def test_dialog_table_has_four_columns_with_expected_headers(qtbot, tmp_path):
    model = Model()
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    assert dialog.table.columnCount() == 4
    headers = [dialog.table.horizontalHeaderItem(i).text() for i in range(4)]
    assert headers == ["Element Path", "Attribute", "Value", "Label"]


def test_dialog_table_populates_one_row_per_value(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1", "2", "3"])
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    assert dialog.table.rowCount() == 3
    values = sorted(dialog.table.item(row, VALUE_COLUMN).text() for row in range(3))
    assert values == ["1", "2", "3"]


def test_dialog_table_cells_show_path_attribute_value_label(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(
        model, "Project/Page", "viewAbilityMode", ["3"], labels={"3": "Modal window"},
    )
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    assert dialog.table.item(0, PATH_COLUMN).text() == "Project/Page"
    assert dialog.table.item(0, ATTRIBUTE_COLUMN).text() == "viewAbilityMode"
    assert dialog.table.item(0, VALUE_COLUMN).text() == "3"
    assert dialog.table.item(0, LABEL_COLUMN).text() == "Modal window"


def test_dialog_table_sorting_is_enabled(qtbot, tmp_path):
    model = Model()
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    assert dialog.table.isSortingEnabled() is True


def test_dialog_only_label_column_is_editable(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1"])
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    assert not bool(dialog.table.item(0, PATH_COLUMN).flags() & Qt.ItemFlag.ItemIsEditable)
    assert not bool(dialog.table.item(0, ATTRIBUTE_COLUMN).flags() & Qt.ItemFlag.ItemIsEditable)
    assert not bool(dialog.table.item(0, VALUE_COLUMN).flags() & Qt.ItemFlag.ItemIsEditable)
    assert bool(dialog.table.item(0, LABEL_COLUMN).flags() & Qt.ItemFlag.ItemIsEditable)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: FAIL with `ImportError: cannot import name 'AnnotateSchemaValuesDialog'`

- [ ] **Step 3: Write minimal implementation**

Append to `pgtp_editor/ui/annotate_schema_values_dialog.py`:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

PATH_COLUMN = 0
ATTRIBUTE_COLUMN = 1
VALUE_COLUMN = 2
LABEL_COLUMN = 3
_COLUMN_HEADERS = ["Element Path", "Attribute", "Value", "Label"]


class AnnotateSchemaValuesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Annotate Schema Values")
        self._populating = False
        self._model = None
        self._model_path = None

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(_COLUMN_HEADERS)
        self.table.setSortingEnabled(True)
        self.table.itemChanged.connect(self._on_item_changed)

        layout = QVBoxLayout(self)
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
        self._populate_table(_build_rows(model))

    def _populate_table(self, rows):
        self._populating = True
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
                self.table.setItem(row_index, LABEL_COLUMN, label_item)
        finally:
            self._populating = False

    def _on_item_changed(self, item):
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: PASS (19 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/annotate_schema_values_dialog.py tests/ui/test_annotate_schema_values_dialog.py
git commit -m "feat(ui): add AnnotateSchemaValuesDialog table populated from _build_rows"
```

---

### Task 6: Dialog — text filter box and "Show only unlabeled" checkbox wired to `_apply_filters`

**Files:**
- Modify: `pgtp_editor/ui/annotate_schema_values_dialog.py`
- Modify: `tests/ui/test_annotate_schema_values_dialog.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_annotate_schema_values_dialog.py`:

```python
def test_dialog_unlabeled_only_checkbox_defaults_checked(qtbot, tmp_path):
    model = Model()
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    assert dialog.unlabeled_only_checkbox.isChecked() is True


def test_dialog_default_view_hides_already_labeled_rows(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(
        model, "Project/Page", "viewAbilityMode", ["1", "2"], labels={"1": "One"},
    )
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, VALUE_COLUMN).text() == "2"


def test_dialog_unchecking_unlabeled_only_reveals_labeled_rows(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(
        model, "Project/Page", "viewAbilityMode", ["1", "2"], labels={"1": "One"},
    )
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    dialog.unlabeled_only_checkbox.setChecked(False)

    assert dialog.table.rowCount() == 2


def test_dialog_text_filter_narrows_visible_rows(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/AbilityMode", "x", ["1"])
    _seed_enum_attribute(model, "Project/Other", "y", ["2"])
    dialog = _dialog_with_model(qtbot, model, tmp_path)
    dialog.unlabeled_only_checkbox.setChecked(False)

    dialog.filter_box.setText("AbilityMode")

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, PATH_COLUMN).text() == "Project/AbilityMode"


def test_dialog_clearing_text_filter_restores_full_view(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/AbilityMode", "x", ["1"])
    _seed_enum_attribute(model, "Project/Other", "y", ["2"])
    dialog = _dialog_with_model(qtbot, model, tmp_path)
    dialog.unlabeled_only_checkbox.setChecked(False)

    dialog.filter_box.setText("AbilityMode")
    dialog.filter_box.setText("")

    assert dialog.table.rowCount() == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: FAIL with `AttributeError: 'AnnotateSchemaValuesDialog' object has no attribute 'unlabeled_only_checkbox'`

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `pgtp_editor/ui/annotate_schema_values_dialog.py`'s `AnnotateSchemaValuesDialog.__init__` and add the filter wiring:

```python
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
                self.table.setItem(row_index, LABEL_COLUMN, label_item)
        finally:
            self._populating = False

    def _on_item_changed(self, item):
        pass
```

Note: `_refresh_visible_rows` re-derives the visible subset from `self._all_rows` (the full unfiltered set captured once at load time) rather than re-calling `_build_rows(self._model)`, so that edits made to `self._model.paths[...]["labels"]` via `_on_item_changed` (Task 7) do not require rebuilding `self._all_rows` from scratch — `_on_item_changed` updates the matching dict in `self._all_rows` directly (see Task 7).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: PASS (24 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/annotate_schema_values_dialog.py tests/ui/test_annotate_schema_values_dialog.py
git commit -m "feat(ui): wire text filter and Show only unlabeled checkbox in dialog"
```

---

### Task 7: Inline editing + autosave, with a real `Model.save`/`Model.load` round trip

**Files:**
- Modify: `pgtp_editor/ui/annotate_schema_values_dialog.py`
- Modify: `tests/ui/test_annotate_schema_values_dialog.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_annotate_schema_values_dialog.py`:

```python
from pgtp_editor.schema_learning.model import Model as ModelForRoundTrip


def test_editing_label_cell_updates_in_memory_model(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["3"])
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    dialog.unlabeled_only_checkbox.setChecked(False)

    dialog.table.item(0, LABEL_COLUMN).setText("Modal window")

    entry = model.paths["Project/Page"]["attributes"]["viewAbilityMode"]
    assert entry["labels"]["3"] == "Modal window"


def test_editing_label_cell_saves_and_reloads_with_new_label(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["3"])
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    dialog.unlabeled_only_checkbox.setChecked(False)

    dialog.table.item(0, LABEL_COLUMN).setText("Modal window")

    reloaded = ModelForRoundTrip.load(model_path)
    entry = reloaded.paths["Project/Page"]["attributes"]["viewAbilityMode"]
    assert entry["labels"]["3"] == "Modal window"


def test_clearing_label_cell_removes_key_rather_than_storing_empty_string(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(
        model, "Project/Page", "viewAbilityMode", ["3"], labels={"3": "Modal window"},
    )
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    dialog.unlabeled_only_checkbox.setChecked(False)

    dialog.table.item(0, LABEL_COLUMN).setText("")

    entry = model.paths["Project/Page"]["attributes"]["viewAbilityMode"]
    assert "3" not in entry["labels"]

    reloaded = ModelForRoundTrip.load(model_path)
    reloaded_entry = reloaded.paths["Project/Page"]["attributes"]["viewAbilityMode"]
    assert "3" not in reloaded_entry["labels"]


def test_programmatic_table_population_does_not_trigger_save(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1", "2", "3"])
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    mtime_before_dialog = model_path.stat().st_mtime_ns

    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)

    # Toggling the checkbox re-populates the table programmatically —
    # this must not write to disk on its own.
    dialog.unlabeled_only_checkbox.setChecked(False)
    dialog.unlabeled_only_checkbox.setChecked(True)

    assert model_path.stat().st_mtime_ns == mtime_before_dialog


def test_editing_label_updates_visible_row_after_a_filter_toggle(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1", "3"])
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    dialog.unlabeled_only_checkbox.setChecked(False)

    row_for_value_3 = next(
        row for row in range(dialog.table.rowCount())
        if dialog.table.item(row, VALUE_COLUMN).text() == "3"
    )
    dialog.table.item(row_for_value_3, LABEL_COLUMN).setText("Modal window")

    # Flip to "unlabeled only" then back — the labeled row for value "3"
    # must stay correctly labeled (self._all_rows was kept in sync, not
    # left stale), and must disappear/reappear per the filter as expected.
    dialog.unlabeled_only_checkbox.setChecked(True)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, VALUE_COLUMN).text() == "1"

    dialog.unlabeled_only_checkbox.setChecked(False)
    row_for_value_3_again = next(
        row for row in range(dialog.table.rowCount())
        if dialog.table.item(row, VALUE_COLUMN).text() == "3"
    )
    assert dialog.table.item(row_for_value_3_again, LABEL_COLUMN).text() == "Modal window"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: FAIL — editing a Label cell currently does nothing (`_on_item_changed` is a no-op `pass`), so the in-memory model is never updated and nothing is ever saved to `model_path`.

- [ ] **Step 3: Write minimal implementation**

In `pgtp_editor/ui/annotate_schema_values_dialog.py`, replace the `_on_item_changed` method body and update `_populate_table` to track each row dict on its Label item (so `_on_item_changed` can find the matching entry in `self._all_rows` without re-parsing the Path/Attribute/Value cell text):

```python
from PySide6.QtCore import Qt

_ROW_DATA_ROLE = Qt.ItemDataRole.UserRole
```

```python
    def _populate_table(self, rows):
        self._populating = True
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
            self._populating = False

    def _on_item_changed(self, item):
        if self._populating or item.column() != LABEL_COLUMN:
            return

        row = item.data(_ROW_DATA_ROLE)
        path = row["path"]
        attr = row["attribute"]
        value = row["value"]
        new_label = item.text()

        entry = self._model.paths[path]["attributes"][attr]
        entry.setdefault("labels", {})
        if new_label:
            entry["labels"][value] = new_label
        else:
            entry["labels"].pop(value, None)

        row["label"] = new_label

        self._model.save(self._model_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: PASS (29 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/annotate_schema_values_dialog.py tests/ui/test_annotate_schema_values_dialog.py
git commit -m "feat(ui): inline label editing autosaves to schema_model.json via schema_learning.model.Model"
```

---

### Task 8: Disk-loading constructor path (`AnnotateSchemaValuesDialog(schema_storage_dir=...)`)

**Files:**
- Modify: `pgtp_editor/ui/annotate_schema_values_dialog.py`
- Modify: `tests/ui/test_annotate_schema_values_dialog.py`

This task adds the real, production `__init__` path used by the menu action (Task 10): it loads `Model` from disk via `schema_model_path(schema_storage_dir)` (imported directly from `pgtp_editor.schema_learning.storage`, per the reconciliation noted at the top of this plan — no dialog-local path helper is introduced). `_for_testing` (added in Task 5) remains as-is for the earlier, in-memory-only tests; it is not removed, since those tests intentionally avoid requiring a pre-existing file on disk for the parts of the dialog that don't care about load behavior.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_annotate_schema_values_dialog.py`:

```python
from pgtp_editor.schema_learning.storage import schema_model_path


def test_dialog_loads_model_from_schema_storage_dir_on_construction(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["3"])
    model.save(schema_model_path(storage_dir))

    dialog = AnnotateSchemaValuesDialog(schema_storage_dir=storage_dir)
    qtbot.addWidget(dialog)
    dialog.unlabeled_only_checkbox.setChecked(False)

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, VALUE_COLUMN).text() == "3"


def test_dialog_edits_against_real_storage_dir_persist_to_the_correct_file(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["3"])
    model_path = schema_model_path(storage_dir)
    model.save(model_path)

    dialog = AnnotateSchemaValuesDialog(schema_storage_dir=storage_dir)
    qtbot.addWidget(dialog)
    dialog.unlabeled_only_checkbox.setChecked(False)
    dialog.table.item(0, LABEL_COLUMN).setText("Modal window")

    reloaded = ModelForRoundTrip.load(model_path)
    entry = reloaded.paths["Project/Page"]["attributes"]["viewAbilityMode"]
    assert entry["labels"]["3"] == "Modal window"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: FAIL with `TypeError: AnnotateSchemaValuesDialog() takes no keyword arguments` (or similar — `__init__` does not yet accept `schema_storage_dir`).

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/annotate_schema_values_dialog.py`. Add the import and update `__init__`:

```python
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import schema_model_path
```

```python
class AnnotateSchemaValuesDialog(QDialog):
    def __init__(self, parent=None, schema_storage_dir=None):
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

        model_path = schema_model_path(schema_storage_dir)
        model = Model.load(model_path)
        self._load_model_and_populate(model, model_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: PASS (31 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/annotate_schema_values_dialog.py tests/ui/test_annotate_schema_values_dialog.py
git commit -m "feat(ui): AnnotateSchemaValuesDialog loads schema_model.json via schema_learning.storage.schema_model_path"
```

---

### Task 9: Empty-state and malformed-JSON handling

**Files:**
- Modify: `pgtp_editor/ui/annotate_schema_values_dialog.py`
- Modify: `tests/ui/test_annotate_schema_values_dialog.py`

Per design spec §3.6: if `schema_model.json` does not exist, the dialog shows a centered empty-state message and hides the filter controls and table (not shown empty). Any other load failure (e.g. malformed JSON) is a hard error via `QMessageBox.critical`, matching `open_project_file`'s existing convention in `pgtp_editor/ui/main_window.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_annotate_schema_values_dialog.py`:

```python
from unittest.mock import patch


def test_missing_schema_model_shows_empty_state_message_and_hides_controls(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()

    dialog = AnnotateSchemaValuesDialog(schema_storage_dir=storage_dir)
    qtbot.addWidget(dialog)

    assert dialog.empty_state_label.isVisible() is True
    assert dialog.empty_state_label.text() == (
        "No schema data yet. Open a .pgtp file to begin learning the schema, "
        "then come back here to annotate it."
    )
    assert dialog.table.isVisible() is False
    assert dialog.filter_box.isVisible() is False
    assert dialog.unlabeled_only_checkbox.isVisible() is False


def test_existing_schema_model_hides_empty_state_message(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1"])
    model.save(schema_model_path(storage_dir))

    dialog = AnnotateSchemaValuesDialog(schema_storage_dir=storage_dir)
    qtbot.addWidget(dialog)

    assert dialog.empty_state_label.isVisible() is False
    assert dialog.table.isVisible() is True
    assert dialog.filter_box.isVisible() is True
    assert dialog.unlabeled_only_checkbox.isVisible() is True


def test_malformed_schema_model_shows_critical_message_box(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    model_path = schema_model_path(storage_dir)
    model_path.write_text("{not valid json", encoding="utf-8")

    with patch("pgtp_editor.ui.annotate_schema_values_dialog.QMessageBox.critical") as mock_critical:
        dialog = AnnotateSchemaValuesDialog(schema_storage_dir=storage_dir)
        qtbot.addWidget(dialog)

    mock_critical.assert_called_once()
    args, _kwargs = mock_critical.call_args
    assert args[0] is dialog
    assert "Failed to Load Schema Model" in args[1]
    assert str(model_path) in args[2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: FAIL — `Model.load(model_path)` raises `FileNotFoundError` for the missing-file case (uncaught, crashes the test) and `json.JSONDecodeError` for the malformed case (also uncaught); `dialog.empty_state_label` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/annotate_schema_values_dialog.py`: add the `QLabel`/`QMessageBox` imports and restructure `__init__`'s final block plus add `empty_state_label` to the layout:

```python
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

_EMPTY_STATE_TEXT = (
    "No schema data yet. Open a .pgtp file to begin learning the schema, "
    "then come back here to annotate it."
)


class AnnotateSchemaValuesDialog(QDialog):
    def __init__(self, parent=None, schema_storage_dir=None):
        super().__init__(parent)
        self.setWindowTitle("Annotate Schema Values")
        self._populating = False
        self._model = None
        self._model_path = None
        self._all_rows = []

        self.empty_state_label = QLabel(_EMPTY_STATE_TEXT)
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setVisible(False)

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
        layout.addWidget(self.empty_state_label)
        layout.addLayout(filter_row)
        layout.addWidget(self.table)
        self._filter_row_widgets = [self.filter_box, self.unlabeled_only_checkbox]

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
        self.table.setVisible(False)
        for widget in self._filter_row_widgets:
            widget.setVisible(False)

    def _load_model_and_populate(self, model, model_path):
        self._model = model
        self._model_path = model_path
        self._all_rows = _build_rows(model)
        self._refresh_visible_rows()
```

Note on the malformed-JSON case: after showing `QMessageBox.critical`, the dialog also falls back to the empty state (rather than leaving `self.table` populated from a half-loaded model) since there is no usable `Model` to display — this is a deliberate, minimal extension of spec §3.6, which specifies the critical dialog but does not explicitly say what the dialog's own body should show afterward; hiding the table here (rather than showing a blank one with no explanatory label) keeps the same "never a blank, unexplained table" principle §3.6 already establishes for the missing-file case.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_annotate_schema_values_dialog.py -v`
Expected: PASS (34 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/annotate_schema_values_dialog.py tests/ui/test_annotate_schema_values_dialog.py
git commit -m "feat(ui): add empty-state message and malformed-JSON error handling to dialog"
```

---

### Task 10: Menu wiring — `_build_schema_menu()` and `_open_annotate_schema_values()`

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_menus.py`

Per design spec §3.1 and §4.3: a new top-level **Schema** menu, added between **Diff / Merge** and **Tools**, containing a single entry **"Annotate Schema Values..."**. The action is always enabled — no dependency on `self._current_project`. `_open_annotate_schema_values` forwards `self._schema_storage_dir` to the dialog it constructs, so tests can isolate the dialog's storage location exactly the way `test_schema_learning_wiring.py` already isolates `open_project_file`'s.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_menus.py`:

```python
def test_schema_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Schema")
    assert menu is not None
    assert action_labels(menu) == ["Annotate Schema Values..."]


def test_schema_menu_sits_between_diff_merge_and_tools(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    titles = all_top_level_menu_titles(window)
    assert titles == [
        "File", "Edit", "View", "Diff / Merge", "Schema", "Tools", "Generation", "Help",
    ]


def test_annotate_schema_values_action_is_always_enabled(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Schema")
    action = find_action(menu, "Annotate Schema Values...")
    assert action.isEnabled() is True
```

Update the existing full-menu-order test:

```python
def test_all_top_level_menus_present_in_order(qtbot):
    # Do not call window.show() here — under the offscreen test platform's
    # small virtual screen, showing this window triggers Qt's menu-bar
    # overflow chevron, which injects a phantom empty-titled QMenu into
    # findChildren(QMenu) and breaks this order/count assertion.
    window = MainWindow()
    qtbot.addWidget(window)
    titles = all_top_level_menu_titles(window)
    assert titles == [
        "File", "Edit", "View", "Diff / Merge", "Schema", "Tools", "Generation", "Help",
    ]
```

Add a new test file for the actual dialog-opening handler:

```python
# tests/ui/test_schema_menu_entry_point.py
"""Tests for the "Annotate Schema Values..." menu entry point wired into
MainWindow — the trigger that constructs and opens AnnotateSchemaValuesDialog.
"""
from unittest.mock import MagicMock, patch

from pgtp_editor.ui.main_window import MainWindow


def test_open_annotate_schema_values_constructs_dialog_with_schema_storage_dir(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    mock_dialog_instance = MagicMock()
    with patch(
        "pgtp_editor.ui.main_window.AnnotateSchemaValuesDialog",
        return_value=mock_dialog_instance,
    ) as mock_dialog_class:
        window._open_annotate_schema_values()

    mock_dialog_class.assert_called_once_with(window, schema_storage_dir=storage_dir)
    mock_dialog_instance.exec.assert_called_once()


def test_open_annotate_schema_values_available_with_no_project_open(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    assert window._current_project is None

    with patch("pgtp_editor.ui.main_window.AnnotateSchemaValuesDialog") as mock_dialog_class:
        mock_dialog_class.return_value = MagicMock()
        window._open_annotate_schema_values()

    mock_dialog_class.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_menus.py tests/ui/test_schema_menu_entry_point.py -v`
Expected: FAIL — `find_top_menu(window, "Schema")` returns `None` (no such menu yet), and `pgtp_editor.ui.main_window` has no `AnnotateSchemaValuesDialog` name to patch (`AttributeError`) since it isn't imported there yet.

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/main_window.py`. Add the import near the top, alongside the other `pgtp_editor.ui` imports:

```python
from pgtp_editor.ui.annotate_schema_values_dialog import AnnotateSchemaValuesDialog
```

Update `_build_menu_bar`:

```python
    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_diff_merge_menu()
        self._build_schema_menu()
        self._build_tools_menu()
        self._build_generation_menu()
        self._build_help_menu()
```

Add the new menu-builder method and handler, placed after `_build_diff_merge_menu` and before `_build_tools_menu`:

```python
    def _build_schema_menu(self):
        menu = self.menuBar().addMenu("Schema")
        annotate_action = menu.addAction("Annotate Schema Values...")
        annotate_action.triggered.connect(self._open_annotate_schema_values)

    def _open_annotate_schema_values(self):
        dialog = AnnotateSchemaValuesDialog(self, schema_storage_dir=self._schema_storage_dir)
        dialog.exec()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_menus.py tests/ui/test_schema_menu_entry_point.py -v`
Expected: PASS (all tests pass, including the updated `test_all_top_level_menus_present_in_order`)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_menus.py tests/ui/test_schema_menu_entry_point.py
git commit -m "feat(ui): add Schema menu with Annotate Schema Values... entry point"
```

---

### Task 11: Full-suite regression check

**Files:** None modified — verification only.

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -v`
Expected: All tests pass, including every test in `tests/ui/test_annotate_schema_values_dialog.py`, `tests/ui/test_menus.py`, `tests/ui/test_schema_menu_entry_point.py`, and the full pre-existing suite (`tests/schema_learning/`, `tests/diff/`, the rest of `tests/ui/`) with no regressions.

- [ ] **Step 2: Confirm no stray debug code or prints were left behind**

Run: `grep -rn "print(" pgtp_editor/ui/annotate_schema_values_dialog.py pgtp_editor/ui/main_window.py`
Expected: No output (no matches).

- [ ] **Step 3: Final commit if anything was left uncommitted**

```bash
git status
```

Expected: `nothing to commit, working tree clean` (every prior task already committed its own changes — this step is a safety check, not expected to find anything to commit).

---

## Summary of judgment calls made while writing this plan

1. **`schema_model_path` reconciliation (see "Before you start"):** the dialog imports and calls `pgtp_editor.schema_learning.storage.schema_model_path` directly; no dialog-local path helper exists anywhere in this plan, deviating from the spec's §4.2 code sketch as explicitly invited by the spec itself.
2. **`AnnotateSchemaValuesDialog(schema_storage_dir=...)` constructor parameter**, mirroring `MainWindow(schema_storage_dir=...)`'s existing name/default/`Path | None` shape exactly, so `_open_annotate_schema_values()` can forward `self._schema_storage_dir` straight through and tests can isolate the dialog's storage location the same way `tests/ui/test_schema_learning_wiring.py` already isolates `open_project_file`'s.
3. **A `_for_testing` classmethod construction path** (Tasks 5-7) that bypasses disk I/O, used only for the table/filter/edit-behavior tests that don't care about load-from-disk behavior — added so those tests don't need to pre-write a `schema_model.json` to a temp directory just to exercise table population logic. The real, production `__init__` disk-loading path (empty-state / malformed-JSON / success) is exercised directly (no bypass) starting in Task 8.
4. **Row-to-cell binding via `Qt.ItemDataRole.UserRole`** (`_ROW_DATA_ROLE`) on each Label `QTableWidgetItem`, storing the row dict itself rather than re-reading Path/Attribute/Value column text in `_on_item_changed`. This keeps `_on_item_changed` correct even though the table is sortable (a sorted row's on-screen row index no longer matches build order) and avoids re-parsing three adjacent cells' text on every edit.
