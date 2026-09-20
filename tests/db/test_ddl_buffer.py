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


def test_only_routines_triggers_and_views_are_editable_kinds():
    """The read-only boundary moved by EXACTLY one kind (`FQ-260812025836`):
    a view alters in place with `CREATE OR REPLACE VIEW`, which is the property
    §18.5's apply lane is built around. Tables and matviews are still in the
    buffer to be READ."""
    assert EDITABLE_SPAN_KINDS == {"function", "procedure", "trigger", "view"}


def test_matviews_are_not_editable_and_that_is_load_bearing():
    """The carve-out this project has twice had widened by analogy: there is no
    `CREATE OR REPLACE MATERIALIZED VIEW`, so replacing one is a `DROP` +
    `CREATE` that discards its stored data. Asserted as a REFUSAL, not as an
    absence from a list that happens not to mention it."""
    assert "matview" not in EDITABLE_SPAN_KINDS
    assert "table" not in EDITABLE_SPAN_KINDS


def test_a_routines_only_schema_is_byte_for_byte_what_it_was():
    """The widening is additive: a schema with no relations produces exactly
    the buffer it produced before this feature."""
    text, spans = build_ddl_text(_schema())
    assert text.startswith("-- FUNCTION pr.audit_log() --")
    assert all(span.kind in EDITABLE_SPAN_KINDS for span in spans)


# ---------------------------------------------------------------------------
# DUAL MODE -- the FULL (`pg_dump`) renderer (`FQ-260812022749`)
# ---------------------------------------------------------------------------

from pgtp_editor.db.ddl_buffer import (  # noqa: E402
    OBJECT_SPAN_KINDS,
    build_ddl_buffer,
)
from pgtp_editor.db.pg_dump_mode import DdlMode  # noqa: E402
from pgtp_editor.db.table_ddl import SEQUENCE_CLONE_HAZARD  # noqa: E402

#: A whole-database `pg_dump --schema-only` covering exactly the relations
#: `_full_schema()` introspects -- with the sequence in a DIFFERENT section from
#: its table (which is why the clone hazard applies in full mode too), a CHECK
#: constraint left INLINE, a PK as a standalone two-line `ALTER TABLE`, and the
#: `CREATE FUNCTION`/`CREATE TRIGGER` a real dump carries.
FULL_DUMP = '''--
-- Dumped by pg_dump version 16.2
--

SET statement_timeout = 0;

CREATE SCHEMA pr;

--
-- Name: orders; Type: TABLE; Schema: pr; Owner: pg
--

CREATE TABLE pr.orders (
    id integer NOT NULL,
    tag text,
    CONSTRAINT orders_tag_check CHECK ((tag <> ''::text))
)
PARTITION BY RANGE (id);

CREATE SEQUENCE pr.orders_id_seq
    AS integer
    START WITH 1;

ALTER SEQUENCE pr.orders_id_seq OWNED BY pr.orders.id;

ALTER TABLE ONLY pr.orders ALTER COLUMN id SET DEFAULT nextval('pr.orders_id_seq'::regclass);

ALTER TABLE ONLY pr.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);

CREATE INDEX ix_tag ON pr.orders USING btree (tag);

CREATE VIEW pr.v_orders AS
 SELECT orders.id
   FROM pr.orders;

CREATE MATERIALIZED VIEW pr.m_orders AS
 SELECT orders.tag
   FROM pr.orders
  WITH NO DATA;

CREATE FUNCTION pr.calc_total(integer) RETURNS numeric
    LANGUAGE plpgsql
    AS $$begin return 1; end;$$;
'''


