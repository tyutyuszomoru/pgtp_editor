# tests/db/test_introspect.py
"""Tests for pgtp_editor.db.introspect using an injected fake `runner`.

psycopg is NEVER imported here: only `run_queries` imports it (lazily, inside
the function) and these tests never call it. `fetch_schema`/`test_connection`
take a `runner=` callable, so the whole suite passes even without psycopg.
"""
import logging

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.introspect import (
    ROUTINE_TRIGGER_SQL,
    SCHEMA_SQL,
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
    _decode_trigger_type,
    _input_args,
    fetch_routines_and_triggers,
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


def test_fetch_schema_captures_fk_target():
    """FK constraint rows carrying a referenced schema.table.column populate
    ColumnInfo.fk_target; PK rows (4-tuple or None ref) leave it None."""
    relations = [("pr", "part", "r")]
    columns = [
        ("pr", "part", "id", "integer", True, None),
        ("pr", "part", "equipment_id", "integer", False, None),
    ]
    constraints = [
        ("pr", "part", "id", "p", None),
        ("pr", "part", "equipment_id", "f", "pr.equipment.id"),
    ]

    def runner(params, sql_list):
        return [relations, columns, constraints]

    schema = fetch_schema(_PARAMS, runner=runner)
    assert schema.column("pr.part", "equipment_id").fk_target == "pr.equipment.id"
    assert schema.column("pr.part", "id").fk_target is None


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


def test_database_schema_tables_only_construction_defaults_routines_and_triggers_empty():
    """Pre-existing callers throughout the codebase (generation/*, db/compare
    tests) construct `DatabaseSchema` positionally or with only `tables=` --
    the new `.routines`/`.triggers` fields must not break that contract."""
    table = TableInfo("s.t", "table", [])

    positional = DatabaseSchema({"s.t": table})
    keyword = DatabaseSchema(tables={"s.t": table})
    no_args = DatabaseSchema()

    for schema in (positional, keyword, no_args):
        assert schema.routines == {}
        assert schema.triggers == {}
    assert positional.tables == {"s.t": table}
    assert keyword.tables == {"s.t": table}
    assert no_args.tables == {}


def test_fetch_schema_start_log_is_redacted(caplog):
    runner, _ = _canned_runner()
    with caplog.at_level(logging.INFO, logger="pgtp_editor.db.introspect"):
        fetch_schema(_PARAMS, runner=runner)
    messages = [r.message for r in caplog.records]
    assert any("password=***" in m for m in messages)
    assert not any(_PARAMS.password in m for m in messages)


# --- Routines & triggers (§18.1 DDL Explorer) -------------------------------


def test_input_args_all_in_modes_null_is_the_common_case():
    """Postgres leaves proargmodes NULL when every argument is IN -- the
    overwhelmingly common case. An absent mode must read as IN, and names
    line up positionally with types."""
    assert _input_args(["integer", "integer"], ["year", "month"], None) == [
        ("year", "integer"),
        ("month", "integer"),
    ]


def test_input_args_zero_arguments():
    assert _input_args([], None, None) == []
    assert _input_args(None, None, None) == []


def test_input_args_drops_out_arguments_but_keeps_inout():
    """With OUT args present, proargmodes/proargnames/proallargtypes all
    align over ALL args -- only i (IN) and b (INOUT) are input arguments."""
    result = _input_args(
        ["integer", "text", "numeric"],
        ["in_id", "out_label", "both_qty"],
        ["i", "o", "b"],
    )
    assert result == [("in_id", "integer"), ("both_qty", "numeric")]


def test_input_args_drops_table_mode():
    result = _input_args(
        ["integer", "text"],
        ["real_arg", "table_col"],
        ["i", "t"],
    )
    assert result == [("real_arg", "integer")]


def test_input_args_unnamed_arguments_yield_empty_name():
    """proargnames is NULL when no argument is named; individual entries can
    also be empty for a partially-named signature."""
    assert _input_args(["integer"], None, None) == [("", "integer")]
    assert _input_args(["integer", "text"], ["", "named"], None) == [
        ("", "integer"),
        ("named", "text"),
    ]


def test_input_args_tolerates_short_name_and_mode_arrays():
    """Defensive: a names/modes array shorter than the type array must not
    IndexError -- missing entries degrade to unnamed / IN."""
    assert _input_args(["integer", "text"], ["only_first"], None) == [
        ("only_first", "integer"),
        ("", "text"),
    ]
    assert _input_args(["integer", "text"], None, ["i"]) == [
        ("", "integer"),
        ("", "text"),
    ]


def test_input_args_all_out_arguments_yield_no_inputs():
    """An OUT-only signature (`f(OUT a int, OUT b text)`) is a zero-input
    routine as far as the tree is concerned -- §18.1's `args == []` case."""
    assert _input_args(["integer", "text"], ["a", "b"], ["o", "o"]) == []


def test_input_args_keeps_variadic_mode():
    """VARIADIC ('v') IS an input argument -- the caller passes it -- so it
    must appear among the pairs. Dropping it (as an over-literal reading of
    "IN/INOUT only" first did) silently hid the trailing parameter of e.g.
    `f(fixed int, VARIADIC rest text[])` from the tree."""
    assert _input_args(
        ["integer", "text[]"], ["fixed", "rest"], ["i", "v"]
    ) == [("fixed", "integer"), ("rest", "text[]")]


def test_input_args_empty_mode_entry_reads_as_in():
    """A falsy per-entry mode (NULL inside the array) degrades to IN rather
    than silently dropping a real input argument."""
    assert _input_args(["integer", "text"], ["a", "b"], [None, ""]) == [
        ("a", "integer"),
        ("b", "text"),
    ]


def test_input_args_ignores_names_and_modes_beyond_the_type_array():
    """The type array is the spine: longer names/modes arrays cannot invent
    extra arguments."""
    assert _input_args(
        ["integer"], ["a", "ghost", "phantom"], ["i", "i", "o"]
    ) == [("a", "integer")]


def test_input_args_preserves_declared_order_with_out_args_interleaved():
    """proallargtypes/proargnames/proargmodes are positionally parallel over
    ALL arguments -- dropping an OUT must not shift later names onto the
    wrong types."""
    assert _input_args(
        ["integer", "text", "boolean", "numeric"],
        ["first", "out_mid", "second", "third"],
        ["i", "o", "b", "i"],
    ) == [("first", "integer"), ("second", "boolean"), ("third", "numeric")]


def test_input_args_returns_a_fresh_list_each_call():
    """No shared mutable default leaking between RoutineInfo instances."""
    one = _input_args(["integer"], ["a"], None)
    two = _input_args(["integer"], ["a"], None)
    assert one == two
    assert one is not two


def test_routine_info_args_defaults_to_empty_list():
    """Backward compatibility: `args` is additive, existing construction
    sites that never pass it still work and get []."""
    routine = RoutineInfo(schema="s", name="n")
    assert routine.args == []
    assert RoutineInfo(schema="s", name="other").args is not routine.args


def test_routines_sql_sources_names_and_modes():
    """The widened query must actually select the two catalog columns the
    correlation depends on (§18.1)."""
    routines_sql = ROUTINE_TRIGGER_SQL[0]
    assert "proargnames" in routines_sql
    assert "proargmodes" in routines_sql
    assert "proallargtypes" in routines_sql


def test_decode_trigger_type_before_insert_update():
    # BEFORE(2) | INSERT(4) | UPDATE(16) = 22
    timing, events = _decode_trigger_type(2 | 4 | 16)
    assert timing == "before"
    assert events == ["insert", "update"]


def test_decode_trigger_type_defaults_to_after_when_before_bit_unset():
    # AFTER DELETE: no BEFORE(2), no INSTEAD(64) bit -- DELETE(8) only.
    timing, events = _decode_trigger_type(8)
    assert timing == "after"
    assert events == ["delete"]


def test_decode_trigger_type_instead_of():
    timing, _events = _decode_trigger_type(64)
    assert timing == "instead of"


def test_decode_trigger_type_truncate():
    _timing, events = _decode_trigger_type(32)
    assert events == ["truncate"]


def test_decode_trigger_type_no_bits_set_yields_after_and_no_events():
    timing, events = _decode_trigger_type(0)
    assert timing == "after"
    assert events == []


def test_decode_trigger_type_all_four_events_preserve_canonical_order():
    # INSERT(4) | UPDATE(16) | DELETE(8) | TRUNCATE(32), passed out of order.
    timing, events = _decode_trigger_type(32 | 4 | 16 | 8)
    assert timing == "after"
    assert events == ["insert", "update", "delete", "truncate"]


def test_decode_trigger_type_instead_of_takes_precedence_over_before_bit():
    # Not a real Postgres combination (INSTEAD OF triggers can't be BEFORE/AFTER
    # qualified), but the decoder is a pure bitmask function -- pin its
    # precedence rule (INSTEAD checked first) so a future refactor can't
    # silently flip it.
    timing, _events = _decode_trigger_type(64 | 2)
    assert timing == "instead of"


def test_decode_trigger_type_before_with_no_event_bits():
    timing, events = _decode_trigger_type(2)
    assert timing == "before"
    assert events == []


def _canned_routine_trigger_runner():
    # Columns: schema, name, prokind, return_type, language, source,
    # arg_types (IN-only, banner), all_arg_types, proargnames, proargmodes.
    routine_rows = [
        (
            "pr", "calc_total", "f", "numeric", "plpgsql", "CREATE FUNCTION ...",
            ["integer"], ["integer"], ["amount"], None,
        ),
        (
            "pr", "do_thing", "p", "void", "plpgsql", "CREATE PROCEDURE ...",
            [], [], None, None,
        ),
    ]
    trigger_rows = [
        ("pr", "equipment", "trg_audit", 2 | 4 | 16, "audit_log", "CREATE TRIGGER ..."),
    ]
    calls = []

    def runner(params, sql_list):
        calls.append((params, list(sql_list)))
        return [routine_rows, trigger_rows]

    return runner, calls


def test_fetch_routines_and_triggers_passes_routine_trigger_sql():
    runner, calls = _canned_routine_trigger_runner()
    fetch_routines_and_triggers(_PARAMS, runner=runner)
    assert len(calls) == 1
    assert calls[0][1] == ROUTINE_TRIGGER_SQL


def test_fetch_routines_and_triggers_builds_routines_keyed_by_schema_name():
    runner, _ = _canned_routine_trigger_runner()
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)

    routine = schema.routines["pr.calc_total"]
    assert routine == RoutineInfo(
        schema="pr", name="calc_total", arg_types=["integer"], return_type="numeric",
        language="plpgsql", source="CREATE FUNCTION ...", kind="function",
        args=[("amount", "integer")],
    )
    assert schema.routines["pr.do_thing"].kind == "procedure"


