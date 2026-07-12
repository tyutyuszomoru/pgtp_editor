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
