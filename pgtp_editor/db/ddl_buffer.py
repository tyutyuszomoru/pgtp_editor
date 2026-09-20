# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# pgtp_editor/db/ddl_buffer.py
"""Synthesize one browsable text buffer from a `DatabaseSchema`'s **every
object kind** -- tables, views and matviews, then routines and triggers -- with
a structural span index over it (§18.1 DDL Explorer, widened by
`FQ-260810183812`).

Plays the same role for the DDL buffer that `TagSpan` (`ui/xml_structure.py`,
§8) plays for the Raw XML buffer: one shared text document plus a line-indexed
span per object, so a tree (`ui/ddl_buffer_panel.py::BrowserPanel`) can
navigate into a single `CodeEditor` (`ui/ddl_editor_panel.py::EditorPanel`) by
line number instead of opening a bespoke viewer per routine/trigger.

Pure and Qt-free: no I/O, no database access -- this module only formats
already-introspected `RoutineInfo`/`TriggerInfo` rows into text + spans. That
holds for the `pg_dump` path too: the **text** of a dump arrives as a parameter
(`build_ddl_buffer(..., dump_text=...)`), and the one subprocess that produces
it lives in `db/pg_dump_ddl.py`.

**THE BUFFER IS DUAL-MODE** (`FQ-260812022749`, owner ruling 2026-08-12): one
buffer, two renderers.

* **RESTRICTED** -- `build_ddl_text`, today's synthesized DDL from
  `db/table_ddl.py`. Unchanged, including BUG-018's *proven* determinism: the
  test that permutes `DatabaseSchema` dict order and demands a byte-identical
  buffer covers exactly this path and keeps passing.
* **FULL** -- `build_full_ddl_text`, one whole-database `pg_dump --schema-only`
  parsed into statements. Chosen when a correctly-versioned `pg_dump` is
  present (`db/pg_dump_mode.py` owns that verdict, and it arrives here as a
  **parameter**; this layer never probes).

**What full mode cannot promise that restricted mode does.** `pg_dump`'s own
output depends on the client's version (a version-dependent `SET` preamble, and
whatever a newer major spells differently), so end-to-end byte-identity in full
mode is an **environmental assumption, not a proven property**. What IS proven,
and pinned by tests: the *parser* is pure (same dump text in, identical lines
and spans out), and the composition here orders relations by name rather than
by `pg_dump`'s walk order, so nothing but the dump text itself can move a line.

**And it may refuse.** A FULL request whose dump cannot be attributed to every
relation the introspection found comes back RESTRICTED with a
`DdlBuffer.degrade_reason` for the `[DDL]` row. Half-parsing is not a third
outcome: spans pointing at the wrong lines are worse than restricted DDL.
"""
from __future__ import annotations

from dataclasses import dataclass

from .introspect import DatabaseSchema, RoutineInfo, TableInfo, TriggerInfo
from .pg_dump_ddl import (
    KIND_CONSTRAINT,
    KIND_INDEX,
    DumpStatement,
    ParsedDump,
    parse_pg_dump,
)
from .pg_dump_mode import RESTRICTED_CLONE_WARNING, DdlMode
from .table_ddl import build_relation_ddl, sequence_clone_hazard_lines

#: The span kinds whose object has a *live source definition* that
#: `resolve_edit_target` can hand to the editable single-object tab (§18.5 D1).
#:
#: Everything else in the buffer -- tables, matviews and the
#: column/constraint/index detail spans -- is **navigable but not editable**
#: (`FQ-260810183812`): a table's shape changes through `Alter Table ▸` alone.
#: Named here rather than spelled as a tuple at each call site, because two
#: copies of this set is exactly how the second one comes to miss a kind.
#:
#: **`"view"` is here and `"matview"` is NOT, and the asymmetry is
#: PostgreSQL's, not a preference** (`FQ-260812025836`). Everything editable
#: through §18.5 is editable because it has `CREATE OR REPLACE` semantics --
#: the apply lane replaces an object in place, and its four preconditions are
#: written around that. A view has that property. A **materialized view does
#: not**: there is no `CREATE OR REPLACE MATERIALIZED VIEW`, so "replacing" one
#: means `DROP` + `CREATE`, which discards its stored data, needs a `REFRESH`
#: afterwards and drops its dependents. **Do not widen this set to `"matview"`
#: by analogy** -- everything else in this codebase groups the two kinds (the
#: tree branch, `TableInfo.kind`, `pg_get_viewdef`, `table_ddl.build_view_ddl`),
#: which is exactly the shape of carve-out this project has had widened twice
#: (BUG-052, BUG-063). A test asserts the matview refusal directly.
EDITABLE_SPAN_KINDS = frozenset({"function", "procedure", "trigger", "view"})

