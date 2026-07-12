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
    # This row already has a label, and the "Show only unlabeled" checkbox
    # (added in Task 6) defaults to checked — uncheck it so the labeled
    # row stays visible for this cell-content assertion.
    dialog.unlabeled_only_checkbox.setChecked(False)

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
