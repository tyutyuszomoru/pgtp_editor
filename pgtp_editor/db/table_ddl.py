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

# pgtp_editor/db/table_ddl.py
"""Synthesize a relation's DDL text from already-introspected catalog rows
(`FQ-260810183812`, §18.1) -- `CREATE TABLE` for tables, `CREATE VIEW` /
`CREATE MATERIALIZED VIEW` for views.

Pure and Qt-free, beside `ddl_buffer.py` and for the same reason: no I/O, no
database access, no widgets. It *formats* `TableInfo`/`ColumnInfo`/
`ConstraintInfo`/`IndexInfo` rows that some other layer already fetched, which
is what makes every reconstruction branch (a nullable column with a default, a
multi-column PK, a partial index, a table with no constraints at all) testable
without a server.

**A synthesized `CREATE TABLE` is a RECONSTRUCTION, and this module states so
in its own output.** PostgreSQL has no `pg_get_tabledef`; v1 reads columns,
constraints, indexes and comments, and therefore omits identity/`SERIAL`
sequences, `GENERATED` columns, table inheritance and partitioning. Presenting
that text as *"the table's DDL"* without saying so is a silent wrong result
(§1's master invariant): a user who sees no `GENERATED ALWAYS AS IDENTITY`
concludes the column has none. So every table's text carries
`RECONSTRUCTION_NOTICE` -- **per table, not once per buffer** (see below).
Nothing here ever *guesses*: a partitioned or inherited table renders as the
columns and constraints that were read, with the omission named, never with an
invented `PARTITION BY`.

Constraint text is `pg_get_constraintdef` **verbatim** (`ConstraintInfo.
definition`) and index text is `pg_get_indexdef` verbatim
(`IndexInfo.definition`). Re-deriving either from its columns is how this pane
and §18.3's schema diff come to disagree about what a constraint *is* -- the
same drift `ddl_buffer._banner` avoids by embedding `RoutineInfo.signature`
unrendered (BUG-018).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .introspect import ColumnInfo, ConstraintInfo, IndexInfo, TableInfo

#: The visible incompleteness statement, emitted **once per table**, directly
#: under that table's banner and above its `CREATE TABLE`.
#:
#: **Granularity: per table, deliberately.** The whole point of this feature is
#: that a tree click *jumps into the middle* of a multi-megabyte buffer, so a
#: single notice at the top of the buffer is invisible to exactly the gesture
#: the feature adds -- the user lands on `CREATE TABLE pr.orders` and never
#: scrolls past it. A per-table line is seen by every reader of every table,
#: costs one line per table, and folds away with the object like everything
#: else here.
#:
#: An SQL comment, because the buffer is read as SQL and a comment is the one
#: thing that cannot be mistaken for part of the definition.
RECONSTRUCTION_NOTICE = (
    "-- NOTE: reconstructed by PGTP Editor from pg_catalog (columns, "
    "constraints, indexes, comments) --"
)
RECONSTRUCTION_NOTICE_DETAIL = (
    "--       this is NOT the original CREATE statement. NOT reconstructed: "
    "identity/SERIAL, GENERATED columns, inheritance, partitioning."
)

#: Ordering rank for inline constraints, so a table's rendered DDL is
#: reproducible across fetches (BUG-018's determinism rule, which is NOT one of
#: this feature's open questions). Within a rank, by constraint name.
_CONSTRAINT_RANK = {
    "primary key": 0,
    "unique": 1,
    "foreign key": 2,
    "check": 3,
    "exclude": 4,
}

_BARE_IDENT = re.compile(r"^[a-z_][a-z0-9_$]*$")


def quote_ident(name: str) -> str:
    """Quote `name` only when PostgreSQL would need it quoted to read back the
    same identifier -- i.e. anything that is not already a bare lower-case
    identifier. `orders` stays `orders`; `Order Lines` becomes `"Order Lines"`.

    Catalog names arrive unquoted, so the common case renders exactly as the
    user typed it and the uncommon case does not silently render invalid SQL.
    """
    if _BARE_IDENT.match(name or ""):
        return name
    return '"' + (name or "").replace('"', '""') + '"'


def qualified_ident(qualified: str) -> str:
    """`pr.order lines` -> `pr."order lines"` -- quote each part of a
    `schema.name` pair independently."""
    schema, _, name = qualified.partition(".")
    if not _:
        return quote_ident(qualified)
    return f"{quote_ident(schema)}.{quote_ident(name)}"


def _quote_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


@dataclass(frozen=True)
class RelationDdl:
    """One relation's synthesized text, plus the 0-based offsets *within it* of
    the lines a tree node may want to jump to.

    The offsets exist so `ddl_buffer.build_ddl_text` can turn a column /
    constraint / index tree node into a `DdlObjectSpan` pointing at the line
    that actually renders it -- without this module knowing anything about
    spans, buffers or line 1 of anything.
    """

    lines: list[str] = field(default_factory=list)
    #: column name -> 0-based index into `lines`
    column_offsets: dict[str, int] = field(default_factory=dict)
    #: constraint name -> 0-based index into `lines`
    constraint_offsets: dict[str, int] = field(default_factory=dict)
    #: index name -> 0-based index into `lines`
    index_offsets: dict[str, int] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _column_line(column: ColumnInfo) -> str:
    parts = [f"    {quote_ident(column.name)} {column.data_type}"]
    if not column.is_nullable:
        parts.append(" NOT NULL")
    if column.default:
        parts.append(f" DEFAULT {column.default}")
    return "".join(parts)


def _sorted_constraints(constraints) -> list[ConstraintInfo]:
    return sorted(
        constraints,
        key=lambda c: (_CONSTRAINT_RANK.get(c.kind, 9), c.name),
    )


def _standalone_indexes(indexes) -> list[IndexInfo]:
    """The indexes that are NOT the implicit index of a PK/UNIQUE/EXCLUDE
    constraint -- rendering those too would print the same object twice, once
    as the inline constraint and once as a `CREATE INDEX` PostgreSQL never
    accepted (`IndexInfo.is_constraint_backed`, FQ-025)."""
    return sorted(
        (index for index in indexes if not index.is_constraint_backed),
        key=lambda i: i.name,
    )


def _statement(definition: str) -> str:
    """A catalog-supplied statement, verbatim, with exactly one terminator."""
    body = (definition or "").strip()
    return body if body.endswith(";") else f"{body};"


def build_table_ddl(
    table: TableInfo,
    constraints=(),
    indexes=(),
) -> RelationDdl:
    """`CREATE TABLE` for `table`, with the reconstruction notice, its columns,
    its constraints INLINE, then the standalone `CREATE INDEX` statements and
    the `COMMENT ON` statements.

    **No `ALTER` statements anywhere** (owner: *"don't worry about ALTER"*),
    which is exactly why constraints render inline: an
    `ALTER TABLE ... ADD CONSTRAINT` form was considered and rejected.
    """
    name = qualified_ident(table.name)
    lines: list[str] = [RECONSTRUCTION_NOTICE, RECONSTRUCTION_NOTICE_DETAIL]
    column_offsets: dict[str, int] = {}
    constraint_offsets: dict[str, int] = {}
    index_offsets: dict[str, int] = {}

    columns = list(table.columns or [])
    ordered_constraints = _sorted_constraints(constraints)

    if not columns and not ordered_constraints:
        # A table with no readable columns is still a real relation; rendering
        # `CREATE TABLE x ();` is what PostgreSQL itself accepts for one.
        lines.append(f"CREATE TABLE {name} ();")
    else:
        lines.append(f"CREATE TABLE {name} (")
        body: list[tuple[str, str, str]] = []  # (role, key, text)
        for column in columns:
            body.append(("column", column.name, _column_line(column)))
        for constraint in ordered_constraints:
            body.append(
                (
                    "constraint",
                    constraint.name,
                    f"    CONSTRAINT {quote_ident(constraint.name)} "
                    f"{constraint.definition}",
                )
            )
        for position, (role, key, text) in enumerate(body):
            last = position == len(body) - 1
            offset = len(lines)
            lines.append(text if last else f"{text},")
            if role == "column":
                column_offsets[key] = offset
            else:
                constraint_offsets[key] = offset
        lines.append(");")

    standalone = _standalone_indexes(indexes)
    if standalone:
        lines.append("")
        for index in standalone:
            index_offsets[index.name] = len(lines)
            lines.append(_statement(index.definition))

    comments = _comment_lines(table, "TABLE")
    if comments:
        lines.append("")
        lines.extend(comments)

    return RelationDdl(
        lines=lines,
        column_offsets=column_offsets,
        constraint_offsets=constraint_offsets,
        index_offsets=index_offsets,
    )


def build_view_ddl(table: TableInfo, indexes=()) -> RelationDdl:
    """`CREATE VIEW` / `CREATE MATERIALIZED VIEW` from `pg_get_viewdef`.

    Unlike a table, a view's body is **not** reconstructed -- PostgreSQL hands
    back the whole `SELECT`, so it is emitted verbatim and carries no
    incompleteness notice. A matview's indexes are appended the same way a
    table's are.
    """
    name = qualified_ident(table.name)
    label = "MATERIALIZED VIEW" if table.kind == "matview" else "VIEW"
    lines: list[str] = []
    index_offsets: dict[str, int] = {}
    column_offsets: dict[str, int] = {}

    definition = (table.view_definition or "").strip()
    if definition:
        lines.append(f"CREATE {label} {name} AS")
        lines.extend(_statement(definition).splitlines())
    else:
        # Honest absence rather than an invented body -- the same rule the
        # table reconstruction follows.
        lines.append(
            f"-- {label} {table.name}: definition not available from this connection --"
        )
        for column in table.columns or []:
            column_offsets[column.name] = len(lines)
            lines.append(f"--     {quote_ident(column.name)} {column.data_type}")

    standalone = _standalone_indexes(indexes)
    if standalone:
        lines.append("")
        for index in standalone:
            index_offsets[index.name] = len(lines)
            lines.append(_statement(index.definition))

    comments = _comment_lines(table, label)
    if comments:
        lines.append("")
        lines.extend(comments)

    return RelationDdl(
        lines=lines, column_offsets=column_offsets, index_offsets=index_offsets
    )


def _comment_lines(table: TableInfo, label: str) -> list[str]:
    name = qualified_ident(table.name)
    lines: list[str] = []
    if table.comment:
        lines.append(f"COMMENT ON {label} {name} IS {_quote_literal(table.comment)};")
    for column in table.columns or []:
        if column.comment:
            lines.append(
                f"COMMENT ON COLUMN {name}.{quote_ident(column.name)} "
                f"IS {_quote_literal(column.comment)};"
            )
    return lines


def build_relation_ddl(table: TableInfo, constraints=(), indexes=()) -> RelationDdl:
    """Dispatch on `TableInfo.kind` -- the one entry point `db/ddl_buffer.py`
    calls, so the buffer never branches on relation kind itself."""
    if table.kind in ("view", "matview"):
        return build_view_ddl(table, indexes)
    return build_table_ddl(table, constraints, indexes)