#: Kinds that render a whole object with a banner of its own, as opposed to the
#: detail spans that point at ONE line inside another object's text. Object
#: spans are emitted first in `build_ddl_text`'s span list so `_span_at_line`,
#: which returns the first containing span, resolves a click inside a table to
#: the TABLE rather than to whichever column happens to sit on that line.
OBJECT_SPAN_KINDS = frozenset(
    {"function", "procedure", "trigger", "table", "view", "matview"}
)


@dataclass(frozen=True)
class DdlObjectSpan:
    """One navigable region of the synthesized buffer.

    **`kind` GROWS; there is deliberately no sibling span type.** Two walks
    iterate `self._spans` -- `ui/ddl_editor_panel.py::_fold_regions_for_spans`
    and `EditorPanel._span_at_line` -- so a parallel `DdlTableSpan` would fork
    both, and the second one written would miss a case. One dataclass, one
    `kind` field (`FQ-260810183812`).
    """

    #: "function" | "procedure" | "trigger" | "table" | "view" | "matview"
    #: | "column" | "constraint" | "index"
    kind: str
    schema: str
    name: str
    #: The owning relation, for the kinds that have one: triggers (the table
    #: the trigger fires on) and the `column`/`constraint`/`index` detail
    #: spans. `None` for routines and for relations themselves.
    table: str | None
    start_line: int  # 1-based; the banner comment line
    end_line: int  # 1-based, inclusive; the source text's last line
    #: Routines only -- `RoutineInfo.signature`, the full `schema.name(args)`
    #: identity. `None` for triggers. Without it a span cannot be matched back
    #: to *one* of two overloads sharing a `schema.name`, and BrowserPanel's
    #: span map hands both tree items the same body (BUG-018). Trailing and
    #: defaulted so existing positional constructions stay valid.
    signature: str | None = None


_RELATION_LABELS = {
    "table": "TABLE",
    "view": "VIEW",
    "matview": "MATERIALIZED VIEW",
}


def _banner(kind: str, schema: str, name: str, *, table: str | None, signature: str | None) -> str:
    """The banner comment line anchoring one object's span.

    A routine's banner embeds `RoutineInfo.signature` **verbatim** -- it is
    never re-rendered here. That string is the single source of a routine's
    identity: the `DatabaseSchema.routines` dict key, the diff identity
    (`db/schema_diff.py::routine_identity`) and the future `ddl/` filename are
    all the same characters, and a second rendering is exactly how they drift
    apart (BUG-018).
    """
    if kind == "trigger":
        return f"-- TRIGGER {schema}.{name} ON {table} --"
    if kind in _RELATION_LABELS:
        return f"-- {_RELATION_LABELS[kind]} {schema}.{name} --"
    label = "FUNCTION" if kind == "function" else "PROCEDURE"
    return f"-- {label} {signature} --"


def build_ddl_text(schema: DatabaseSchema) -> tuple[str, list[DdlObjectSpan]]:
    """Synthesize one text buffer holding **every object kind** -- tables,
    views and matviews first, then routines and triggers -- each preceded by a
    banner comment anchoring its span (`FQ-260810183812`, §18.1).

    **Ordering is dual-grouped, matching the tree** (relations, then routines
    and triggers), rather than alphabetical across kinds: `BrowserPanel` has
    always shown a "Tables" branch above a "Functions & Procedures" branch, and
    a buffer whose order matches the tree's is the one a reader can scroll as
    well as jump into. Within each group the order is fully deterministic
    across fetches -- schema, then name, then (for two overloads sharing a
    `schema.name`) their argument types. Without that last clause overloads tie
    and the stable sort falls back to catalog row order (BUG-018).

    The returned span list is **object spans first, detail spans after**, so
    `EditorPanel._span_at_line`'s first-match resolution answers "the table"
    for a click on a line that is also a column's line.
    """
    lines: list[str] = []
    spans: list[DdlObjectSpan] = []
    detail_spans: list[DdlObjectSpan] = []
    _append_relations(schema, lines, spans, detail_spans)
    _append_routines_and_triggers(schema, lines, spans)
    return "\n".join(lines), spans + detail_spans