def _full_schema():
    """The relations `FULL_DUMP` dumps, plus the routines/triggers of
    `_schema()` -- i.e. a schema whose every object must find a span."""
    tables = {
        "pr.orders": TableInfo(
            name="pr.orders",
            kind="table",
            columns=[
                ColumnInfo(
                    "id", "integer", True, False, False,
                    "nextval('pr.orders_id_seq'::regclass)",
                ),
                ColumnInfo("tag", "text", False, False, True, None),
            ],
        ),
        "pr.v_orders": TableInfo(
            name="pr.v_orders", kind="view", view_definition="SELECT id FROM pr.orders"
        ),
        "pr.m_orders": TableInfo(
            name="pr.m_orders", kind="matview", view_definition="SELECT tag FROM pr.orders"
        ),
    }
    constraints = {
        "pr.orders.orders_pkey": ConstraintInfo(
            schema="pr", table="orders", name="orders_pkey", kind="primary key",
            columns=["id"], definition="PRIMARY KEY (id)",
        ),
        "pr.orders.orders_tag_check": ConstraintInfo(
            schema="pr", table="orders", name="orders_tag_check", kind="check",
            columns=["tag"], definition="CHECK ((tag <> ''::text))",
        ),
    }
    indexes = {
        "pr.ix_tag": IndexInfo(
            schema="pr", table="orders", name="ix_tag", columns=["tag"],
            method="btree", definition="CREATE INDEX ix_tag ON pr.orders USING btree (tag)",
        )
    }
    routines_and_triggers = _schema()
    return DatabaseSchema(
        tables=tables,
        constraints=constraints,
        indexes=indexes,
        routines=routines_and_triggers.routines,
        triggers=routines_and_triggers.triggers,
    )


def _full():
    return build_ddl_buffer(_full_schema(), mode=DdlMode.FULL, dump_text=FULL_DUMP)


def _by_kind(spans):
    out = {}
    for span in spans:
        out.setdefault(span.kind, {})[span.name] = span
    return out


def test_restricted_is_the_default_and_is_the_buffer_it_always_was():
    """The mode is a PARAMETER -- this layer never probes for it -- and the
    default keeps every existing caller byte-for-byte unchanged."""
    schema = _relation_schema()
    buffer = build_ddl_buffer(schema)
    text, spans = build_ddl_text(schema)
    assert buffer.mode is DdlMode.RESTRICTED
    assert buffer.degrade_reason is None
    assert (buffer.text, buffer.spans) == (text, spans)


def test_full_mode_renders_pg_dumps_own_statements_verbatim():
    buffer = _full()
    assert buffer.mode is DdlMode.FULL
    assert buffer.degrade_reason is None
    assert "PARTITION BY RANGE (id);" in buffer.text
    assert "-- NOTE: reconstructed by PGTP Editor" not in buffer.text


def test_full_mode_closes_the_gap_the_synthesizer_states_it_has():
    """The whole reason the mode exists: `table_ddl.py` cannot express
    `PARTITION BY`, and says so in every table's notice."""
    restricted = build_ddl_buffer(_full_schema())
    assert "PARTITION BY" not in restricted.text
    assert "PARTITION BY" in _full().text


def test_a_table_click_lands_on_its_CREATE_TABLE(  # owner-settled, 2026-08-12
):
    """*"click should bring to create table."* CONTAINMENT IS LOST in full
    mode and that is DESIGN, not a cost: the table's span covers its
    `CREATE TABLE` statement and does NOT enclose its constraints or indexes,
    so folding hides less and a constraint line resolves to the constraint."""
    buffer = _full()
    lines = buffer.text.splitlines()
    table = _by_kind(buffer.spans)["table"]["orders"]
    region = lines[table.start_line - 1: table.end_line]

    assert region[0] == "-- TABLE pr.orders --"
    assert any(line.startswith("CREATE TABLE pr.orders (") for line in region)
    # ...and the statements pg_dump emitted separately are OUTSIDE it.
    assert not any("ADD CONSTRAINT orders_pkey" in line for line in region)
    assert not any(line.startswith("CREATE INDEX ix_tag") for line in region)
    assert "ADD CONSTRAINT orders_pkey" in buffer.text
    assert "CREATE INDEX ix_tag ON pr.orders" in buffer.text


