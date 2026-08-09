# tests/db/test_introspect.py
"""Tests for pgtp_editor.db.introspect using an injected fake `runner`.

psycopg is NEVER imported here: only `run_queries` imports it (lazily, inside
the function) and these tests never call it. `fetch_schema`/`test_connection`
take a `runner=` callable, so the whole suite passes even without psycopg.
"""
import logging

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.introspect import (
    BASELINE_EXTRA_SQL,
    INDEX_SQL,
    ROUTINE_TRIGGER_SQL,
    SCHEMA_SQL,
    BaselineSnapshot,
    ColumnInfo,
    ConstraintInfo,
    DatabaseSchema,
    IndexInfo,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
    TypeInfo,
    _decode_trigger_type,
    _input_args,
    fetch_routines_and_triggers,
    fetch_schema,
    snapshot_for_baseline,
)
from pgtp_editor.db.introspect import test_connection as check_connection

_PARAMS = ConnectionParams(
    host="h", port="5432", database="d", user="u", password="s3cr3t-real-pw"
)


def _canned_runner():
    """Return (runner, calls) — a fake returning pg_catalog-shaped rows.

    relations:   (schema, name, relkind)
    columns:     (schema, table, colname, format_type, attnotnull, default, comment)
    constraints: (schema, table, colname, contype)
    """
    relations = [
        ("pr", "equipment", "r"),
        ("pr", "eq_view", "v"),
        ("pr", "eq_matview", "m"),
        ("pr", "part", "p"),
    ]
    columns = [
        ("pr", "equipment", "id", "integer", True, "nextval('seq'::regclass)", None),
        ("pr", "equipment", "tag", "varchar(255)", False, None, "the equipment tag"),
        ("pr", "equipment", "owner_id", "integer", True, None, None),
        ("pr", "eq_view", "vcol", "text", False, None, None),
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
        comment=None,
    )

    tag_col = schema.column("pr.equipment", "tag")
    assert tag_col.data_type == "varchar(255)"
    assert tag_col.is_pk is False
    assert tag_col.is_fk is False
    assert tag_col.is_nullable is True
    assert tag_col.default is None
    assert tag_col.comment == "the equipment tag"

    owner_col = schema.column("pr.equipment", "owner_id")
    assert owner_col.is_fk is True
    assert owner_col.is_pk is False
    assert owner_col.is_nullable is False


def test_fetch_schema_captures_fk_target():
    """FK constraint rows carrying a referenced schema.table.column populate
    ColumnInfo.fk_target; PK rows (4-tuple or None ref) leave it None."""
    relations = [("pr", "part", "r")]
    columns = [
        ("pr", "part", "id", "integer", True, None, None),
        ("pr", "part", "equipment_id", "integer", False, None, None),
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


def test_columns_sql_sources_column_comments():
    """The widened query must actually select `col_description` keyed on the
    column's own `attrelid`/`attnum` (2026-08-05, §18.1's Properties-panel
    widening) -- not just thread a `comment` field through row-unpacking
    without the catalog function that produces it."""
    columns_sql = SCHEMA_SQL[1]
    assert "col_description(a.attrelid, a.attnum)" in columns_sql


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


def _canned_routine_trigger_runner(relations=None, columns=None, constraints=None, indexes=None):
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
        return [
            routine_rows,
            trigger_rows,
            relations if relations is not None else [],
            columns if columns is not None else [],
            constraints if constraints is not None else [],
            indexes if indexes is not None else [],
        ]

    return runner, calls


def test_fetch_routines_and_triggers_passes_routine_trigger_schema_and_index_sql():
    """The widened fetch (§18.6, widened again by FQ-025) runs all three query
    sets in one round trip -- routines/triggers, the same three queries
    `fetch_schema` runs, and the index query."""
    runner, calls = _canned_routine_trigger_runner()
    fetch_routines_and_triggers(_PARAMS, runner=runner)
    assert len(calls) == 1
    assert calls[0][1] == list(ROUTINE_TRIGGER_SQL) + list(SCHEMA_SQL) + list(INDEX_SQL)


def test_fetch_routines_and_triggers_builds_routines_keyed_by_signature():
    runner, _ = _canned_routine_trigger_runner()
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)

    routine = schema.routines["pr.calc_total(integer)"]
    assert routine == RoutineInfo(
        schema="pr", name="calc_total", arg_types=["integer"], return_type="numeric",
        language="plpgsql", source="CREATE FUNCTION ...", kind="function",
        args=[("amount", "integer")],
    )
    # A zero-argument routine keys with empty parens, never bare `pr.do_thing`.
    assert schema.routines["pr.do_thing()"].kind == "procedure"