def _append_relations(
    schema: DatabaseSchema,
    lines: list[str],
    spans: list[DdlObjectSpan],
    detail_spans: list[DdlObjectSpan],
) -> None:
    """Every table/view/matview, synthesized by `db/table_ddl.py` and given one
    object span plus one detail span per column, constraint and index.

    The detail spans are what makes *"every tree item that has DDL navigates to
    it"* true for the column, constraint and index nodes: each points at the
    single line that renders that item **inside** the `CREATE TABLE`, which is
    the answer that honours the no-`ALTER` shape (open question 1) -- a
    constraint has no statement of its own to jump to, only a line.
    """
    for qualified in sorted(schema.tables):
        table = schema.tables[qualified]
        schema_name, _, table_name = qualified.partition(".")
        rendered = build_relation_ddl(
            table,
            schema.constraints_for(qualified),
            schema.indexes_for(qualified),
        )
        kind = table.kind if table.kind in _RELATION_LABELS else "table"
        lines.append(_banner(kind, schema_name, table_name, table=None, signature=None))
        start_line = len(lines)
        offset = len(lines)  # 0-based offsets are relative to the first body line
        lines.extend(rendered.lines or [""])
        end_line = len(lines)
        lines.append("")  # blank separator before the next object

        spans.append(
            DdlObjectSpan(
                kind=kind,
                schema=schema_name,
                name=table_name,
                table=None,
                start_line=start_line,
                end_line=end_line,
            )
        )
        for detail_kind, offsets in (
            ("column", rendered.column_offsets),
            ("constraint", rendered.constraint_offsets),
            ("index", rendered.index_offsets),
        ):
            for item_name, item_offset in offsets.items():
                line = offset + item_offset + 1
                detail_spans.append(
                    DdlObjectSpan(
                        kind=detail_kind,
                        schema=schema_name,
                        name=item_name,
                        table=table_name,
                        start_line=line,
                        end_line=line,
                    )
                )


# ---------------------------------------------------------------------------
# FULL mode -- the same buffer, rendered from `pg_dump --schema-only`
# (`FQ-260812022749` Part 3)
# ---------------------------------------------------------------------------

#: Introduces the statements `pg_dump` emitted that name no relation: the `SET`
#: preamble, `CREATE SCHEMA`, `CREATE EXTENSION`, `CREATE TYPE`/`DOMAIN`, and
#: **the owned `CREATE SEQUENCE` / `ALTER SEQUENCE ... OWNED BY` pairs**.
#:
#: They are emitted rather than dropped for one reason: a `CREATE TYPE` a
#: column depends on, or a sequence a `nextval` default points at, is exactly
#: what a clone of that table silently needs. Dropping a statement because this
#: app did not recognise it is the shape of silent loss §1 forbids -- so the
#: bucket is a catch-all, not a whitelist, and a statement kind PostgreSQL adds
#: in 2030 lands here verbatim instead of vanishing.
#:
#: They carry **no span**: nothing in the tree denotes them (`DatabaseSchema`
#: has no sequence or extension branch), and a span no tree item can reach is
#: dead weight in both span walks.
DUMP_PREAMBLE_BANNER = "-- DATABASE-LEVEL STATEMENTS (pg_dump --schema-only) --"
DUMP_PREAMBLE_NOTE = (
    "--       schemas, extensions, types and the sequences owned by SERIAL "
    "columns. pg_dump emits these"
)
DUMP_PREAMBLE_NOTE_DETAIL = (
    "--       apart from the tables that use them; they are kept here verbatim "
    "rather than dropped."
)

#: Ordering rank for the statements attached to one relation. Constraints
#: first (they are what the restricted renderer puts inline), then indexes,
#: then everything else -- and by name within a rank, so the buffer is
#: identical for identical dump text no matter what order `pg_dump` walked.
_ATTACHMENT_RANK = {KIND_CONSTRAINT: 0, KIND_INDEX: 1}


