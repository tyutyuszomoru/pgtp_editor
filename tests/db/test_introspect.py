# tests/db/test_introspect.py
"""Tests for pgtp_editor.db.introspect using an injected fake `runner`.

psycopg is NEVER imported here: only `run_queries` imports it (lazily, inside
the function) and these tests never call it. `fetch_schema`/`test_connection`
take a `runner=` callable, so the whole suite passes even without psycopg.
"""
import logging

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.introspect import (
    SCHEMA_SQL,
    ColumnInfo,
    DatabaseSchema,
    TableInfo,
    fetch_schema,
)
from pgtp_editor.db.introspect import test_connection as check_connection

_PARAMS = ConnectionParams(
    host="h", port="5432", database="d", user="u", password="s3cr3t-real-pw"
)


def _canned_runner():
    """Return (runner, calls) — a fake returning pg_catalog-shaped rows.

    relations:   (schema, name, relkind)
    columns:     (schema, table, colname, format_type, attnotnull, default)
    constraints: (schema, table, colname, contype)
    """
    relations = [
        ("pr", "equipment", "r"),
        ("pr", "eq_view", "v"),
        ("pr", "eq_matview", "m"),
        ("pr", "part", "p"),
    ]
    columns = [
        ("pr", "equipment", "id", "integer", True, "nextval('seq'::regclass)"),
        ("pr", "equipment", "tag", "varchar(255)", False, None),
        ("pr", "equipment", "owner_id", "integer", True, None),
        ("pr", "eq_view", "vcol", "text", False, None),
    ]
    constraints = [
        ("pr", "equipment", "id", "p"),
        ("pr", "equipment", "owner_id", "f"),
    ]
    calls = []

    def runner(params, sql_list):
        calls.append((params, list(sql_list)))
        return [relations, columns, constraints]

    return runner, calls


def test_fetch_schema_passes_schema_sql_to_runner():
    runner, calls = _canned_runner()
    fetch_schema(_PARAMS, runner=runner)
    assert len(calls) == 1
    assert calls[0][0] is _PARAMS
    assert calls[0][1] == list(SCHEMA_SQL)


def test_fetch_schema_maps_relation_kinds():
    runner, _ = _canned_runner()
    schema = fetch_schema(_PARAMS, runner=runner)
    assert schema.table("pr.equipment").kind == "table"
    assert schema.table("pr.part").kind == "table"
    assert schema.table("pr.eq_view").kind == "view"
    assert schema.table("pr.eq_matview").kind == "matview"


def test_fetch_schema_keys_are_schema_qualified():
    runner, _ = _canned_runner()
    schema = fetch_schema(_PARAMS, runner=runner)
    assert schema.has_table("pr.equipment")
    assert not schema.has_table("equipment")
    assert schema.table("nope.table") is None


def test_fetch_schema_column_metadata():
    runner, _ = _canned_runner()
    schema = fetch_schema(_PARAMS, runner=runner)

    id_col = schema.column("pr.equipment", "id")
    assert id_col == ColumnInfo(
        name="id",
        data_type="integer",
        is_pk=True,
        is_fk=False,
        is_nullable=False,
        default="nextval('seq'::regclass)",
    )

    tag_col = schema.column("pr.equipment", "tag")
    assert tag_col.data_type == "varchar(255)"
    assert tag_col.is_pk is False
    assert tag_col.is_fk is False
    assert tag_col.is_nullable is True
    assert tag_col.default is None

    owner_col = schema.column("pr.equipment", "owner_id")
    assert owner_col.is_fk is True
    assert owner_col.is_pk is False
    assert owner_col.is_nullable is False


def test_fetch_schema_missing_column_returns_none():
    runner, _ = _canned_runner()
    schema = fetch_schema(_PARAMS, runner=runner)
    assert schema.column("pr.equipment", "nonexistent") is None
    assert schema.column("nope.table", "x") is None


def test_test_connection_ok():
    def runner(params, sql_list):
        assert sql_list == ["SELECT 1"]
        return [[(1,)]]

    ok, message = check_connection(_PARAMS, runner=runner)
    assert ok is True
    assert message == "Connected."


def test_test_connection_error_never_raises():
    def runner(params, sql_list):
        raise RuntimeError("connection refused")

    ok, message = check_connection(_PARAMS, runner=runner)
    assert ok is False
    assert "connection refused" in message


def test_dataclasses_and_schema_helpers():
    col = ColumnInfo("c", "int", False, False, True, None)
    table = TableInfo("s.t", "table", [col])
    schema = DatabaseSchema({"s.t": table})
    assert schema.has_table("s.t")
    assert schema.table("s.t") is table
    assert schema.column("s.t", "c") is col


def test_fetch_schema_start_log_is_redacted(caplog):
    runner, _ = _canned_runner()
    with caplog.at_level(logging.INFO, logger="pgtp_editor.db.introspect"):
        fetch_schema(_PARAMS, runner=runner)
    messages = [r.message for r in caplog.records]
    assert any("password=***" in m for m in messages)
    assert not any(_PARAMS.password in m for m in messages)
