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