@dataclass(frozen=True)
class DdlBuffer:
    """One built buffer, and **which renderer actually produced it**.

    The mode is reported, not assumed, because `build_ddl_buffer` is allowed to
    refuse: a FULL request whose dump cannot be attributed to every relation
    comes back RESTRICTED with `degrade_reason` set, and the caller turns that
    into a `[DDL]` row. A half-parsed buffer with spans pointing at the wrong
    lines is the worst outcome this feature could have -- worse than restricted
    DDL -- so refusing is the only other branch.
    """

    text: str
    spans: list[DdlObjectSpan]
    mode: DdlMode
    #: `None` unless FULL was asked for and refused; otherwise the sentence for
    #: the `[DDL]` row, WITHOUT its prefix (`ui/audit_router.py::DDL_PREFIX` is
    #: the prefix's one home, and this module stays Qt-free).
    degrade_reason: str | None = None


def build_ddl_buffer(
    schema: DatabaseSchema,
    *,
    mode: DdlMode = DdlMode.RESTRICTED,
    dump_text: str | None = None,
) -> DdlBuffer:
    """The dual-mode entry point (owner ruling, 2026-08-12): **one buffer, two
    renderers**.

    `mode` is a **parameter**, deliberately -- the verdict is probed once per
    quality connection by `db/pg_dump_mode.py` and lives on the window; this
    layer never reaches for it, never re-probes, and stays testable from two
    plain values.

    RESTRICTED is `build_ddl_text` unchanged, so BUG-018's proven determinism
    (the test that permutes `DatabaseSchema` dict order and demands a
    byte-identical buffer) keeps holding over exactly the code it always
    covered.

    FULL renders `dump_text` -- one whole-database `pg_dump --schema-only`,
    fetched by `pg_dump_ddl.fetch_schema_dump` -- and **degrades to RESTRICTED,
    with a reason, rather than ever half-succeeding.**
    """
    if mode is not DdlMode.FULL:
        text, spans = build_ddl_text(schema)
        return DdlBuffer(text=text, spans=spans, mode=DdlMode.RESTRICTED)

    if not (dump_text or "").strip():
        return _degraded(schema, "Restricted DDL — pg_dump produced no schema dump output.")

    # Parsed ONCE and handed to both the check and the build: a whole-database
    # dump is megabytes, and a second parse for the same answer is the kind of
    # duplicated work that later gets "optimized" by skipping the check.
    parsed = parse_pg_dump(dump_text or "")
    refusal = _full_mode_refusal(schema, parsed)
    if refusal is not None:
        return _degraded(schema, refusal)

    text, spans = build_full_ddl_text(schema, parsed)
    return DdlBuffer(text=text, spans=spans, mode=DdlMode.FULL)


def _degraded(schema: DatabaseSchema, refusal: str) -> DdlBuffer:
    """The whole RESTRICTED buffer plus the sentence saying why -- never a
    partially-built full one."""
    text, spans = build_ddl_text(schema)
    return DdlBuffer(
        text=text,
        spans=spans,
        mode=DdlMode.RESTRICTED,
        degrade_reason=f"{refusal} {RESTRICTED_CLONE_WARNING}",
    )


def _full_mode_refusal(schema: DatabaseSchema, parsed: ParsedDump) -> str | None:
    """Why this dump must not be rendered, or None.

    The one check that matters is **attribution**: every relation the
    introspection found must have exactly one `CREATE` statement in the dump.
    That is what makes the two consumers of a buffer generation agree -- the
    tree is built from `schema`, the buffer from the dump, and §18.1 forbids a
    second parallel source of truth. A relation present in the tree with no
    statement in the text is precisely a tree row whose click goes nowhere, and
    a dump written by a `pg_dump` whose layout this parser does not understand
    fails this check *loudly* instead of producing wrong line numbers.

    Skew is the other thing this catches for free: the dump is a **second
    connection at a different instant** than the psycopg introspection, so a
    table created between the two shows up here as an unattributed relation.
    """
    if parsed.empty:
        return "Restricted DDL — pg_dump's output held no SQL statements."
    missing = [
        qualified for qualified in sorted(schema.tables) if qualified not in parsed.creates
    ]
    if missing:
        shown = ", ".join(missing[:3])
        more = f" (+{len(missing) - 3} more)" if len(missing) > 3 else ""
        return (
            f"Restricted DDL — pg_dump's output could not be attributed to "
            f"{len(missing)} of {len(schema.tables)} relations ({shown}{more}), "
            f"so full mode would have produced spans pointing at the wrong "
            f"lines."
        )
    return None