def test_every_relation_column_constraint_and_index_still_navigates():
    """Navigation is preserved IN FULL -- the recovery is by statement
    boundary, on the existing `DdlObjectSpan`, with no sibling span type."""
    buffer = _full()
    lines = buffer.text.splitlines()
    by_kind = _by_kind(buffer.spans)

    assert set(by_kind["table"]) == {"orders"}
    assert set(by_kind["view"]) == {"v_orders"}
    assert set(by_kind["matview"]) == {"m_orders"}
    assert set(by_kind["column"]) == {"id", "tag"}
    assert set(by_kind["constraint"]) == {"orders_pkey", "orders_tag_check"}
    assert set(by_kind["index"]) == {"ix_tag"}

    assert lines[by_kind["column"]["tag"].start_line - 1].strip().startswith("tag text")
    # The INLINE check constraint and the STANDALONE primary key -- pg_dump
    # splits a table's constraints across both shapes, and both navigate.
    assert "orders_tag_check" in lines[
        by_kind["constraint"]["orders_tag_check"].start_line - 1
    ]
    pkey = by_kind["constraint"]["orders_pkey"]
    assert "ADD CONSTRAINT orders_pkey" in "\n".join(
        lines[pkey.start_line - 1: pkey.end_line]
    )
    assert lines[by_kind["index"]["ix_tag"].start_line - 1].startswith("CREATE INDEX")


def test_object_spans_still_come_before_detail_spans_in_full_mode():
    """`_span_at_line` returns the first containing span, and the ordering
    contract is the buffer's, not the mode's."""
    kinds = [span.kind for span in _full().spans]
    last_object = max(
        i for i, kind in enumerate(kinds) if kind in OBJECT_SPAN_KINDS
    )
    first_detail = min(
        i for i, kind in enumerate(kinds) if kind in ("column", "constraint", "index")
    )
    assert last_object < first_detail


def test_routines_and_triggers_come_from_the_CATALOG_even_in_full_mode():
    """A routine's identity is `RoutineInfo.signature`, which has exactly one
    source and is never re-rendered (BUG-018). Recovering it from a
    `CREATE FUNCTION` header would mean re-deriving it out of argument names,
    modes and defaults -- so the dump's routine statements are left out and the
    catalog's text is used, in BOTH modes."""
    buffer = _full()
    by_kind = _by_kind(buffer.spans)
    assert set(by_kind["function"]) == {"audit_log", "calc_total"}
    assert by_kind["function"]["calc_total"].signature == "pr.calc_total(integer)"
    assert set(by_kind["trigger"]) == {"trg_audit"}
    # The dump's own CREATE FUNCTION is NOT also in the buffer -- one routine,
    # one region, so a tree click cannot land on the copy without a span.
    assert buffer.text.count("pr.calc_total") == 2  # the banner and the catalog source
    assert "$$begin return 1; end;$$" not in buffer.text


def test_the_sequence_the_table_depends_on_is_kept_not_dropped():
    """`pg_dump` emits an owned sequence in a different section; a statement
    this app does not attribute to a relation is still a statement a clone of
    that table needs, so the catch-all bucket keeps it verbatim."""
    text = _full().text
    assert "CREATE SEQUENCE pr.orders_id_seq" in text
    assert "ALTER SEQUENCE pr.orders_id_seq OWNED BY pr.orders.id;" in text
    assert "CREATE SCHEMA pr;" in text


def test_the_nextval_clone_hazard_is_stated_in_BOTH_modes():
    """Owner ruling: WARN ONLY -- no `CREATE SEQUENCE` span, nothing
    restructured. It applies to full mode too, because pg_dump puts the
    sequence in a different section from the table, so copying the
    `CREATE TABLE` still misses it."""
    schema = _full_schema()
    assert SEQUENCE_CLONE_HAZARD in build_ddl_buffer(schema).text
    assert SEQUENCE_CLONE_HAZARD in _full().text
    # No sequence span in either mode.
    assert all(span.kind != "sequence" for span in _full().spans)


def test_the_hazard_sits_INSIDE_the_region_a_whole_object_copy_takes():
    """A notice read at open is forgotten twenty tables down; the one inside
    the copied region travels with the text."""
    buffer = _full()
    lines = buffer.text.splitlines()
    table = _by_kind(buffer.spans)["table"]["orders"]
    region = lines[table.start_line - 1: table.end_line]
    assert SEQUENCE_CLONE_HAZARD in region