def test_routine_signature_renders_zero_one_and_many_arguments():
    """The one spelling every consumer shares (BUG-018).

    Zero arguments render as `pr.f()` -- **empty parens, never bare `pr.f`**.
    That is the common case, so a divergence here would be everywhere and
    invisible, and it is exactly what distinguishes `f()` from `f(integer)`.
    """
    assert RoutineInfo(schema="pr", name="f").signature == "pr.f()"
    assert RoutineInfo(schema="pr", name="f", arg_types=["integer"]).signature == "pr.f(integer)"
    # Joiner is ", " -- comma + space -- and the source is `arg_types` (types
    # only), not `args` (name/type pairs).
    many = RoutineInfo(
        schema="pr", name="f", arg_types=["integer", "text"],
        args=[("a", "integer"), ("b", "text")],
    )
    assert many.signature == "pr.f(integer, text)"


def test_fetch_routines_and_triggers_keeps_both_overloads_of_one_name():
    """`pg_proc` holds one row per overload; both must survive (BUG-018).

    Keyed by `schema.name` the second row silently overwrote the first and
    every consumer saw only one of the two functions.
    """
    routine_rows = [
        ("pr", "fmt", "f", "text", "plpgsql", "BODY-INT", ["integer"], ["integer"], ["n"], None),
        ("pr", "fmt", "f", "text", "plpgsql", "BODY-TEXT", ["text"], ["text"], ["s"], None),
    ]

    def runner(_params, _sql_list):
        return [routine_rows, [], [], [], [], []]

    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)

    assert len(schema.routines) == 2
    assert set(schema.routines) == {"pr.fmt(integer)", "pr.fmt(text)"}
    # Each overload keeps its own body -- not the last row's.
    assert schema.routines["pr.fmt(integer)"].source == "BODY-INT"
    assert schema.routines["pr.fmt(text)"].source == "BODY-TEXT"


def test_fetch_routines_and_triggers_builds_triggers_keyed_by_schema_table_name():
    runner, _ = _canned_routine_trigger_runner()
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)

    trigger = schema.triggers["pr.equipment.trg_audit"]
    assert trigger == TriggerInfo(
        schema="pr", table="equipment", name="trg_audit", timing="before",
        events=["insert", "update"], function_name="audit_log",
        definition="CREATE TRIGGER ...",
    )


def test_fetch_routines_and_triggers_populates_tables():
    """Superseded (§18.6, §28): the widened fetch also runs `SCHEMA_SQL` and
    populates `.tables`, exactly like `fetch_schema` does -- so DDL Explorer's
    one connect-time fetch now serves completion's table/column data too."""
    relations = [("pr", "equipment", "r")]
    columns = [("pr", "equipment", "id", "integer", True, None, None)]
    constraints = [("pr", "equipment", "id", "p")]
    runner, _ = _canned_routine_trigger_runner(
        relations=relations, columns=columns, constraints=constraints
    )
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)
    assert set(schema.tables) == {"pr.equipment"}
    table = schema.tables["pr.equipment"]
    assert table.kind == "table"
    assert table.columns == [
        ColumnInfo(
            name="id", data_type="integer", is_pk=True, is_fk=False,
            is_nullable=False, default=None, comment=None,
        )
    ]


def test_fetch_routines_and_triggers_tables_empty_when_no_relations():
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
        return [routine_rows, [], [], [], [], []]

    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)
    # The key uses the IN-only `arg_types` -- `(text)`, not the three
    # `all_arg_types` -- because that is what PostgreSQL identifies it by.
    routine = schema.routines["pr.split_name(text)"]
    assert routine.args == [("full", "text")]
    assert routine.arg_types == ["text"]  # banner signature untouched