def build_full_ddl_text(
    schema: DatabaseSchema, parsed: ParsedDump
) -> tuple[str, list[DdlObjectSpan]]:
    """The FULL-mode buffer: `pg_dump`'s statements verbatim, grouped per
    relation, with the same banners and the same span shape the restricted
    buffer uses.

    **Three deliberate decisions a later reader will otherwise re-derive:**

    1. **A table's object span covers its `CREATE TABLE` statement only** --
       owner-settled (*"click should bring to create table"*). Containment is
       therefore LOST in full mode: folding a table hides less than it does in
       restricted mode, and `_span_at_line` on a constraint line resolves to the
       **constraint**, not to the enclosing table. Both are recorded design, not
       costs to re-raise, and a test pins the click-lands-on-`CREATE TABLE`
       behaviour so a refactor cannot drift it.
    2. **Relations are ordered by name, and their attached statements by
       (kind, name)** -- not in `pg_dump`'s global dependency order. Dependency
       order matters when the file is *executed*; this file is *read and
       partially copied*, and the tree it is navigated from is alphabetical.
       Ordering here also removes `pg_dump`'s walk order from the buffer's
       identity, which is the one determinism this layer can actually own.
    3. **Routines and triggers still come from the CATALOG** (the same
       `_append_routines_and_triggers` restricted mode uses), and their
       `CREATE FUNCTION`/`CREATE TRIGGER` statements are left out of the dump
       section rather than shown twice. This is a requirement, not a shortcut:
       a routine's identity is `RoutineInfo.signature` -- `schema.name(` +
       `format_type(proargtypes)` -- and recovering it from a `CREATE FUNCTION`
       header would mean **re-rendering** that string out of argument names,
       `OUT`/`VARIADIC` modes and `DEFAULT` expressions, with typmods spelled
       differently on the two sides (`character varying(20)` vs
       `character varying`). BUG-018's rule is that this string has exactly one
       source and is never re-rendered; a near-miss would silently unnavigate a
       routine and break its `Edit DDL`. Nothing is lost by it either: a
       routine's catalog text is `pg_get_functiondef`, which is already complete
       -- the incompleteness full mode exists to fix is a **table** problem.
    """
    lines: list[str] = []
    spans: list[DdlObjectSpan] = []
    detail_spans: list[DdlObjectSpan] = []
    _append_dump_preamble(parsed, lines)
    _append_dump_relations(schema, parsed, lines, spans, detail_spans)
    _append_routines_and_triggers(schema, lines, spans)
    return "\n".join(lines), spans + detail_spans


def _append_dump_preamble(parsed: ParsedDump, lines: list[str]) -> None:
    if not parsed.other:
        return
    lines.extend([DUMP_PREAMBLE_BANNER, DUMP_PREAMBLE_NOTE, DUMP_PREAMBLE_NOTE_DETAIL, ""])
    for statement in parsed.other:
        lines.extend(statement.lines)
        lines.append("")


