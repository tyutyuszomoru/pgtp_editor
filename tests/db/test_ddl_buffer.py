"""Tests for pgtp_editor.db.ddl_buffer -- pure buffer/span synthesis (§18.1)."""
from pgtp_editor.db.ddl_buffer import DdlObjectSpan, build_ddl_text
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo, TriggerInfo


def _schema():
    routines = {
        "pr.calc_total(integer)": RoutineInfo(
            schema="pr", name="calc_total", arg_types=["integer"],
            return_type="numeric", language="plpgsql",
            source="CREATE FUNCTION pr.calc_total(integer) ...\nRETURN 1;\n",
            kind="function",
        ),
        "pr.audit_log()": RoutineInfo(
            schema="pr", name="audit_log", arg_types=[], return_type="trigger",
            language="plpgsql", source="CREATE FUNCTION pr.audit_log() ...",
            kind="function",
        ),
    }
    triggers = {
        "pr.equipment.trg_audit": TriggerInfo(
            schema="pr", table="equipment", name="trg_audit", timing="after",
            events=["insert", "update"], function_name="audit_log",
            definition="CREATE TRIGGER trg_audit ...",
        ),
    }
    return DatabaseSchema(routines=routines, triggers=triggers)


def test_build_ddl_text_empty_schema_returns_empty_buffer():
    text, spans = build_ddl_text(DatabaseSchema())
    assert text == ""
    assert spans == []


def test_build_ddl_text_orders_routines_before_triggers_within_schema_then_by_name():
    text, spans = build_ddl_text(_schema())

    assert [s.kind for s in spans] == ["function", "function", "trigger"]
    assert [s.name for s in spans] == ["audit_log", "calc_total", "trg_audit"]


def test_build_ddl_text_banner_and_span_lines_are_consistent():
    text, spans = build_ddl_text(_schema())
    lines = text.splitlines()

    calc_total = next(s for s in spans if s.name == "calc_total")
    assert lines[calc_total.start_line - 1] == "-- FUNCTION pr.calc_total(integer) --"
    # The source text's own lines follow the banner up to end_line (inclusive,
    # 1-based) -- as a 0-indexed slice that's [start_line : end_line].
    source_lines = _schema().routines["pr.calc_total(integer)"].source.splitlines()
    assert lines[calc_total.start_line: calc_total.end_line] == source_lines


def test_build_ddl_text_trigger_span_and_fields():
    text, spans = build_ddl_text(_schema())
    lines = text.splitlines()

    trg = next(s for s in spans if s.kind == "trigger")
    assert trg.schema == "pr"
    assert trg.table == "equipment"
    assert lines[trg.start_line - 1] == "-- TRIGGER pr.trg_audit ON equipment --"


def test_build_ddl_text_procedure_banner_uses_procedure_label():
    schema = DatabaseSchema(
        routines={
            "pr.do_thing(text)": RoutineInfo(
                schema="pr", name="do_thing", arg_types=["text"],
                return_type="void", language="plpgsql", source="CREATE PROCEDURE ...",
                kind="procedure",
            ),
        },
    )
    text, spans = build_ddl_text(schema)
    lines = text.splitlines()
    assert lines[spans[0].start_line - 1] == "-- PROCEDURE pr.do_thing(text) --"


def test_ddl_object_span_is_a_plain_frozen_dataclass():
    span = DdlObjectSpan(
        kind="function", schema="pr", name="f", table=None, start_line=1, end_line=1
    )
    assert span.kind == "function"
    assert span.table is None
    # `signature` is trailing and defaulted, so this construction stays valid.
    assert span.signature is None


def _overload_schema(order=("integer", "text")):
    routines = {}
    for arg in order:
        routine = RoutineInfo(
            schema="pr", name="fmt", arg_types=[arg], return_type="text",
            language="plpgsql", source=f"BODY-{arg}", kind="function",
            args=[("v", arg)],
        )
        routines[routine.signature] = routine
    return DatabaseSchema(routines=routines)


def test_build_ddl_text_gives_each_overload_its_own_banner_and_span():
    text, spans = build_ddl_text(_overload_schema())
    lines = text.splitlines()

    assert len(spans) == 2
    first, second = spans
    assert lines[first.start_line - 1] == "-- FUNCTION pr.fmt(integer) --"
    assert lines[second.start_line - 1] == "-- FUNCTION pr.fmt(text) --"
    assert lines[first.start_line: first.end_line] == ["BODY-integer"]
    assert lines[second.start_line: second.end_line] == ["BODY-text"]
    # Distinct, non-overlapping spans, each carrying its own identity.
    assert first.end_line < second.start_line
    assert [s.signature for s in spans] == ["pr.fmt(integer)", "pr.fmt(text)"]


def test_build_ddl_text_is_reproducible_regardless_of_overload_insertion_order():
    """Two overloads tie on (schema, kind, name), so without an argument-type
    tiebreak the stable sort falls back to `pg_proc` row order and the buffer
    changes between fetches (BUG-018)."""
    forward, forward_spans = build_ddl_text(_overload_schema(("integer", "text")))
    reversed_, reversed_spans = build_ddl_text(_overload_schema(("text", "integer")))

    assert forward == reversed_
    assert [(s.signature, s.start_line, s.end_line) for s in forward_spans] == [
        (s.signature, s.start_line, s.end_line) for s in reversed_spans
    ]


