from pgtp_editor.schema_learning.model import Model
from pgtp_editor.ui.annotate_schema_values_dialog import (
    _build_attribute_rows,
    _filter_attribute_rows,
)


def _seed_enum_attribute(
    model, path, attr_name, values, attr_type="integer", labels=None, kind=None
):
    """Directly builds a Model.paths[...] ["attributes"][...] entry shaped
    exactly like Model.merge_element would produce for a non-overflowed,
    non-secret attribute — optionally with a `kind` set (as the labeler
    would write it). Kept independent of the Schema Learning Engine's own
    ingestion path."""
    entry, _ = model._get_or_create_path(path)
    entry["attributes"][attr_name] = {
        "type": attr_type,
        "values": list(values),
        "overflowed": False,
        "attr_seen_count": len(values),
        "labels": dict(labels or {}),
    }
    if kind is not None:
        entry["attributes"][attr_name]["kind"] = kind


# ---------------------------------------------------------------------------
# _build_attribute_rows
# ---------------------------------------------------------------------------


def test_build_attribute_rows_one_row_per_enum_candidate():
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1", "2", "3"])

    rows = _build_attribute_rows(model)

    assert len(rows) == 1
    row = rows[0]
    assert row["path"] == "Project/Page"
    assert row["attribute"] == "viewAbilityMode"


def test_build_attribute_rows_counts_values_and_labeled():
    model = Model()
    _seed_enum_attribute(
        model, "Project/Page", "viewAbilityMode", ["1", "2", "3"],
        labels={"1": "Modal", "3": "Inline"},
    )

    rows = _build_attribute_rows(model)

    assert rows[0]["num_values"] == 3
    assert rows[0]["num_labeled"] == 2


def test_build_attribute_rows_kind_defaults_to_unclassified():
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1"])

    rows = _build_attribute_rows(model)

    assert rows[0]["kind"] == "unclassified"


def test_build_attribute_rows_reflects_setting_kind():
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "editFormMode", ["1"], kind="setting")

    rows = _build_attribute_rows(model)

    assert rows[0]["kind"] == "setting"


def test_build_attribute_rows_includes_content_kind_rows():
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "caption", ["a", "b"], attr_type="string", kind="content")

    rows = _build_attribute_rows(model)

    assert len(rows) == 1
    assert rows[0]["kind"] == "content"


def test_build_attribute_rows_excludes_overflowed():
    model = Model()
    entry, _ = model._get_or_create_path("Project/Page")
    entry["attributes"]["freeform"] = {
        "type": "string",
        "values": None,
        "overflowed": True,
        "attr_seen_count": 11,
        "labels": {},
    }

    rows = _build_attribute_rows(model)

    assert rows == []


def test_build_attribute_rows_excludes_boolean():
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "isVisible", ["true", "false"], attr_type="boolean")

    rows = _build_attribute_rows(model)

    assert rows == []


def test_build_attribute_rows_excludes_empty_values():
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "neverSeen", [])

    rows = _build_attribute_rows(model)

    assert rows == []


def test_build_attribute_rows_sorted_by_path_then_attribute():
    model = Model()
    _seed_enum_attribute(model, "Z/Path", "b", ["1"])
    _seed_enum_attribute(model, "A/Path", "z", ["1"])
    _seed_enum_attribute(model, "A/Path", "a", ["1"])

    rows = _build_attribute_rows(model)

    keys = [(r["path"], r["attribute"]) for r in rows]
    assert keys == [("A/Path", "a"), ("A/Path", "z"), ("Z/Path", "b")]


def test_build_attribute_rows_missing_labels_key_counts_zero():
    model = Model()
    entry, _ = model._get_or_create_path("Project/Page")
    entry["attributes"]["legacy"] = {
        "type": "integer",
        "values": ["1"],
        "overflowed": False,
        "attr_seen_count": 1,
    }

    rows = _build_attribute_rows(model)

    assert rows[0]["num_labeled"] == 0
    assert rows[0]["num_values"] == 1