def _append_dump_relations(
    schema: DatabaseSchema,
    parsed: ParsedDump,
    lines: list[str],
    spans: list[DdlObjectSpan],
    detail_spans: list[DdlObjectSpan],
) -> None:
    for qualified in sorted(schema.tables):
        table = schema.tables[qualified]
        schema_name, _, table_name = qualified.partition(".")
        create = parsed.creates[qualified]  # attribution was checked up front
        kind = table.kind if table.kind in _RELATION_LABELS else "table"

        lines.append(_banner(kind, schema_name, table_name, table=None, signature=None))
        # The span starts at the BANNER, exactly as it does in restricted mode
        # (`DdlObjectSpan.start_line`'s contract), so a tree click lands in the
        # same place in both modes and the clone hazard sits INSIDE the region a
        # whole-object copy takes with it. What differs between the modes is
        # where the span ENDS -- see this function's docstring.
        start_line = len(lines)
        lines.extend(sequence_clone_hazard_lines(table))
        body_start = len(lines) + 1
        lines.extend(create.lines)
        end_line = len(lines)
        spans.append(
            DdlObjectSpan(
                kind=kind,
                schema=schema_name,
                name=table_name,
                table=None,
                start_line=start_line,
                end_line=end_line,
            )
        )
        detail_spans.extend(
            _column_detail_spans(table, create, schema_name, table_name, body_start)
        )
        # `pg_dump` splits a table's constraints across two shapes: CHECK stays
        # INSIDE the `CREATE TABLE`, PK/UNIQUE/FK come out later as
        # `ALTER TABLE ONLY … ADD CONSTRAINT`. Both shapes get a span here, or
        # every CHECK constraint's tree row would click into nothing.
        inline_constraints = {
            constraint.name
            for constraint in schema.constraints_for(qualified)
            if constraint.name in create.constraint_offsets
        }
        for name in sorted(inline_constraints):
            line = body_start + create.constraint_offsets[name]
            detail_spans.append(
                DdlObjectSpan(
                    kind=KIND_CONSTRAINT,
                    schema=schema_name,
                    name=name,
                    table=table_name,
                    start_line=line,
                    end_line=line,
                )
            )

        for statement in _ordered_attachments(parsed, qualified):
            lines.append("")
            attach_start = len(lines) + 1
            lines.extend(statement.lines)
            # A statement's TEXT is always emitted -- dropping dump text is not
            # something this layer does. Only a duplicate SPAN is suppressed: one
            # constraint cannot legally be in both shapes, and two spans for one
            # identity would make the tree's span map last-wins (BUG-018's
            # shape).
            duplicate = (
                statement.kind == KIND_CONSTRAINT and statement.name in inline_constraints
            )
            if not duplicate and statement.kind in (KIND_CONSTRAINT, KIND_INDEX):
                detail_spans.append(
                    DdlObjectSpan(
                        kind=statement.kind,
                        schema=schema_name,
                        name=statement.name,
                        table=table_name,
                        start_line=attach_start,
                        end_line=len(lines),
                    )
                )
        lines.append("")  # blank separator before the next object


def _ordered_attachments(parsed: ParsedDump, qualified: str) -> list[DumpStatement]:
    return sorted(
        parsed.attachments.get(qualified, ()),
        key=lambda statement: (
            _ATTACHMENT_RANK.get(statement.kind, 9),
            statement.name,
            "\n".join(statement.lines),
        ),
    )


def _column_detail_spans(
    table: TableInfo,
    create: DumpStatement,
    schema_name: str,
    table_name: str,
    body_start: int,
) -> list[DdlObjectSpan]:
    """One detail span per column the dump's `CREATE TABLE` body actually
    names, **intersected with the columns the catalog reported**.

    The intersection is the safety property: a body entry this parser misread
    cannot become a span (it is not a catalog column), and a catalog column the
    body does not spell gets **no** span rather than a guessed line. A column
    inherited from a parent table is exactly that case -- `pg_dump` suppresses
    it from the child's `CREATE TABLE`, and pointing its tree row at some
    neighbouring line would be the wrong-navigation failure this feature must
    not have.
    """
    spans: list[DdlObjectSpan] = []
    for column in table.columns or []:
        offset = create.column_offsets.get(column.name)
        if offset is None:
            continue
        line = body_start + offset
        spans.append(
            DdlObjectSpan(
                kind="column",
                schema=schema_name,
                name=column.name,
                table=table_name,
                start_line=line,
                end_line=line,
            )
        )
    return spans


def _append_routines_and_triggers(
    schema: DatabaseSchema, lines: list[str], spans: list[DdlObjectSpan]
) -> None:
    items: list[tuple[str, RoutineInfo | TriggerInfo]] = [
        ("routine", routine) for routine in schema.routines.values()
    ]
    items += [("trigger", trigger) for trigger in schema.triggers.values()]
    items.sort(
        key=lambda item: (
            item[1].schema,
            0 if item[0] == "routine" else 1,
            item[1].name,
            tuple(item[1].arg_types) if item[0] == "routine" else (),
        )
    )

    for tag, obj in items:
        is_trigger = tag == "trigger"
        kind = "trigger" if is_trigger else obj.kind
        table = obj.table if is_trigger else None
        signature = None if is_trigger else obj.signature
        source = obj.definition if is_trigger else obj.source

        lines.append(
            _banner(kind, obj.schema, obj.name, table=table, signature=signature)
        )
        start_line = len(lines)
        lines.extend(source.splitlines() or [""])
        end_line = len(lines)
        lines.append("")  # blank separator before the next object

        spans.append(
            DdlObjectSpan(
                kind=kind,
                schema=obj.schema,
                name=obj.name,
                table=table,
                start_line=start_line,
                end_line=end_line,
                signature=signature,
            )
        )