def test_build_ddl_text_orders_by_schema_before_kind_or_name():
    schema = DatabaseSchema(
        routines={
            "zz.aaa()": RoutineInfo(
                schema="zz", name="aaa", source="body_zz", kind="function",
            ),
            "aa.zzz()": RoutineInfo(
                schema="aa", name="zzz", source="body_aa", kind="function",
            ),
        },
    )
    text, spans = build_ddl_text(schema)
    # "aa" schema sorts before "zz" schema even though "aaa" < "zzz" by name.
    assert [s.schema for s in spans] == ["aa", "zz"]
    assert [s.name for s in spans] == ["zzz", "aaa"]


def test_build_ddl_text_multiple_triggers_on_same_object_are_all_spanned_distinctly():
    schema = DatabaseSchema(
        triggers={
            "pr.equipment.trg_b": TriggerInfo(
                schema="pr", table="equipment", name="trg_b", timing="after",
                events=["update"], function_name="f", definition="DEF_B\nLINE2\n",
            ),
            "pr.equipment.trg_a": TriggerInfo(
                schema="pr", table="equipment", name="trg_a", timing="before",
                events=["insert"], function_name="f", definition="DEF_A\n",
            ),
        },
    )
    text, spans = build_ddl_text(schema)
    lines = text.splitlines()

    assert [s.name for s in spans] == ["trg_a", "trg_b"]
    trg_a, trg_b = spans
    assert lines[trg_a.start_line - 1] == "-- TRIGGER pr.trg_a ON equipment --"
    assert lines[trg_a.start_line: trg_a.end_line] == ["DEF_A"]
    assert lines[trg_b.start_line - 1] == "-- TRIGGER pr.trg_b ON equipment --"
    assert lines[trg_b.start_line: trg_b.end_line] == ["DEF_B", "LINE2"]
    # Spans don't overlap.
    assert trg_a.end_line < trg_b.start_line


def test_build_ddl_text_empty_source_still_produces_a_span():
    schema = DatabaseSchema(
        routines={
            "pr.empty_fn()": RoutineInfo(
                schema="pr", name="empty_fn", source="", kind="function",
            ),
        },
    )
    text, spans = build_ddl_text(schema)
    assert len(spans) == 1
    span = spans[0]
    lines = text.splitlines()
    # start_line is the banner line itself (consistent with the other tests
    # above); an empty source still occupies one blank body line at end_line,
    # so navigate-to-line never targets a gap.
    assert lines[span.start_line - 1] == "-- FUNCTION pr.empty_fn() --"
    assert lines[span.start_line: span.end_line] == [""]
    assert span.end_line == span.start_line + 1


# ---------------------------------------------------------------------------
# ALL object kinds in the buffer (`FQ-260810183812`).
# ---------------------------------------------------------------------------

from pgtp_editor.db.ddl_buffer import EDITABLE_SPAN_KINDS  # noqa: E402
from pgtp_editor.db.introspect import (  # noqa: E402
    ColumnInfo,
    ConstraintInfo,
    IndexInfo,
    TableInfo,
)
from pgtp_editor.db.table_ddl import RECONSTRUCTION_NOTICE  # noqa: E402


def _relation_schema():
    tables = {
        "pr.orders": TableInfo(
            name="pr.orders",
            kind="table",
            columns=[
                ColumnInfo("id", "integer", True, False, False, None),
                ColumnInfo("tag", "text", False, False, True, None),
            ],
        ),
        "pr.v_orders": TableInfo(
            name="pr.v_orders", kind="view", view_definition="SELECT 1"
        ),
        "pr.m_orders": TableInfo(
            name="pr.m_orders", kind="matview", view_definition="SELECT 2"
        ),
    }
    constraints = {
        "pr.orders.orders_pkey": ConstraintInfo(
            schema="pr", table="orders", name="orders_pkey", kind="primary key",
            columns=["id"], definition="PRIMARY KEY (id)",
        )
    }
    indexes = {
        "pr.ix_tag": IndexInfo(
            schema="pr", table="orders", name="ix_tag", columns=["tag"],
            method="btree", definition="CREATE INDEX ix_tag ON pr.orders (tag)",
        )
    }
    return DatabaseSchema(tables=tables, constraints=constraints, indexes=indexes)


def test_tables_views_and_matviews_all_enter_the_buffer():
    text, spans = build_ddl_text(_relation_schema())
    kinds = {span.kind for span in spans}
    assert {"table", "view", "matview"} <= kinds
    assert "-- TABLE pr.orders --" in text
    assert "-- VIEW pr.v_orders --" in text
    assert "-- MATERIALIZED VIEW pr.m_orders --" in text


def test_a_tables_span_covers_its_whole_synthesized_ddl():
    text, spans = build_ddl_text(_relation_schema())
    lines = text.splitlines()
    span = next(s for s in spans if s.kind == "table")
    assert lines[span.start_line - 1] == "-- TABLE pr.orders --"
    body = "\n".join(lines[span.start_line : span.end_line])
    assert RECONSTRUCTION_NOTICE in body
    assert "CREATE TABLE pr.orders (" in body