def test_fetch_routines_and_triggers_start_log_is_redacted(caplog):
    runner, _ = _canned_routine_trigger_runner()
    with caplog.at_level(logging.INFO, logger="pgtp_editor.db.introspect"):
        fetch_routines_and_triggers(_PARAMS, runner=runner)
    messages = [r.message for r in caplog.records]
    assert any("password=***" in m for m in messages)
    assert not any(_PARAMS.password in m for m in messages)


# --- snapshot_for_baseline / BaselineSnapshot (§18.5 D2 "recorded gap") ------


def _canned_baseline_runner(
    relations=None, columns=None, constraints=None, viewdefs=None, types=None
):
    routine_rows = [
        (
            "pr", "calc_total", "f", "numeric", "plpgsql", "CREATE FUNCTION ...",
            ["integer"], ["integer"], ["amount"], None,
        ),
    ]
    trigger_rows = [
        ("pr", "equipment", "trg_audit", 2 | 4 | 16, "audit_log", "CREATE TRIGGER ..."),
    ]
    calls = []

    def runner(params, sql_list):
        calls.append((params, list(sql_list)))
        return [
            routine_rows,
            trigger_rows,
            relations if relations is not None else [],
            columns if columns is not None else [],
            constraints if constraints is not None else [],
            viewdefs if viewdefs is not None else [],
            types if types is not None else [],
        ]

    return runner, calls


def test_snapshot_for_baseline_passes_all_three_query_sets_in_one_round_trip():
    runner, calls = _canned_baseline_runner()
    snapshot_for_baseline(_PARAMS, runner=runner)
    assert len(calls) == 1  # ONE round trip, not several separate connections
    assert calls[0][0] is _PARAMS
    expected = list(ROUTINE_TRIGGER_SQL) + list(SCHEMA_SQL) + list(BASELINE_EXTRA_SQL)
    assert calls[0][1] == expected


def test_snapshot_for_baseline_returns_a_baseline_snapshot_wrapping_a_database_schema():
    runner, _ = _canned_baseline_runner()
    snapshot = snapshot_for_baseline(_PARAMS, runner=runner)
    assert isinstance(snapshot, BaselineSnapshot)
    assert isinstance(snapshot.schema, DatabaseSchema)


def test_snapshot_for_baseline_populates_tables_routines_and_triggers():
    relations = [("pr", "equipment", "r")]
    columns = [("pr", "equipment", "id", "integer", True, None, None)]
    constraints = [("pr", "equipment", "id", "p")]
    runner, _ = _canned_baseline_runner(relations=relations, columns=columns, constraints=constraints)
    snapshot = snapshot_for_baseline(_PARAMS, runner=runner)
    assert set(snapshot.schema.tables) == {"pr.equipment"}
    assert "pr.calc_total(integer)" in snapshot.schema.routines
    assert "pr.equipment.trg_audit" in snapshot.schema.triggers


def test_snapshot_for_baseline_attaches_view_definitions_to_table_info():
    relations = [("pr", "eq_view", "v"), ("pr", "eq_matview", "m")]
    viewdefs = [
        ("pr", "eq_view", "SELECT id FROM pr.equipment;"),
        ("pr", "eq_matview", "SELECT id, tag FROM pr.equipment;"),
    ]
    runner, _ = _canned_baseline_runner(relations=relations, viewdefs=viewdefs)
    snapshot = snapshot_for_baseline(_PARAMS, runner=runner)
    assert snapshot.schema.tables["pr.eq_view"].view_definition == "SELECT id FROM pr.equipment;"
    assert (
        snapshot.schema.tables["pr.eq_matview"].view_definition
        == "SELECT id, tag FROM pr.equipment;"
    )


def test_snapshot_for_baseline_plain_table_has_no_view_definition():
    relations = [("pr", "equipment", "r")]
    runner, _ = _canned_baseline_runner(relations=relations)
    snapshot = snapshot_for_baseline(_PARAMS, runner=runner)
    assert snapshot.schema.tables["pr.equipment"].view_definition is None


def test_snapshot_for_baseline_builds_domain_type_info():
    types = [
        ("pr", "positive_int", "d", "integer", True, [], []),
    ]
    runner, _ = _canned_baseline_runner(types=types)
    snapshot = snapshot_for_baseline(_PARAMS, runner=runner)
    info = snapshot.schema.types["pr.positive_int"]
    assert info == TypeInfo(
        schema="pr", name="positive_int", kind="domain",
        base_type="integer", not_null=True, attributes=[],
    )