def test_fetch_routines_and_triggers_builds_triggers_keyed_by_schema_table_name():
    runner, _ = _canned_routine_trigger_runner()
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)

    trigger = schema.triggers["pr.equipment.trg_audit"]
    assert trigger == TriggerInfo(
        schema="pr", table="equipment", name="trg_audit", timing="before",
        events=["insert", "update"], function_name="audit_log",
        definition="CREATE TRIGGER ...",
    )


def test_fetch_routines_and_triggers_leaves_tables_empty():
    runner, _ = _canned_routine_trigger_runner()
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)
    assert schema.tables == {}


def test_fetch_routines_and_triggers_correlates_out_args_end_to_end():
    """Through the real row-unpacking path: a routine with an OUT argument
    keeps its banner `arg_types` (IN-only) AND gets IN/INOUT-only `args`."""
    routine_rows = [
        (
            "pr", "split_name", "f", "record", "plpgsql", "CREATE FUNCTION ...",
            ["text"],                      # arg_types -- banner, IN only
            ["text", "text", "text"],      # all_arg_types -- IN + 2 OUT
            ["full", "given", "family"],
            ["i", "o", "o"],
        ),
    ]

    def runner(_params, _sql_list):
        return [routine_rows, []]

    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)
    routine = schema.routines["pr.split_name"]
    assert routine.args == [("full", "text")]
    assert routine.arg_types == ["text"]  # banner signature untouched


def test_fetch_routines_and_triggers_start_log_is_redacted(caplog):
    runner, _ = _canned_routine_trigger_runner()
    with caplog.at_level(logging.INFO, logger="pgtp_editor.db.introspect"):
        fetch_routines_and_triggers(_PARAMS, runner=runner)
    messages = [r.message for r in caplog.records]
    assert any("password=***" in m for m in messages)
    assert not any(_PARAMS.password in m for m in messages)
