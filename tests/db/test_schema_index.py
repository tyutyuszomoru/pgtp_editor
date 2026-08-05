# tests/db/test_schema_index.py
"""Tests for pgtp_editor.db.schema_index -- pure, Qt-free lookup over a
`DatabaseSchema` (spec §18.6). No Qt import, no live database."""
from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
)
from pgtp_editor.db.schema_index import SchemaIndex


def _schema():
    tables = {
        "pr.equipment": TableInfo(
            name="pr.equipment",
            kind="table",
            columns=[
                ColumnInfo(
                    name="id", data_type="integer", is_pk=True, is_fk=False,
                    is_nullable=False, default=None,
                ),
                ColumnInfo(
                    name="tag", data_type="varchar", is_pk=False, is_fk=False,
                    is_nullable=True, default=None,
                ),
            ],
        ),
        "pr.eq_view": TableInfo(name="pr.eq_view", kind="view", columns=[]),
        "hr.employee": TableInfo(
            name="hr.employee",
            kind="table",
            columns=[
                ColumnInfo(
                    name="name", data_type="text", is_pk=False, is_fk=False,
                    is_nullable=True, default=None,
                ),
            ],
        ),
    }
    routines = {
        "pr.audit_log()": RoutineInfo(
            schema="pr", name="audit_log", arg_types=[], return_type="trigger",
            language="plpgsql", source="CREATE FUNCTION pr.audit_log() ...",
            kind="function",
        ),
        "pr.calc_total(integer)": RoutineInfo(
            schema="pr", name="calc_total", arg_types=["integer"],
            return_type="numeric", language="plpgsql", source="...",
            kind="function",
        ),
    }
    triggers = {
        "pr.equipment.trg_audit": TriggerInfo(
            schema="pr", table="equipment", name="trg_audit", timing="after",
            events=["insert"], function_name="audit_log",
            definition="CREATE TRIGGER trg_audit ...",
        ),
    }
    return DatabaseSchema(tables=tables, routines=routines, triggers=triggers)


def test_known_schemas_sorted():
    index = SchemaIndex(_schema())
    assert index.known_schemas() == ["hr", "pr"]


def test_known_schemas_empty_when_no_tables():
    index = SchemaIndex(DatabaseSchema())
    assert index.known_schemas() == []


def test_known_tables_lists_bare_names_for_schema():
    index = SchemaIndex(_schema())
    assert index.known_tables("pr") == ["eq_view", "equipment"]


def test_known_tables_prefix_filters_case_insensitive():
    index = SchemaIndex(_schema())
    assert index.known_tables("pr", "Eq") == ["eq_view", "equipment"]
    assert index.known_tables("pr", "equi") == ["equipment"]


def test_known_tables_unknown_schema_is_empty():
    index = SchemaIndex(_schema())
    assert index.known_tables("nosuch") == []


def test_known_columns_schema_qualified_key():
    index = SchemaIndex(_schema())
    assert index.known_columns("pr.equipment") == ["id", "tag"]


def test_known_columns_unknown_table_is_empty():
    index = SchemaIndex(_schema())
    assert index.known_columns("pr.nosuch") == []


def test_known_columns_view_with_no_columns():
    index = SchemaIndex(_schema())
    assert index.known_columns("pr.eq_view") == []


def test_trigger_for_function_finds_attached_trigger():
    index = SchemaIndex(_schema())
    trigger = index.trigger_for_function("pr", "audit_log")
    assert trigger is not None
    assert trigger.table == "equipment"
    assert trigger.name == "trg_audit"


def test_trigger_for_function_none_when_unattached():
    index = SchemaIndex(_schema())
    assert index.trigger_for_function("pr", "calc_total") is None


def test_trigger_for_function_none_when_name_unknown():
    index = SchemaIndex(_schema())
    assert index.trigger_for_function("pr", "nosuch") is None


def test_trigger_for_function_disambiguates_by_schema():
    schema = _schema()
    schema.triggers["hr.employee.trg_other"] = TriggerInfo(
        schema="hr", table="employee", name="trg_other", timing="before",
        events=["update"], function_name="audit_log", definition="...",
    )
    index = SchemaIndex(schema)
    assert index.trigger_for_function("pr", "audit_log").schema == "pr"
    assert index.trigger_for_function("hr", "audit_log").schema == "hr"


def test_trigger_for_function_falls_back_when_schema_not_matched():
    """No candidate matches `schema` exactly (stale/mismatched caller data) --
    returns the first candidate rather than silently reporting unattached."""
    index = SchemaIndex(_schema())
    trigger = index.trigger_for_function("other_schema", "audit_log")
    assert trigger is not None
    assert trigger.function_name == "audit_log"