def test_snapshot_for_baseline_domain_not_null_false():
    types = [("pr", "nickname", "d", "text", False, [], [])]
    runner, _ = _canned_baseline_runner(types=types)
    snapshot = snapshot_for_baseline(_PARAMS, runner=runner)
    assert snapshot.schema.types["pr.nickname"].not_null is False


def test_snapshot_for_baseline_builds_composite_type_info():
    types = [
        ("pr", "full_address", "c", None, False, ["street", "city"], ["text", "text"]),
    ]
    runner, _ = _canned_baseline_runner(types=types)
    snapshot = snapshot_for_baseline(_PARAMS, runner=runner)
    info = snapshot.schema.types["pr.full_address"]
    assert info == TypeInfo(
        schema="pr", name="full_address", kind="composite",
        base_type=None, not_null=False,
        attributes=[("street", "text"), ("city", "text")],
    )
    assert info.qualified_name == "pr.full_address"


def test_snapshot_for_baseline_types_default_empty_when_no_type_rows():
    runner, _ = _canned_baseline_runner()
    snapshot = snapshot_for_baseline(_PARAMS, runner=runner)
    assert snapshot.schema.types == {}


def test_baseline_extra_sql_has_viewdef_and_type_queries():
    assert len(BASELINE_EXTRA_SQL) == 2
    viewdef_sql, types_sql = BASELINE_EXTRA_SQL
    assert "pg_get_viewdef" in viewdef_sql
    assert "relkind IN ('v', 'm')" in viewdef_sql
    assert "typtype IN ('d', 'c')" in types_sql


def test_snapshot_for_baseline_start_log_is_redacted(caplog):
    runner, _ = _canned_baseline_runner()
    with caplog.at_level(logging.INFO, logger="pgtp_editor.db.introspect"):
        snapshot_for_baseline(_PARAMS, runner=runner)
    messages = [r.message for r in caplog.records]
    assert any("password=***" in m for m in messages)
    assert not any(_PARAMS.password in m for m in messages)


def test_table_info_view_definition_defaults_to_none():
    """Backward compatibility: existing construction sites that never pass
    `view_definition` still work and get None."""
    table = TableInfo(name="s.t", kind="table", columns=[])
    assert table.view_definition is None


def test_database_schema_types_defaults_empty_and_is_additive():
    """Pre-existing callers that construct `DatabaseSchema` without `types=`
    must not break -- mirrors the same contract test for routines/triggers."""
    schema = DatabaseSchema(tables={})
    assert schema.types == {}


# --- Named constraints & indexes (FQ-025 slice 2) ---------------------------
# Constraint rows are now 7-wide:
#   (schema, table, colname, contype, fk_target, conname, constraintdef)
# Index rows (INDEX_SQL) are 9-wide:
#   (schema, table, index_name, method, is_unique, is_primary, definition,
#    [columns], backing_constraint_name)


def _constraint_row(table, column, contype, name, definition="", fk_target=None):
    return ("pr", table, column, contype, fk_target, name, definition)


def _schema_with_constraints(constraint_rows, relations=None, columns=None):
    def runner(_params, _sql_list):
        return [
            relations if relations is not None else [("pr", "equipment", "r")],
            columns if columns is not None else [],
            constraint_rows,
        ]

    return fetch_schema(_PARAMS, runner=runner)


def test_constraint_names_surface_keyed_by_schema_table_name():
    """`con.conname` was never selected before FQ-025, so no picker could
    exist. It must now arrive keyed the way triggers are (`schema.table.name`)."""
    schema = _schema_with_constraints(
        [_constraint_row("equipment", "id", "p", "equipment_pkey")]
    )
    assert set(schema.constraints) == {"pr.equipment.equipment_pkey"}
    info = schema.constraints["pr.equipment.equipment_pkey"]
    assert info == ConstraintInfo(
        schema="pr", table="equipment", name="equipment_pkey",
        kind="primary key", columns=["id"], definition="",
    )
    assert info.qualified_name == "pr.equipment.equipment_pkey"
    assert info.table_name == "pr.equipment"


