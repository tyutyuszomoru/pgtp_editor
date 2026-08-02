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