def test_full_mode_is_byte_identical_whatever_order_the_catalog_returned():
    """Full mode cannot inherit restricted mode's end-to-end determinism --
    `pg_dump`'s own text varies with the client's version. What it CAN own is
    that nothing on OUR side of the seam moves a line: relations are ordered by
    name, and attached statements by (kind, name), not by pg_dump's walk."""
    schema = _full_schema()
    forwards = build_ddl_buffer(schema, mode=DdlMode.FULL, dump_text=FULL_DUMP)
    reversed_schema = DatabaseSchema(
        tables=dict(reversed(list(schema.tables.items()))),
        constraints=dict(reversed(list(schema.constraints.items()))),
        indexes=dict(reversed(list(schema.indexes.items()))),
        routines=dict(reversed(list(schema.routines.items()))),
        triggers=dict(reversed(list(schema.triggers.items()))),
    )
    backwards = build_ddl_buffer(
        reversed_schema, mode=DdlMode.FULL, dump_text=FULL_DUMP
    )
    assert backwards.text == forwards.text
    assert backwards.spans == forwards.spans


# -- the refusal: degrade to restricted, never half-parse ---------------------

def test_an_unattributable_relation_degrades_to_restricted_with_a_reason():
    """A half-parsed buffer whose spans point at the wrong lines is the worst
    outcome available here -- worse than restricted DDL -- so it is not a
    reachable third branch."""
    schema = _full_schema()
    schema.tables["pr.late"] = TableInfo(name="pr.late", kind="table", columns=[])

    buffer = build_ddl_buffer(schema, mode=DdlMode.FULL, dump_text=FULL_DUMP)

    assert buffer.mode is DdlMode.RESTRICTED
    assert "pr.late" in buffer.degrade_reason
    assert "1 of 4 relations" in buffer.degrade_reason
    # It is the RESTRICTED buffer, whole -- not a partial full one.
    assert (buffer.text, buffer.spans) == build_ddl_text(schema)


def test_the_degrade_reason_carries_the_clone_warning_the_mode_row_carries():
    """One wording home: the restricted mode's *do not clone a partitioned or
    inherited table from this text* sentence is `db/pg_dump_mode.py`'s, and the
    refusal reuses it rather than spelling a second variant."""
    buffer = build_ddl_buffer(_full_schema(), mode=DdlMode.FULL, dump_text="")
    assert "do not clone a partitioned or inherited table" in buffer.degrade_reason


def test_an_empty_or_statementless_dump_degrades_with_its_own_reason():
    for dump, fragment in (
        ("", "produced no schema dump output"),
        ("   \n\n", "produced no schema dump output"),
        ("-- just a comment\n", "held no SQL statements"),
    ):
        buffer = build_ddl_buffer(_full_schema(), mode=DdlMode.FULL, dump_text=dump)
        assert buffer.mode is DdlMode.RESTRICTED
        assert fragment in buffer.degrade_reason


def test_full_mode_with_no_dump_text_at_all_degrades_rather_than_raising():
    buffer = build_ddl_buffer(_full_schema(), mode=DdlMode.FULL, dump_text=None)
    assert buffer.mode is DdlMode.RESTRICTED
    assert buffer.degrade_reason


def test_a_relation_the_dump_does_not_spell_never_gets_a_guessed_column_line():
    """An inherited column is suppressed from a child's `CREATE TABLE`; giving
    its tree row a neighbouring line would be exactly the wrong-navigation
    failure this feature must not have."""
    schema = _full_schema()
    schema.tables["pr.orders"] = TableInfo(
        name="pr.orders",
        kind="table",
        columns=[
            ColumnInfo("id", "integer", True, False, False, None),
            ColumnInfo("inherited", "text", False, False, True, None),
        ],
    )
    buffer = build_ddl_buffer(schema, mode=DdlMode.FULL, dump_text=FULL_DUMP)
    columns = _by_kind(buffer.spans).get("column", {})
    assert "id" in columns
    assert "inherited" not in columns
