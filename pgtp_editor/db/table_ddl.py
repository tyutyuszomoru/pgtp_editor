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
in its own output.** PostgreSQL has no `pg_get_tabledef`; this reads columns,
constraints, indexes and comments. Presenting that text as *"the table's DDL"*
without saying so is a silent wrong result (§1's master invariant), so every
table's text carries `RECONSTRUCTION_NOTICE` -- **per table, not once per
buffer** (see below). Nothing here ever *guesses*: a partitioned or inherited
table renders as the columns and constraints that were read, with the omission
named, never with an invented `PARTITION BY`.

**Two structural gaps remain, by decision rather than by neglect**
(`DEC-260811022536`, 2026-08-11): **table inheritance and partitioning**. They
restructure the statement -- partition key, partition-of clauses, per-partition
rendering, `INHERITS` with inherited columns suppressed -- and no feature
consumes this buffer as anything but read-only text, so closing them would buy
partitioning support before anything needs it. The boundary is *stated*, not
*pending*: `DEC-260811094437` holds the trigger that would reopen it (the first
feature that consumes this buffer as an input rather than a view). A reader
finding the two-gap notice should read it as a drawn line, not as a half-done
job.

**The two per-column gaps ARE closed** (same ruling): identity columns render
`GENERATED ALWAYS / BY DEFAULT AS IDENTITY` and stored generated columns render
`GENERATED ALWAYS AS (<expr>) STORED`, from `ColumnInfo.identity` /
`ColumnInfo.generated`. They extend the column line and nothing else, which is
why they were cheap, and nearly every table has a surrogate key, which is why
they were worth it. Each is **mutually exclusive with a rendered `DEFAULT`**:
an identity column's `nextval` is the sequence's business, not a default clause,
and a generated column's expression *is* its `pg_attrdef` row -- printing both
would render the expression twice.

**`SERIAL` is rendered as the catalog holds it -- `integer DEFAULT
nextval('...'::regclass)` -- never as the word `SERIAL`.** There is a real
argument the other way (`SERIAL` is what the human wrote, and it is shorter),
and it is rejected for three reasons. `SERIAL` is not a type: it is a macro for
*integer + sequence + ownership*, so emitting it would mean **inferring** that
the sequence behind this column is the one `SERIAL` would have created --
inference is exactly what this module does not do. It also *loses* information a
read-only inspection pane exists to show, namely which sequence feeds the
column, which need not be the canonically named one. And `pg_dump` makes the
same call for the same reason. So a `SERIAL` column is fully rendered here
already; what is not emitted is its owned sequence's own `CREATE SEQUENCE`,
which is a separate catalog object and not part of this statement -- the same
way an index's `CREATE INDEX` is emitted as its own statement rather than folded
into the column line.

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
#: The second line names what is out of scope. It named FOUR things until
#: `DEC-260811022536` closed the two per-column ones (identity/`SERIAL` and
#: `GENERATED` columns are rendered now); the remaining two are **structural and
#: deliberately out of scope**, not a to-do. The wording says "does not cover"
#: rather than "not reconstructed yet" for exactly that reason: it is a stated
#: boundary a reader can rely on, while still being honest that a partitioned or
#: inherited table's shape is missing from the text they are looking at.
RECONSTRUCTION_NOTICE_DETAIL = (
    "--       this is NOT the original CREATE statement, and it does not cover "
    "table inheritance or partitioning."
)

#: The `SERIAL`/`nextval` clone hazard, emitted per table **in BOTH modes**
#: (`FQ-260812022749`, owner ruling: **warn only**).
#:
#: Part 5 settled what a table's complete DDL is *for*: it is a **clone
#: source**, read by a developer who renames it and executes it in the SQL
#: Console. That makes a `nextval()` default a concrete, checkable defect
#: generator -- the clone's default still points at the **original** table's
#: sequence, so the two tables draw from one counter and dropping the original
#: breaks the clone.
#:
#: **Why it applies to full mode too, which is the counter-intuitive half.**
#: `pg_dump` *does* emit the owned `CREATE SEQUENCE` -- but in a **different
#: section of the file** from the table, so a developer copying the
#: `CREATE TABLE` still does not get it. Neither mode is clone-safe here, so
#: neither mode may be the one that stays quiet.
#:
#: **Warn-only, by ruling.** No `CREATE SEQUENCE` span is emitted, and nothing
#: is restructured to "fix" this -- the correct clone is a judgement call about
#: whether the two tables should share a counter, and the app does not make it.
SEQUENCE_CLONE_HAZARD = (
    "-- WARNING: a column default calls nextval() — a COPY of this statement "
    "under a new name would draw from"
)
SEQUENCE_CLONE_HAZARD_DETAIL = (
    "--          the ORIGINAL table's sequence. The owned CREATE SEQUENCE is "
    "not part of this statement; give a clone its own."
)

#: `nextval('pr.orders_id_seq'::regclass)` -- what a `SERIAL`/`BIGSERIAL`
#: column's default looks like once PostgreSQL has expanded the macro. Matched
#: on the catalog's own `pg_attrdef` text, never on the word `SERIAL`, which
#: never reaches the catalog at all.
_NEXTVAL_DEFAULT = re.compile(r"\bnextval\s*\(", re.IGNORECASE)


def has_sequence_default(table: TableInfo) -> bool:
    """Does any of `table`'s columns default to `nextval(...)`?

    An **identity** column deliberately does not count: cloning
    `GENERATED ... AS IDENTITY` creates a *new* implicit sequence for the new
    table, so the shared-counter hazard does not arise -- warning about it
    would train the reader to skip the line that matters.
    """
    for column in table.columns or []:
        if column.identity in _IDENTITY_CLAUSE:
            continue
        if column.generated == "s":
            continue
        if column.default and _NEXTVAL_DEFAULT.search(column.default):
            return True
    return False


def sequence_clone_hazard_lines(table: TableInfo) -> list[str]:
    """The two hazard lines for `table`, or `[]`. One home for the wording, so
    the full-mode and restricted-mode notices cannot drift apart."""
    if table.kind not in (None, "", "table"):
        # Views and matviews are not cloned by copying a `CREATE TABLE`, and a
        # matview's `nextval` default is its base table's business.
        return []
    if not has_sequence_default(table):
        return []
    return [SEQUENCE_CLONE_HAZARD, SEQUENCE_CLONE_HAZARD_DETAIL]

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


#: `pg_attribute.attidentity` -> the SQL that declares it. `''` (not an identity
#: column) is normalized to `None` by `introspect._build_tables`, so an unknown
#: value here means a catalog this build has never seen -- and the right answer
#: for that is to render no identity clause rather than invent one.
_IDENTITY_CLAUSE = {
    "a": " GENERATED ALWAYS AS IDENTITY",
    "d": " GENERATED BY DEFAULT AS IDENTITY",
}


def _column_line(column: ColumnInfo) -> str:
    """ONE line per column, always -- `column_offsets` maps a column name to a
    line index, and every subsequent constraint/column offset is derived from
    `len(lines)`, so a column that wrapped onto two lines would silently shift
    every offset below it and break click-to-navigate.

    Order of clauses: type, `NOT NULL`, then **exactly one** of the generated
    expression, the identity clause, or the default (`DEC-260811022536`) -- see
    the module docstring for why the three are mutually exclusive.
    """
    parts = [f"    {quote_ident(column.name)} {column.data_type}"]
    if not column.is_nullable:
        parts.append(" NOT NULL")
    if column.generated == "s" and column.default:
        # The expression IS the `pg_attrdef` row, i.e. `ColumnInfo.default`; it
        # replaces the default clause instead of accompanying it.
        parts.append(f" GENERATED ALWAYS AS ({column.default}) STORED")
    elif column.identity in _IDENTITY_CLAUSE:
        # An identity column's `nextval` belongs to its implicit sequence, so
        # rendering a DEFAULT beside the identity clause would be both wrong
        # (PostgreSQL rejects it) and redundant.
        parts.append(_IDENTITY_CLAUSE[column.identity])
    elif column.default:
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
    # The clone hazard rides directly under the incompleteness notice, inside
    # the region a whole-object copy takes with it (`FQ-260812022749` Part 5).
    lines.extend(sequence_clone_hazard_lines(table))
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