def test_every_newly_included_contype_is_classified():
    """'u', 'c' and 'x' join 'p'/'f' -- and each maps to its own lowercase
    prose kind, because the picker shows the type next to the name."""
    schema = _schema_with_constraints(
        [
            _constraint_row("equipment", "id", "p", "eq_pkey"),
            _constraint_row("equipment", "owner_id", "f", "eq_owner_fkey",
                            fk_target="pr.owner.id"),
            _constraint_row("equipment", "tag", "u", "eq_tag_key"),
            _constraint_row("equipment", "qty", "c", "eq_qty_check",
                            definition="CHECK ((qty > 0))"),
            _constraint_row("equipment", "period", "x", "eq_period_excl"),
        ]
    )
    kinds = {name: c.kind for name, c in schema.constraints.items()}
    assert kinds == {
        "pr.equipment.eq_pkey": "primary key",
        "pr.equipment.eq_owner_fkey": "foreign key",
        "pr.equipment.eq_tag_key": "unique",
        "pr.equipment.eq_qty_check": "check",
        "pr.equipment.eq_period_excl": "exclude",
    }
    assert schema.constraints["pr.equipment.eq_qty_check"].definition == "CHECK ((qty > 0))"


def test_multi_column_constraint_groups_its_columns_in_conkey_order():
    """`_CONSTRAINTS_SQL` emits one row per (constraint, column); the columns
    regroup onto ONE ConstraintInfo, in the arrival order the query's
    `ORDER BY ..., k.i` makes conkey order."""
    schema = _schema_with_constraints(
        [
            _constraint_row("equipment", "site", "u", "eq_site_tag_key"),
            _constraint_row("equipment", "tag", "u", "eq_site_tag_key"),
        ]
    )
    assert len(schema.constraints) == 1
    assert schema.constraints["pr.equipment.eq_site_tag_key"].columns == ["site", "tag"]


def test_check_constraint_with_no_columns_is_still_captured():
    """A table-level `CHECK (true)` has a NULL conkey -- the LEFT JOIN keeps
    the row, and the constraint is still droppable, so it must be listed. Its
    `definition` is the only thing a picker can show for it."""
    schema = _schema_with_constraints(
        [("pr", "equipment", None, "c", None, "eq_sane", "CHECK (true)")]
    )
    info = schema.constraints["pr.equipment.eq_sane"]
    assert info.columns == []
    assert info.definition == "CHECK (true)"
    assert info.kind == "check"


def test_table_with_no_constraints_and_no_indexes_yields_empty_collections():
    runner, _ = _canned_routine_trigger_runner(
        relations=[("pr", "bare", "r")],
        columns=[("pr", "bare", "note", "text", False, None, None)],
        constraints=[],
        indexes=[],
    )
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)
    assert schema.tables["pr.bare"].columns  # the table itself is still there
    assert schema.constraints == {}
    assert schema.indexes == {}
    assert schema.constraints_for("pr.bare") == []
    assert schema.indexes_for("pr.bare") == []


def test_pre_fq025_constraint_rows_without_a_name_are_tolerated():
    """The 4-/5-tuple canned rows used across the suite (and every existing
    consumer of the PK/FK column flags) must keep working: no conname means
    no ConstraintInfo, and the is_pk/is_fk flags are unaffected."""
    schema = _schema_with_constraints(
        [("pr", "equipment", "id", "p"), ("pr", "equipment", "owner_id", "f", "pr.o.id")],
        columns=[
            ("pr", "equipment", "id", "integer", True, None, None),
            ("pr", "equipment", "owner_id", "integer", True, None, None),
        ],
    )
    assert schema.constraints == {}
    assert schema.column("pr.equipment", "id").is_pk is True
    assert schema.column("pr.equipment", "owner_id").is_fk is True


def test_constraints_for_filters_by_table():
    schema = _schema_with_constraints(
        [
            _constraint_row("equipment", "id", "p", "eq_pkey"),
            _constraint_row("part", "id", "p", "part_pkey"),
        ],
        relations=[("pr", "equipment", "r"), ("pr", "part", "r")],
    )
    assert [c.name for c in schema.constraints_for("pr.equipment")] == ["eq_pkey"]
    assert [c.name for c in schema.constraints_for("pr.part")] == ["part_pkey"]
    assert schema.constraints_for("pr.nope") == []


