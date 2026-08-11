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
already-introspected `RoutineInfo`/`TriggerInfo` rows into text + spans.
"""
from __future__ import annotations

from dataclasses import dataclass

from .introspect import DatabaseSchema, RoutineInfo, TriggerInfo
from .table_ddl import build_relation_ddl

#: The span kinds whose object has a *live source definition* that
#: `resolve_edit_target` can hand to the editable single-object tab (§18.5 D1).
#:
#: Everything else in the buffer -- tables, views, matviews and the
#: column/constraint/index detail spans -- is **navigable but not editable**
#: (`FQ-260810183812`): those objects are not part of §18.2's checkout model,
#: and a table's shape changes through `Alter Table ▸` alone. Named here rather
#: than spelled as a tuple at each call site, because two copies of this set is
#: exactly how the second one comes to miss a kind.
EDITABLE_SPAN_KINDS = frozenset({"function", "procedure", "trigger"})

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