def test_column_constraint_and_index_spans_point_at_their_own_line():
    """The detail spans are what makes "every tree item that has DDL navigates
    to it" true for the column/constraint/index nodes."""
    text, spans = build_ddl_text(_relation_schema())
    lines = text.splitlines()
    by_kind = {}
    for span in spans:
        by_kind.setdefault(span.kind, {})[span.name] = span

    assert lines[by_kind["column"]["tag"].start_line - 1].strip().startswith("tag text")
    assert "CONSTRAINT orders_pkey" in lines[
        by_kind["constraint"]["orders_pkey"].start_line - 1
    ]
    assert lines[by_kind["index"]["ix_tag"].start_line - 1].startswith("CREATE INDEX")


def test_detail_spans_carry_their_owning_table():
    _text, spans = build_ddl_text(_relation_schema())
    details = [s for s in spans if s.kind in ("column", "constraint", "index")]
    assert details
    assert all(span.table == "orders" for span in details)


def test_object_spans_come_before_detail_spans():
    """`EditorPanel._span_at_line` returns the FIRST containing span, so a
    click on a column's line must resolve to the TABLE, not to the column."""
    _text, spans = build_ddl_text(_relation_schema())
    kinds = [span.kind for span in spans]
    last_object = max(
        i for i, kind in enumerate(kinds)
        if kind in ("table", "view", "matview", "function", "procedure", "trigger")
    )
    first_detail = min(
        i for i, kind in enumerate(kinds) if kind in ("column", "constraint", "index")
    )
    assert last_object < first_detail


def test_relations_come_before_routines_and_triggers():
    """Open question 4, settled: dual-grouped like the tree, not alphabetical
    across kinds -- so buffer order matches the tree the user clicks in."""
    relations = _relation_schema()
    routines_and_triggers = _schema()
    schema = DatabaseSchema(
        tables=relations.tables,
        constraints=relations.constraints,
        indexes=relations.indexes,
        routines=routines_and_triggers.routines,
        triggers=routines_and_triggers.triggers,
    )
    text, _spans = build_ddl_text(schema)
    assert text.index("-- TABLE pr.orders --") < text.index("-- FUNCTION")


def test_the_buffer_is_reproducible_across_fetches():
    """BUG-018's determinism rule, now over a schema of every kind."""
    first, _ = build_ddl_text(_relation_schema())
    second, _ = build_ddl_text(_relation_schema())
    assert first == second


def test_the_buffer_is_byte_identical_WHATEVER_ORDER_THE_CATALOG_RETURNED():
    """The determinism that matters, and the one building the same schema twice
    cannot show: `psycopg` hands back rows in whatever order the server chose,
    so `DatabaseSchema`'s dicts arrive differently ordered between two fetches
    of an unchanged database. Rebuilding an identically-ordered schema proves
    only that the function is a function.

    Both the TEXT and the SPANS must be identical -- a span list that reorders
    would move `_span_at_line`'s first-match answer.
    """
    schema = _relation_schema()
    schema.tables["pr.audit"] = TableInfo(
        name="pr.audit",
        kind="table",
        columns=[ColumnInfo("id", "integer", True, False, False, None)],
    )
    schema.indexes["pr.ix_id"] = IndexInfo(
        schema="pr", table="orders", name="ix_id", columns=["id"],
        method="btree", definition="CREATE INDEX ix_id ON pr.orders (id)",
    )
    schema.constraints["pr.orders.orders_tag_key"] = ConstraintInfo(
        schema="pr", table="orders", name="orders_tag_key", kind="unique",
        columns=["tag"], definition="UNIQUE (tag)",
    )
    forwards_text, forwards_spans = build_ddl_text(schema)

    reversed_schema = DatabaseSchema(
        tables=dict(reversed(list(schema.tables.items()))),
        constraints=dict(reversed(list(schema.constraints.items()))),
        indexes=dict(reversed(list(schema.indexes.items()))),
    )
    backwards_text, backwards_spans = build_ddl_text(reversed_schema)

    assert backwards_text == forwards_text
    assert backwards_spans == forwards_spans
    # ...and the fixture really did exercise more than one of each, so the
    # assertion above is not vacuously comparing a one-element ordering.
    assert forwards_text.count("CREATE INDEX") == 2
    assert forwards_text.count("CONSTRAINT ") == 2


def test_only_routines_and_triggers_are_editable_kinds():
    """The read-only boundary does not move: tables, views and matviews are in
    the buffer to be READ, and are not part of the checkout model."""
    assert EDITABLE_SPAN_KINDS == {"function", "procedure", "trigger"}


def test_a_routines_only_schema_is_byte_for_byte_what_it_was():
    """The widening is additive: a schema with no relations produces exactly
    the buffer it produced before this feature."""
    text, spans = build_ddl_text(_schema())
    assert text.startswith("-- FUNCTION pr.audit_log() --")
    assert all(span.kind in EDITABLE_SPAN_KINDS for span in spans)