def test_constraints_sql_selects_conname_and_the_widened_contypes():
    """Pin the query itself, not just the row-unpacking: a `conname` threaded
    through Python without being SELECTed would silently list nothing."""
    constraints_sql = SCHEMA_SQL[2]
    assert "con.conname" in constraints_sql
    assert "pg_get_constraintdef(con.oid)" in constraints_sql
    assert "con.contype IN ('p', 'f', 'u', 'c', 'x')" in constraints_sql
    # A NULL conkey (table-level CHECK) must not drop the constraint row.
    assert "LEFT JOIN generate_subscripts(con.conkey, 1)" in constraints_sql


def _index_row(name, columns, is_unique=False, is_primary=False,
               method="btree", constraint_name=None, table="equipment"):
    return (
        "pr", table, name, method, is_unique, is_primary,
        f"CREATE INDEX {name} ...", columns, constraint_name,
    )


def test_indexes_are_built_keyed_by_schema_and_index_name():
    runner, _ = _canned_routine_trigger_runner(
        relations=[("pr", "equipment", "r")],
        indexes=[_index_row("equipment_tag_idx", ["tag"])],
    )
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)
    assert set(schema.indexes) == {"pr.equipment_tag_idx"}
    info = schema.indexes["pr.equipment_tag_idx"]
    assert info == IndexInfo(
        schema="pr", table="equipment", name="equipment_tag_idx",
        columns=["tag"], is_unique=False, is_primary=False, method="btree",
        definition="CREATE INDEX equipment_tag_idx ...", constraint_name=None,
    )
    assert info.table_name == "pr.equipment"
    assert info.qualified_name == "pr.equipment_tag_idx"


def test_constraint_backed_index_is_marked_not_silently_offered():
    """A PK's implicit index cannot be `DROP INDEX`ed -- Postgres refuses. It
    is captured (so it is not a mystery omission) but carries the backing
    constraint's name, and a Drop-index picker filters on
    `is_constraint_backed`."""
    runner, _ = _canned_routine_trigger_runner(
        relations=[("pr", "equipment", "r")],
        indexes=[
            _index_row("equipment_pkey", ["id"], is_unique=True, is_primary=True,
                       constraint_name="equipment_pkey"),
            _index_row("equipment_tag_key", ["tag"], is_unique=True,
                       constraint_name="equipment_tag_key"),
            _index_row("equipment_tag_idx", ["lower(tag)"]),
        ],
    )
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)

    pk_index = schema.indexes["pr.equipment_pkey"]
    unique_index = schema.indexes["pr.equipment_tag_key"]
    standalone = schema.indexes["pr.equipment_tag_idx"]

    assert pk_index.is_constraint_backed is True
    assert pk_index.constraint_name == "equipment_pkey"
    assert pk_index.is_primary is True
    # A UNIQUE constraint's index is equally undroppable.
    assert unique_index.is_constraint_backed is True
    assert unique_index.is_primary is False

    assert standalone.constraint_name is None
    assert standalone.is_constraint_backed is False
    # An expression index keeps its expression text as its "column".
    assert standalone.columns == ["lower(tag)"]

    # `indexes_for` returns EVERYTHING; the droppable filter is the caller's.
    assert len(schema.indexes_for("pr.equipment")) == 3
    droppable = [i for i in schema.indexes_for("pr.equipment") if not i.is_constraint_backed]
    assert [i.name for i in droppable] == ["equipment_tag_idx"]


def test_index_unique_flag_and_method_survive():
    """The create side needs unique/method; the drop side shows them so the
    user knows which index they are dropping."""
    runner, _ = _canned_routine_trigger_runner(
        relations=[("pr", "equipment", "r")],
        indexes=[
            _index_row("eq_doc_gin", ["doc"], method="gin"),
            _index_row("eq_tag_uq", ["tag"], is_unique=True),
        ],
    )
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)
    assert schema.indexes["pr.eq_doc_gin"].method == "gin"
    assert schema.indexes["pr.eq_doc_gin"].is_unique is False
    assert schema.indexes["pr.eq_tag_uq"].is_unique is True
    # A unique INDEX (not a unique CONSTRAINT) IS droppable.
    assert schema.indexes["pr.eq_tag_uq"].is_constraint_backed is False