# ---------------------------------------------------------------------------
# _filter_attribute_rows
# ---------------------------------------------------------------------------


def _rows():
    return [
        {"path": "A/Ability", "attribute": "mode", "kind": "unclassified", "num_values": 2, "num_labeled": 0},
        {"path": "A/Ability", "attribute": "editForm", "kind": "setting", "num_values": 3, "num_labeled": 1},
        {"path": "B/Other", "attribute": "caption", "kind": "content", "num_values": 5, "num_labeled": 0},
    ]


def test_filter_all_includes_content():
    result = _filter_attribute_rows(_rows(), kind_filter="all", text="")
    assert len(result) == 3


def test_filter_unclassified_only():
    result = _filter_attribute_rows(_rows(), kind_filter="unclassified", text="")
    assert [r["attribute"] for r in result] == ["mode"]


def test_filter_setting_only():
    result = _filter_attribute_rows(_rows(), kind_filter="setting", text="")
    assert [r["attribute"] for r in result] == ["editForm"]


def test_filter_content_only():
    result = _filter_attribute_rows(_rows(), kind_filter="content", text="")
    assert [r["attribute"] for r in result] == ["caption"]


def test_filter_text_matches_path_case_insensitively():
    result = _filter_attribute_rows(_rows(), kind_filter="all", text="ability")
    assert [r["attribute"] for r in result] == ["mode", "editForm"]


def test_filter_text_matches_attribute_case_insensitively():
    result = _filter_attribute_rows(_rows(), kind_filter="all", text="CAPTION")
    assert [r["attribute"] for r in result] == ["caption"]


def test_filter_kind_and_text_combine():
    result = _filter_attribute_rows(_rows(), kind_filter="setting", text="ability")
    assert [r["attribute"] for r in result] == ["editForm"]


# ---------------------------------------------------------------------------
# UI: dialog construction / left pane
# ---------------------------------------------------------------------------

from PySide6.QtCore import Qt

from pgtp_editor.ui.annotate_schema_values_dialog import (
    ATTRIBUTE_COLUMN,
    KIND_COLUMN,
    NUM_LABELED_COLUMN,
    NUM_VALUES_COLUMN,
    PATH_COLUMN,
    AnnotateSchemaValuesDialog,
)


def _dialog_with_model(qtbot, model, tmp_path):
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    return dialog


def test_dialog_attribute_table_headers(qtbot, tmp_path):
    dialog = _dialog_with_model(qtbot, Model(), tmp_path)

    assert dialog.attribute_table.columnCount() == 5
    headers = [dialog.attribute_table.horizontalHeaderItem(i).text() for i in range(5)]
    assert headers == ["Element Path", "Attribute", "Kind", "#values", "#labeled"]


