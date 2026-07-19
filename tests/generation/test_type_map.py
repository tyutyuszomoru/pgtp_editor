# tests/generation/test_type_map.py
"""Tests for the declarative parity rules in generation.type_map."""
from pgtp_editor.generation import type_map


def test_humanize_splits_and_titlecases():
    assert type_map.humanize("objecttype_id") == "Objecttype Id"
    assert type_map.humanize("tag") == "Tag"
    assert type_map.humanize("physical_location") == "Physical Location"
    assert type_map.humanize("") == ""


def test_maxlength_of_varchar_and_char():
    assert type_map.maxlength_of("character varying(30)") == "30"
    assert type_map.maxlength_of("varchar(255)") == "255"
    assert type_map.maxlength_of("character(4)") == "4"
    assert type_map.maxlength_of("text") == "0"
    assert type_map.maxlength_of("numeric(10,2)") == "0"  # not a char type


def test_numeric_column_spec():
    spec = type_map.column_spec("id", "integer")
    assert spec.selected_filter_operators == type_map.FILTER_OPERATORS_NUMERIC
    assert spec.view_type == "text"
    assert spec.format_type == "number"
    assert spec.format_extra == {"decimalSeparator": "."}
    assert spec.edit_type == "textBox"
    assert spec.edit_extra == {"maxLength": "0"}


def test_string_column_spec_extracts_maxlength():
    spec = type_map.column_spec("tag", "character varying(30)")
    assert spec.selected_filter_operators == type_map.FILTER_OPERATORS_STRING
    assert spec.view_type == "text"
    assert spec.format_type is None
    assert spec.edit_type == "textBox"
    assert spec.edit_extra == {"maxLength": "30"}
    assert spec.caption == "Tag"


def test_boolean_column_spec():
    spec = type_map.column_spec("is_active", "boolean")
    assert spec.view_type == "checkBox"
    assert spec.edit_type == "checkBox"
    assert spec.format_type is None
    assert spec.edit_extra == {}


def test_datetime_column_spec():
    for dt in ("date", "timestamp without time zone", "timestamptz"):
        spec = type_map.column_spec("created", dt)
        assert spec.edit_type == "date", dt
        assert spec.view_type == "text"


def test_unknown_type_falls_back_to_string():
    spec = type_map.column_spec("weird", "jsonb")
    assert spec.edit_type == "textBox"
    assert spec.selected_filter_operators == type_map.FILTER_OPERATORS_STRING


def test_representation_names_are_the_ten_fixed_lists():
    assert type_map.REPRESENTATION_NAMES == [
        "List", "View", "Edit", "Insert", "QuickFilter",
        "FilterBuilder", "Print", "Export", "Compare", "MultiEdit",
    ]
    assert type_map.PK_HIDDEN_IN == frozenset({"Edit", "Insert", "Compare", "MultiEdit"})