def test_multi_column_index_keeps_column_order():
    runner, _ = _canned_routine_trigger_runner(
        relations=[("pr", "equipment", "r")],
        indexes=[_index_row("eq_site_tag_idx", ["site", "tag"])],
    )
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)
    assert schema.indexes["pr.eq_site_tag_idx"].columns == ["site", "tag"]


def test_index_sql_is_one_query_sourcing_the_droppability_signal():
    assert len(INDEX_SQL) == 1
    index_sql = INDEX_SQL[0]
    assert "pg_get_indexdef" in index_sql
    assert "i.indisunique" in index_sql
    assert "i.indisprimary" in index_sql
    assert "am.amname" in index_sql
    # The constraint-backed distinction comes from pg_constraint.conindid.
    assert "con.conindid = i.indexrelid" in index_sql
    # INCLUDE columns are excluded from `columns` by bounding on indnkeyatts.
    assert "i.indnkeyatts" in index_sql


def test_fetch_routines_and_triggers_also_populates_named_constraints():
    runner, calls = _canned_routine_trigger_runner(
        relations=[("pr", "equipment", "r")],
        constraints=[_constraint_row("equipment", "id", "p", "equipment_pkey")],
    )
    schema = fetch_routines_and_triggers(_PARAMS, runner=runner)
    assert "pr.equipment.equipment_pkey" in schema.constraints
    # Still ONE round trip -- constraints ride the rows already fetched.
    assert len(calls) == 1


def test_fetch_schema_query_contract_is_unchanged_by_the_widening():
    """FQ-025 adds NO query to DB Check's fetch: `.constraints` is built from
    the constraint rows `fetch_schema` already retrieves."""
    runner, calls = _canned_runner()
    fetch_schema(_PARAMS, runner=runner)
    assert calls[0][1] == list(SCHEMA_SQL)
    assert len(calls[0][1]) == 3


def test_fetch_schema_leaves_indexes_empty():
    """Only `fetch_routines_and_triggers` runs `INDEX_SQL` -- DB Check has no
    use for indexes and pays nothing for them."""
    runner, _ = _canned_runner()
    assert fetch_schema(_PARAMS, runner=runner).indexes == {}


def test_snapshot_for_baseline_populates_constraints_but_not_indexes():
    """The sandbox baseline is "catalog shape, not full fidelity": it gets the
    named constraints for free with the rows it already fetches, and does NOT
    grow an index query."""
    relations = [("pr", "equipment", "r")]
    constraints = [_constraint_row("equipment", "id", "p", "equipment_pkey")]
    runner, calls = _canned_baseline_runner(relations=relations, constraints=constraints)
    snapshot = snapshot_for_baseline(_PARAMS, runner=runner)
    assert "pr.equipment.equipment_pkey" in snapshot.schema.constraints
    assert snapshot.schema.indexes == {}
    expected = list(ROUTINE_TRIGGER_SQL) + list(SCHEMA_SQL) + list(BASELINE_EXTRA_SQL)
    assert calls[0][1] == expected


def test_database_schema_constraints_and_indexes_default_empty_and_are_additive():
    """Both new fields are trailing and defaulted, so positional/`tables=`-only
    construction sites across the codebase keep working."""
    table = TableInfo("s.t", "table", [])
    for schema in (DatabaseSchema({"s.t": table}), DatabaseSchema(), DatabaseSchema(tables={})):
        assert schema.constraints == {}
        assert schema.indexes == {}
        assert schema.constraints_for("s.t") == []
        assert schema.indexes_for("s.t") == []


def test_constraint_and_index_info_defaults():
    """Mirrors the other dataclass back-compat tests: every field past the
    identity is defaulted, and the mutable ones are per-instance."""
    constraint = ConstraintInfo(schema="s", table="t", name="c", kind="check")
    assert constraint.columns == []
    assert constraint.definition == ""
    assert ConstraintInfo(schema="s", table="t", name="d", kind="check").columns is not (
        constraint.columns
    )

    index = IndexInfo(schema="s", table="t", name="i")
    assert index.columns == []
    assert index.is_unique is False
    assert index.is_primary is False
    assert index.method == ""
    assert index.definition == ""
    assert index.constraint_name is None
    assert index.is_constraint_backed is False
    assert IndexInfo(schema="s", table="t", name="j").columns is not index.columns