def test_dialog_left_pane_one_row_per_attribute(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1", "2", "3"])
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    assert dialog.attribute_table.rowCount() == 1
    assert dialog.attribute_table.item(0, PATH_COLUMN).text() == "Project/Page"
    assert dialog.attribute_table.item(0, ATTRIBUTE_COLUMN).text() == "viewAbilityMode"
    assert dialog.attribute_table.item(0, NUM_VALUES_COLUMN).text() == "3"
    assert dialog.attribute_table.item(0, NUM_LABELED_COLUMN).text() == "0"


def test_dialog_default_filter_shows_unclassified_and_settings_not_content(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "P", "a_unclassified", ["1"])
    _seed_enum_attribute(model, "P", "b_setting", ["1"], kind="setting")
    _seed_enum_attribute(model, "P", "c_content", ["1"], kind="content")
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    shown = {
        dialog.attribute_table.item(r, ATTRIBUTE_COLUMN).text()
        for r in range(dialog.attribute_table.rowCount())
    }
    assert shown == {"a_unclassified", "b_setting"}


def test_dialog_content_is_viewable_via_filter(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "P", "c_content", ["1"], kind="content")
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    dialog.set_kind_filter("all")

    shown = {
        dialog.attribute_table.item(r, ATTRIBUTE_COLUMN).text()
        for r in range(dialog.attribute_table.rowCount())
    }
    assert "c_content" in shown


def test_dialog_text_filter_narrows_rows(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/AbilityMode", "x", ["1"])
    _seed_enum_attribute(model, "Project/Other", "y", ["1"])
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    dialog.filter_box.setText("AbilityMode")

    assert dialog.attribute_table.rowCount() == 1
    assert dialog.attribute_table.item(0, PATH_COLUMN).text() == "Project/AbilityMode"


# ---------------------------------------------------------------------------
# UI: kind-combo write-back
# ---------------------------------------------------------------------------

from pgtp_editor.schema_learning.model import Model as ModelForRoundTrip


def test_setting_kind_to_content_writes_entry_and_persists(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "caption", ["a"], attr_type="string")
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)

    dialog.set_row_kind(0, "content")

    entry = model.paths["Project/Page"]["attributes"]["caption"]
    assert entry["kind"] == "content"
    reloaded = ModelForRoundTrip.load(model_path)
    assert reloaded.paths["Project/Page"]["attributes"]["caption"]["kind"] == "content"


def test_setting_kind_to_setting_persists(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "editFormMode", ["1"])
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)

    dialog.set_row_kind(0, "setting")

    reloaded = ModelForRoundTrip.load(model_path)
    assert reloaded.paths["Project/Page"]["attributes"]["editFormMode"]["kind"] == "setting"


def test_setting_kind_back_to_unclassified_removes_key(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "editFormMode", ["1"], kind="setting")
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)

    dialog.set_row_kind(0, "unclassified")

    entry = model.paths["Project/Page"]["attributes"]["editFormMode"]
    assert "kind" not in entry
    reloaded = ModelForRoundTrip.load(model_path)
    assert "kind" not in reloaded.paths["Project/Page"]["attributes"]["editFormMode"]


# ---------------------------------------------------------------------------
# UI: right pane / value-label write-back
# ---------------------------------------------------------------------------

from pgtp_editor.ui.annotate_schema_values_dialog import (
    VALUE_LABEL_COLUMN,
    VALUE_VALUE_COLUMN,
)


def test_non_setting_selection_shows_placeholder_and_no_value_rows(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1", "2"])
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    dialog.select_attribute_row(0)

    assert dialog.value_placeholder.isHidden() is False
    assert (
        dialog.value_placeholder.text()
        == "Mark this attribute as a Setting to label its values."
    )
    assert dialog.value_table.isHidden() is True
    assert dialog.value_table.rowCount() == 0


def test_setting_selection_shows_values_with_existing_labels(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(
        model, "Project/Page", "editFormMode", ["1", "2"],
        labels={"1": "Modal"}, kind="setting",
    )
    dialog = _dialog_with_model(qtbot, model, tmp_path)

    dialog.select_attribute_row(0)

    assert dialog.value_table.isHidden() is False
    assert dialog.value_table.rowCount() == 2
    by_value = {
        dialog.value_table.item(r, VALUE_VALUE_COLUMN).text():
        dialog.value_table.item(r, VALUE_LABEL_COLUMN).text()
        for r in range(dialog.value_table.rowCount())
    }
    assert by_value == {"1": "Modal", "2": ""}


def test_editing_value_label_persists(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "editFormMode", ["3"], kind="setting")
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    dialog.select_attribute_row(0)

    dialog.value_table.item(0, VALUE_LABEL_COLUMN).setText("Modal window")

    entry = model.paths["Project/Page"]["attributes"]["editFormMode"]
    assert entry["labels"]["3"] == "Modal window"
    reloaded = ModelForRoundTrip.load(model_path)
    assert reloaded.paths["Project/Page"]["attributes"]["editFormMode"]["labels"]["3"] == "Modal window"


def test_clearing_value_label_removes_key(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(
        model, "Project/Page", "editFormMode", ["3"], labels={"3": "Modal"}, kind="setting",
    )
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    dialog.select_attribute_row(0)

    dialog.value_table.item(0, VALUE_LABEL_COLUMN).setText("")

    entry = model.paths["Project/Page"]["attributes"]["editFormMode"]
    assert "3" not in entry["labels"]
    reloaded = ModelForRoundTrip.load(model_path)
    assert "3" not in reloaded.paths["Project/Page"]["attributes"]["editFormMode"]["labels"]


def test_value_value_column_read_only_label_editable(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    model = Model()
    _seed_enum_attribute(model, "Project/Page", "editFormMode", ["1"], kind="setting")
    dialog = _dialog_with_model(qtbot, model, tmp_path)
    dialog.select_attribute_row(0)

    assert not bool(dialog.value_table.item(0, VALUE_VALUE_COLUMN).flags() & Qt.ItemFlag.ItemIsEditable)
    assert bool(dialog.value_table.item(0, VALUE_LABEL_COLUMN).flags() & Qt.ItemFlag.ItemIsEditable)


def test_programmatic_population_does_not_save(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "editFormMode", ["1", "2"], kind="setting")
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    mtime_before = model_path.stat().st_mtime_ns

    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    dialog.set_kind_filter("all")
    dialog.select_attribute_row(0)
    dialog.set_kind_filter("setting")

    assert model_path.stat().st_mtime_ns == mtime_before


def test_repopulation_does_not_fire_kind_combo_writeback(qtbot, tmp_path):
    """Repopulating the left table (which recreates Kind combos and sets
    their current index) must not trigger a write-back / save."""
    model = Model()
    _seed_enum_attribute(model, "P", "a", ["1"], kind="setting")
    _seed_enum_attribute(model, "P", "b", ["1"], kind="content")
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)

    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    mtime_before = model_path.stat().st_mtime_ns

    # A filter change repopulates the table (recreating combos at various
    # indices). None of that should write to disk.
    dialog.set_kind_filter("all")
    dialog.set_kind_filter("setting")
    dialog.set_kind_filter(None)

    assert model_path.stat().st_mtime_ns == mtime_before


# ---------------------------------------------------------------------------
# C1: kind write-back resolves acting row by identity, not captured index,
# so it stays correct after the user sorts the left table.
# ---------------------------------------------------------------------------


def test_kind_writeback_targets_correct_attribute_after_sort(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "P", "aaa", ["1"])
    _seed_enum_attribute(model, "P", "zzz", ["1"])
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)

    # Initially sorted ascending: row 0 == "aaa", row 1 == "zzz".
    # Reverse the visual order by sorting descending on the attribute col.
    dialog.attribute_table.sortItems(ATTRIBUTE_COLUMN, Qt.DescendingOrder)

    # After descending sort, visual row 0 is "zzz", visual row 1 is "aaa".
    visual_row_0_attr = dialog.attribute_table.item(0, ATTRIBUTE_COLUMN).text()
    visual_row_1_attr = dialog.attribute_table.item(1, ATTRIBUTE_COLUMN).text()
    assert visual_row_0_attr == "zzz"
    assert visual_row_1_attr == "aaa"

    # Drive the combo at VISUAL row 0 (which shows "zzz") to Content.
    combo = dialog.attribute_table.cellWidget(0, KIND_COLUMN)
    combo.setCurrentIndex(2)  # Content

    # The attribute ACTUALLY shown at visual row 0 ("zzz") must be the one
    # that changed; "aaa" must be untouched.
    reloaded = ModelForRoundTrip.load(model_path)
    attrs = reloaded.paths["P"]["attributes"]
    assert attrs["zzz"]["kind"] == "content"
    assert "kind" not in attrs["aaa"]


# ---------------------------------------------------------------------------
# I2: marking a row a kind outside the active filter removes its row.
# ---------------------------------------------------------------------------


def test_marking_content_removes_row_from_default_view(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "P", "a_setting", ["1"], kind="setting")
    _seed_enum_attribute(model, "P", "b_unclassified", ["1"])
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)

    # Default view shows both.
    assert dialog.attribute_table.rowCount() == 2

    # Find the visual row showing "a_setting" and mark it Content.
    target_row = next(
        r for r in range(dialog.attribute_table.rowCount())
        if dialog.attribute_table.item(r, ATTRIBUTE_COLUMN).text() == "a_setting"
    )
    combo = dialog.attribute_table.cellWidget(target_row, KIND_COLUMN)
    combo.setCurrentIndex(2)  # Content

    # In the default (content-hidden) view, the row must be gone.
    shown = {
        dialog.attribute_table.item(r, ATTRIBUTE_COLUMN).text()
        for r in range(dialog.attribute_table.rowCount())
    }
    assert "a_setting" not in shown
    assert shown == {"b_unclassified"}
    assert model.paths["P"]["attributes"]["a_setting"]["kind"] == "content"


# ---------------------------------------------------------------------------
# M3: #labeled column refreshes after a label edit.
# ---------------------------------------------------------------------------


def test_labeled_count_updates_after_label_edit(qtbot, tmp_path):
    model = Model()
    _seed_enum_attribute(model, "P", "editFormMode", ["1", "2"], kind="setting")
    model_path = tmp_path / "schema_model.json"
    model.save(model_path)
    dialog = AnnotateSchemaValuesDialog._for_testing(model, model_path)
    qtbot.addWidget(dialog)
    dialog.select_attribute_row(0)

    # Initially nothing labeled.
    def labeled_cell_text():
        for r in range(dialog.attribute_table.rowCount()):
            if dialog.attribute_table.item(r, ATTRIBUTE_COLUMN).text() == "editFormMode":
                return dialog.attribute_table.item(r, NUM_LABELED_COLUMN).text()
        raise AssertionError("editFormMode row not found")

    assert labeled_cell_text() == "0"

    # Label one value.
    dialog.value_table.item(0, VALUE_LABEL_COLUMN).setText("Modal")

    assert labeled_cell_text() == "1"


# ---------------------------------------------------------------------------
# UI: empty-state & malformed JSON (unchanged behavior)
# ---------------------------------------------------------------------------

from pgtp_editor.schema_learning.storage import schema_model_path


def test_missing_schema_model_shows_empty_state_message_and_hides_controls(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()

    dialog = AnnotateSchemaValuesDialog(schema_storage_dir=storage_dir)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.empty_state_label.isVisible() is True
    assert dialog.empty_state_label.text() == (
        "No schema data yet. Open a .pgtp file to begin learning the schema, "
        "then come back here to annotate it."
    )
    assert dialog.attribute_table.isVisible() is False
    assert dialog.filter_box.isVisible() is False


def test_existing_schema_model_hides_empty_state_message(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["1"])
    model.save(schema_model_path(storage_dir))

    dialog = AnnotateSchemaValuesDialog(schema_storage_dir=storage_dir)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.empty_state_label.isVisible() is False
    assert dialog.attribute_table.isVisible() is True
    assert dialog.filter_box.isVisible() is True


def test_dialog_loads_model_from_schema_storage_dir_on_construction(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    model = Model()
    _seed_enum_attribute(model, "Project/Page", "viewAbilityMode", ["3"])
    model.save(schema_model_path(storage_dir))

    dialog = AnnotateSchemaValuesDialog(schema_storage_dir=storage_dir)
    qtbot.addWidget(dialog)

    assert dialog.attribute_table.rowCount() == 1
    assert dialog.attribute_table.item(0, ATTRIBUTE_COLUMN).text() == "viewAbilityMode"


from unittest.mock import patch


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
