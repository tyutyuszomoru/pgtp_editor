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

# pgtp_editor/db/introspect.py
"""Read-only PostgreSQL introspection via ``pg_catalog``.

`pg_catalog` (not `information_schema`) is queried so materialized views,
relation kind, PK/FK membership, and pretty types (`format_type`) are all
available in one coherent model.

psycopg is imported lazily and ONLY inside `run_queries` — the sole function
that opens a connection. `fetch_schema`/`test_connection` take an injectable
`runner=` callable (defaulting to `run_queries`); tests pass a fake returning
canned catalog rows, so no live database is needed and psycopg need not even be
importable to run the suite.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from pgtp_editor import debuglog

from .config import ConnectionParams

_log = logging.getLogger(__name__)

Rows = list[tuple]
Runner = Callable[[ConnectionParams, list[str]], list[Rows]]


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    is_pk: bool
    is_fk: bool
    is_nullable: bool
    default: str | None
    fk_target: str | None = None  # referenced "schema.table.column" for FK columns
    #: `pg_catalog.col_description(attrelid, attnum)` -- the column's own
    #: comment, if one was ever set via `COMMENT ON COLUMN` (§18.1's
    #: 2026-08-05 Properties-panel widening). Trailing and defaulted so
    #: existing positional/keyword `ColumnInfo(...)` constructions across the
    #: codebase and tests stay valid. `None` for a column with no comment set.
    comment: str | None = None


@dataclass(frozen=True)
class TableInfo:
    name: str  # "schema.table"
    kind: str  # "table" | "view" | "matview"
    columns: list[ColumnInfo] = field(default_factory=list)
    #: `pg_get_viewdef` text for `kind in ("view", "matview")`, else None
    #: (§18.5 D2's "recorded gap" closure -- `DatabaseSchema` previously
    #: modeled no view definitions at all, so a routine touching a view
    #: failed to compile in the sandbox baseline).
    view_definition: str | None = None
    #: `pg_catalog.obj_description(c.oid, 'pg_class')` -- the relation's OWN
    #: comment (`pg_description.objsubid = 0`), as opposed to the per-column
    #: rows (`objsubid = attnum`) that fill `ColumnInfo.comment`. Same
    #: convention as that field in every respect: `None` when no
    #: `COMMENT ON TABLE` was ever set (never `""`), and trailing/defaulted so
    #: every existing positional or keyword `TableInfo(...)` construction
    #: across the codebase and tests stays valid.
    #:
    #: Read by `Set Table Comment…` to SEED its dialog: a blank box means
    #: `IS NULL`, the only way to ask for a comment's removal, so without this
    #: an untouched OK silently dropped the table's existing comment.
    comment: str | None = None


@dataclass(frozen=True)
class RoutineInfo:
    """A function or procedure, sourced from ``pg_proc`` (§18.1)."""

    schema: str
    name: str
    arg_types: list[str] = field(default_factory=list)
    return_type: str | None = None
    language: str = ""
    source: str = ""  # full CREATE [OR REPLACE] FUNCTION/PROCEDURE text
    kind: str = "function"  # "function" | "procedure"
    # Input (IN/INOUT) argument (name, type) pairs in declared order -- what
    # the BrowserPanel tree lists as child leaves. `arg_types` above stays the
    # types-only call signature that build_ddl_text's banner comment uses.
    # A routine with no input arguments has `args == []`.
    args: list[tuple[str, str]] = field(default_factory=list)

    @property
    def signature(self) -> str:
        """`schema.name(argtype, argtype)` — PostgreSQL's real identity.

        **The single source of this string.** A function is identified by
        `(schema, name, argument types)`, so this — not `schema.name` — is what
        keys `DatabaseSchema.routines`, what `db/ddl_buffer.py`'s banner
        comment prints, and what `db/schema_diff.py::routine_identity`
        compares. Consume it verbatim; never re-render it, or the four
        spellings drift apart (BUG-018).

        A zero-argument routine renders with **empty parens** — `public.f()`,
        never bare `public.f` — which is exactly what distinguishes `f()` from
        `f(integer)`. The joiner is `", "` (comma + space) and the source is
        `arg_types` (types only), not `args` (name/type pairs).
        """
        return f"{self.schema}.{self.name}({', '.join(self.arg_types)})"


@dataclass(frozen=True)
class TriggerInfo:
    """A trigger, sourced from ``pg_trigger`` (§18.1)."""

    schema: str
    table: str
    name: str
    timing: str  # "before" | "after" | "instead of"
    events: list[str] = field(default_factory=list)  # "insert"/"update"/"delete"/"truncate"
    function_name: str = ""
    definition: str = ""  # full CREATE TRIGGER text


@dataclass(frozen=True)
class ConstraintInfo:
    """A **named** table constraint, sourced from ``pg_constraint`` (FQ-025).

    `ColumnInfo.is_pk`/`is_fk`/`fk_target` answer *"is this column part of a
    key?"*; this answers *"which named objects can I drop or rename?"* — the
    question the unified `Drop constraint…` / `Rename constraint` dialogs ask.
    `con.conname` was never selected before FQ-025, so no picker could exist.

    `kind` is lowercase prose, following `TableInfo.kind` / `TriggerInfo.timing`
    (the UI upper-cases for display): ``"primary key"``, ``"foreign key"``,
    ``"unique"``, ``"check"`` or ``"exclude"``. `columns` are the constrained
    columns in `conkey` order and can legitimately be **empty** — a
    table-level `CHECK` referencing no column (`CHECK (true)`) has a NULL
    `conkey`; such a constraint is still droppable, so it is captured, and
    `definition` (`pg_get_constraintdef`) is what a picker shows for it.
    """

    schema: str
    table: str
    name: str
    kind: str  # "primary key" | "foreign key" | "unique" | "check" | "exclude"
    columns: list[str] = field(default_factory=list)
    definition: str = ""  # `pg_get_constraintdef` -- e.g. "CHECK ((qty > 0))"

    @property
    def qualified_name(self) -> str:
        """`schema.table.name` -- the key `DatabaseSchema.constraints` uses
        (the same shape `DatabaseSchema.triggers` is keyed by)."""
        return f"{self.schema}.{self.table}.{self.name}"

    @property
    def table_name(self) -> str:
        """`schema.table` -- the `DatabaseSchema.tables` key this belongs to."""
        return f"{self.schema}.{self.table}"


@dataclass(frozen=True)
class IndexInfo:
    """An index, sourced from ``pg_index`` (FQ-025).

    **Constraint-backed indexes are captured but marked, never silently
    offered as droppable.** PostgreSQL creates an implicit index for every
    PRIMARY KEY / UNIQUE / EXCLUDE constraint and then *refuses*
    `DROP INDEX` on it ("cannot drop index ... because constraint ...
    requires it") -- the user has to drop the constraint instead. Rather than
    filter those rows out (which would make a "why is my unique index
    missing from the list?" mystery), the backing constraint's name is
    carried in `constraint_name` and `is_constraint_backed` is True. **A
    `Drop index` picker must list only `is_constraint_backed == False` rows**
    and route the rest to `Drop constraint…`; the full list stays available
    for display purposes.

    `columns` come from `pg_get_indexdef(indexrelid, n, true)` per key
    attribute, so an expression index yields its expression text rather than a
    missing entry. INCLUDE columns are not listed (`indnkeyatts` bounds the
    loop) -- they are visible in `definition` if ever needed.
    """

    schema: str
    table: str
    name: str
    columns: list[str] = field(default_factory=list)
    is_unique: bool = False
    is_primary: bool = False
    method: str = ""  # `pg_am.amname` -- "btree" | "gin" | "gist" | ...
    definition: str = ""  # full CREATE INDEX text (`pg_get_indexdef`)
    #: Name of the constraint this index implicitly backs, or None for a
    #: standalone `CREATE INDEX`. See the class docstring -- this is the
    #: droppable-vs-not distinction.
    constraint_name: str | None = None

    @property
    def is_constraint_backed(self) -> bool:
        """True when a PK/UNIQUE/EXCLUDE constraint owns this index, so
        `DROP INDEX` on it would be rejected by PostgreSQL."""
        return self.constraint_name is not None

    @property
    def qualified_name(self) -> str:
        """`schema.name` -- an index lives in its table's schema and its name
        is unique there, so this (not `schema.table.name`) is its identity and
        the key `DatabaseSchema.indexes` uses."""
        return f"{self.schema}.{self.name}"

    @property
    def table_name(self) -> str:
        """`schema.table` -- the `DatabaseSchema.tables` key this belongs to."""
        return f"{self.schema}.{self.table}"


@dataclass(frozen=True)
class TypeInfo:
    """A domain or composite type, sourced from ``pg_type`` (§18.5 D2's
    "recorded gap" closure) -- just enough to reconstruct a catalog-shape
    `CREATE DOMAIN`/`CREATE TYPE ... AS (...)` for the sandbox baseline.

    Deliberately minimal, matching `build_baseline_sql`'s "catalog shape,
    not full fidelity" posture (§18.5 D2): a **domain's** `CHECK` constraints
    are NOT captured here ("catalog-based `plpgsql_check` reads no rows, only
    needs types to exist").

    Note the narrowed scope of that omission since FQ-025: **table** `CHECK`
    constraints ARE now captured, as `ConstraintInfo` on
    `DatabaseSchema.constraints`, because the DDL Explorer's unified
    `Drop constraint…` must list them by name. Only domain constraints
    (`pg_constraint.conrelid = 0`, excluded by `_CONSTRAINTS_SQL`'s join to
    `pg_class`) remain unmodeled.
    """

    schema: str
    name: str
    kind: str  # "domain" | "composite"
    #: Domain only -- the `format_type` of the underlying base type.
    base_type: str | None = None
    #: Domain only -- `True` when the domain is declared `NOT NULL`.
    not_null: bool = False
    #: Composite only -- ordered `(attribute_name, format_type)` pairs.
    attributes: list[tuple[str, str]] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        """`schema.name` -- the key `DatabaseSchema.types` uses."""
        return f"{self.schema}.{self.name}"


@dataclass(frozen=True)
class DatabaseSchema:
    tables: dict[str, TableInfo] = field(default_factory=dict)
    routines: dict[str, RoutineInfo] = field(default_factory=dict)
    triggers: dict[str, TriggerInfo] = field(default_factory=dict)
    #: Domains and composite types, keyed by `schema.name` (§18.5 D2's
    #: "recorded gap" closure -- previously unmodeled entirely).
    types: dict[str, TypeInfo] = field(default_factory=dict)
    #: Named table constraints, keyed by `schema.table.name` (FQ-025). Filled
    #: by every fetch that runs `SCHEMA_SQL` -- the rows come free with the
    #: constraint query the PK/FK column flags already use.
    constraints: dict[str, ConstraintInfo] = field(default_factory=dict)
    #: Indexes, keyed by `schema.index_name` (FQ-025). Only
    #: `fetch_routines_and_triggers` runs the index query (`INDEX_SQL`), so
    #: this is `{}` after `fetch_schema`/`snapshot_for_baseline` -- neither
    #: DB Check nor the sandbox baseline needs indexes.
    indexes: dict[str, IndexInfo] = field(default_factory=dict)

    def has_table(self, name: str) -> bool:
        return name in self.tables

    def table(self, name: str) -> TableInfo | None:
        return self.tables.get(name)

    def column(self, name: str, col: str) -> ColumnInfo | None:
        table = self.tables.get(name)
        if table is None:
            return None
        for column in table.columns:
            if column.name == col:
                return column
        return None

    def constraints_for(self, name: str) -> list[ConstraintInfo]:
        """Every named constraint on ``schema.table``, in catalog order
        (FQ-025) -- what the unified `Drop constraint…` picker lists. Empty
        for a table with no constraints, and for an unknown table."""
        return [c for c in self.constraints.values() if c.table_name == name]

    def indexes_for(self, name: str) -> list[IndexInfo]:
        """Every index on ``schema.table``, **including** constraint-backed
        ones (FQ-025). A `Drop index` picker must filter
        `is_constraint_backed` out -- see `IndexInfo`."""
        return [i for i in self.indexes.values() if i.table_name == name]


# --- pg_catalog queries -----------------------------------------------------
# Non-system schemas only (exclude pg_catalog / information_schema / pg_toast).
# Order of the three queries is load-bearing: fetch_schema unpacks them
# positionally as [relations, columns, constraints].

# Widened (2026-08-09) with a FOURTH selected value, additively: the relation's
# own comment. `obj_description(c.oid, 'pg_class')` is `pg_description` filtered
# to `objsubid = 0` -- the same catalog table `_COLUMNS_SQL`'s
# `col_description(a.attrelid, a.attnum)` reads at `objsubid = attnum`, so this
# is the existing mechanism keyed one level up, not a second one. It rides on
# the relation query (one row per relation) rather than the per-column query,
# and no new round trip is added. The first three values keep their meaning and
# position, and `_build_tables` unpacks the row tolerantly (`*rest`), so the
# many canned 3-tuple relation rows across the suite keep working and simply
# yield `comment=None`.
_RELATIONS_SQL = """
SELECT n.nspname, c.relname, c.relkind,
       pg_catalog.obj_description(c.oid, 'pg_class')
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
"""

_COLUMNS_SQL = """
SELECT n.nspname, c.relname, a.attname,
       pg_catalog.format_type(a.atttypid, a.atttypmod),
       a.attnotnull,
       pg_catalog.pg_get_expr(d.adbin, d.adrelid),
       pg_catalog.col_description(a.attrelid, a.attnum)
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE c.relkind IN ('r', 'p', 'v', 'm')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY a.attnum
"""

# Widened by FQ-025 (slice 2) along three axes, all ADDITIVE -- the first five
# selected values keep their meaning and position, so every existing consumer
# (`_build_tables`'s PK/FK column flags, DB Check, the sandbox baseline) is
# untouched:
#   1. `con.conname` is now selected (position 6). Nothing could offer a
#      "drop this constraint" list without it.
#   2. `contype` now admits 'u' (UNIQUE), 'c' (CHECK) and 'x' (EXCLUDE) on top
#      of 'p'/'f'. `_build_tables` ignores the three new types; only
#      `_build_constraints` reads them.
#   3. `pg_get_constraintdef` (position 7) -- the one thing that distinguishes
#      two CHECKs on the same table for a user about to drop one.
# The `generate_subscripts`/`pg_attribute` joins became LEFT joins so a
# constraint with a NULL `conkey` (a table-level `CHECK (true)`) still yields
# one row with a NULL column name instead of vanishing. PK/FK constraints
# always have a `conkey`, so their rows are bit-for-bit what they were.
# Domain constraints have `conrelid = 0` and are dropped by the inner join to
# `pg_class`, as before.
_CONSTRAINTS_SQL = """
SELECT n.nspname, c.relname, lc.attname, con.contype,
       CASE WHEN con.contype = 'f' THEN rn.nspname || '.' || rc.relname || '.' || rc_att.attname END,
       con.conname,
       pg_catalog.pg_get_constraintdef(con.oid)
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN generate_subscripts(con.conkey, 1) AS k(i) ON true
LEFT JOIN pg_catalog.pg_attribute lc
     ON lc.attrelid = con.conrelid AND lc.attnum = con.conkey[k.i]
LEFT JOIN pg_catalog.pg_class rc ON rc.oid = con.confrelid
LEFT JOIN pg_catalog.pg_namespace rn ON rn.oid = rc.relnamespace
LEFT JOIN pg_catalog.pg_attribute rc_att
     ON rc_att.attrelid = con.confrelid AND rc_att.attnum = con.confkey[k.i]
WHERE con.contype IN ('p', 'f', 'u', 'c', 'x')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY n.nspname, c.relname, con.conname, k.i
"""

SCHEMA_SQL: list[str] = [_RELATIONS_SQL, _COLUMNS_SQL, _CONSTRAINTS_SQL]

_KIND_BY_RELKIND = {"r": "table", "p": "table", "v": "view", "m": "matview"}

#: `pg_constraint.contype` -> the lowercase prose `ConstraintInfo.kind` carries
#: (FQ-025). Only these five are selected by `_CONSTRAINTS_SQL`; a row with any
#: other contype is ignored by `_build_constraints` rather than guessed at.
_KIND_BY_CONTYPE = {
    "p": "primary key",
    "f": "foreign key",
    "u": "unique",
    "c": "check",
    "x": "exclude",
}

# --- Routines & triggers (§18.1 DDL Explorer) -------------------------------
# A separate query pair from SCHEMA_SQL/fetch_schema above -- routines/triggers
# are only needed by the DDL Explorer, not by the existing DB Check features,
# so this stays an independent fetch rather than growing fetch_schema's
# established 3-query contract.

_ROUTINES_SQL = """
SELECT n.nspname, p.proname, p.prokind,
       pg_catalog.format_type(p.prorettype, NULL),
       l.lanname,
       pg_catalog.pg_get_functiondef(p.oid),
       COALESCE(
           (SELECT array_agg(pg_catalog.format_type(t.oid, NULL) ORDER BY a.ord)
            FROM unnest(p.proargtypes) WITH ORDINALITY AS a(oid, ord)
            JOIN pg_catalog.pg_type t ON t.oid = a.oid),
           ARRAY[]::text[]
       ),
       COALESCE(
           (SELECT array_agg(pg_catalog.format_type(t.oid, NULL) ORDER BY a.ord)
            FROM unnest(COALESCE(p.proallargtypes, p.proargtypes::oid[]))
                 WITH ORDINALITY AS a(oid, ord)
            JOIN pg_catalog.pg_type t ON t.oid = a.oid),
           ARRAY[]::text[]
       ),
       p.proargnames,
       p.proargmodes::text[]
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
JOIN pg_catalog.pg_language l ON l.oid = p.prolang
WHERE p.prokind IN ('f', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
"""

_TRIGGERS_SQL = """
SELECT n.nspname, c.relname, t.tgname, t.tgtype, p.proname,
       pg_catalog.pg_get_triggerdef(t.oid)
FROM pg_catalog.pg_trigger t
JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
WHERE NOT t.tgisinternal
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
"""

ROUTINE_TRIGGER_SQL: list[str] = [_ROUTINES_SQL, _TRIGGERS_SQL]

# --- Indexes (FQ-025) -------------------------------------------------------
# A separate one-query list, appended by `fetch_routines_and_triggers` only:
# the DDL Explorer's `Drop index` picker is the sole consumer, and neither DB
# Check (`fetch_schema`) nor the sandbox baseline (`snapshot_for_baseline`,
# whose posture is "catalog shape, not full fidelity") needs indexes -- so
# their query contracts stay exactly as they were.
#
# `indisprimary`/`conindid` carry the droppable-vs-not distinction documented
# on `IndexInfo`: an index a PK/UNIQUE/EXCLUDE constraint owns cannot be
# dropped with `DROP INDEX`. Key columns are rendered one at a time by
# `pg_get_indexdef(indexrelid, n, true)` so expression indexes yield their
# expression text; `indnkeyatts` bounds the loop, excluding INCLUDE columns.
_INDEXES_SQL = """
SELECT n.nspname, c.relname, ic.relname, am.amname,
       i.indisunique, i.indisprimary,
       pg_catalog.pg_get_indexdef(i.indexrelid),
       COALESCE(
           (SELECT array_agg(pg_catalog.pg_get_indexdef(i.indexrelid, k.n::integer, true)
                             ORDER BY k.n)
            FROM generate_series(1, i.indnkeyatts) AS k(n)),
           ARRAY[]::text[]
       ),
       (SELECT con.conname
        FROM pg_catalog.pg_constraint con
        WHERE con.conindid = i.indexrelid
        LIMIT 1)
FROM pg_catalog.pg_index i
JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid
JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_am am ON am.oid = ic.relam
WHERE c.relkind IN ('r', 'p', 'm')
  AND i.indislive
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY n.nspname, c.relname, ic.relname
"""

INDEX_SQL: list[str] = [_INDEXES_SQL]

# --- View definitions & domain/composite types (§18.5 D2 "recorded gap") ----
# A separate query pair, consumed ONLY by `snapshot_for_baseline` -- neither
# `fetch_schema` nor `fetch_routines_and_triggers` needs view bodies or
# domain/composite shapes, so this does not widen either of those two
# established contracts. `pg_get_viewdef` needs relkind IN ('v', 'm'); the
# `pg_type` query needs typtype IN ('d', 'c') (domain, composite), per §18.5
# D2's explicit instruction.

_VIEWDEFS_SQL = """
SELECT n.nspname, c.relname, pg_catalog.pg_get_viewdef(c.oid, true)
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('v', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
"""

# Domains: base type + NOT NULL only -- a DOMAIN's CHECK constraints are
# deliberately NOT captured (§18.5 D2's "catalog-based, reads no rows"
# baseline: a domain CHECK is data-validation fidelity). Scope note (FQ-025):
# this omission no longer extends to TABLE check constraints -- those are
# captured by `_CONSTRAINTS_SQL`/`ConstraintInfo` so the DDL Explorer can list
# them by name for `Drop constraint…`. Domain constraints have
# `pg_constraint.conrelid = 0` and are excluded there by the join to
# `pg_class`, so the two statements do not conflict. Composites:
# ordered attribute (name, type) pairs, sourced the same way table columns
# are (`pg_attribute` + `format_type`), since a composite type IS a
# `pg_class` row with relkind 'c' under the hood.
_TYPES_SQL = """
SELECT n.nspname, t.typname, t.typtype,
       pg_catalog.format_type(t.typbasetype, t.typtypmod),
       t.typnotnull,
       COALESCE(
           (SELECT array_agg(a.attname ORDER BY a.attnum)
            FROM pg_catalog.pg_attribute a
            WHERE a.attrelid = t.typrelid AND a.attnum > 0 AND NOT a.attisdropped),
           ARRAY[]::text[]
       ),
       COALESCE(
           (SELECT array_agg(pg_catalog.format_type(a.atttypid, a.atttypmod) ORDER BY a.attnum)
            FROM pg_catalog.pg_attribute a
            WHERE a.attrelid = t.typrelid AND a.attnum > 0 AND NOT a.attisdropped),
           ARRAY[]::text[]
       )
FROM pg_catalog.pg_type t
JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
WHERE t.typtype IN ('d', 'c')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  -- A composite type's OWN row-type entry (created implicitly by every
  -- CREATE TABLE) must be excluded -- only "free-standing" CREATE TYPE ... AS
  -- (...) composites are wanted here; table row-types are already fully
  -- captured via SCHEMA_SQL/_build_tables and would otherwise duplicate as a
  -- phantom `CREATE TYPE` for every table.
  AND NOT EXISTS (
      SELECT 1 FROM pg_catalog.pg_class c
      WHERE c.oid = t.typrelid AND c.relkind != 'c'
  )
"""

BASELINE_EXTRA_SQL: list[str] = [_VIEWDEFS_SQL, _TYPES_SQL]

# pg_trigger.tgtype bit flags (see Postgres's trigger.h) -- decoded in Python
# rather than in SQL so the mapping is unit-testable without a live database.
_TRIGGER_BEFORE = 1 << 1
_TRIGGER_INSERT = 1 << 2
_TRIGGER_DELETE = 1 << 3
_TRIGGER_UPDATE = 1 << 4
_TRIGGER_TRUNCATE = 1 << 5
_TRIGGER_INSTEAD = 1 << 6


# pg_proc.proargmodes values that denote an argument the CALLER passes in:
# i=IN, b=INOUT, v=VARIADIC. (o=OUT and t=TABLE are outputs.)
_INPUT_ARG_MODES = frozenset("ibv")


def _input_args(
    all_arg_types: list[str] | None,
    arg_names: list[str] | None,
    arg_modes: list[str] | None,
) -> list[tuple[str, str]]:
    """Correlate ``pg_proc``'s parallel argument arrays into input-argument
    ``(name, type)`` pairs in declared order (§18.1).

    ``all_arg_types`` is ``COALESCE(proallargtypes, proargtypes)`` already
    run through ``format_type``; ``arg_names`` is ``proargnames``;
    ``arg_modes`` is ``proargmodes``. Postgres leaves ``proargmodes`` NULL
    when every argument is IN (the common case) -- an absent mode therefore
    reads as IN. Returns the modes that are genuinely *input* arguments:
    IN (``i``), INOUT (``b``) and VARIADIC (``v``) -- a variadic parameter is
    passed in by the caller, so omitting it would silently hide a real
    parameter from the tree. OUT (``o``) and TABLE (``t``) entries are
    dropped. An unnamed argument yields ``""`` for its name.

    Kept in Python (like ``_decode_trigger_type``) so the correlation is
    unit-testable without a live database.
    """
    pairs: list[tuple[str, str]] = []
    for index, type_name in enumerate(all_arg_types or []):
        mode = "i"
        if arg_modes and index < len(arg_modes) and arg_modes[index]:
            mode = arg_modes[index]
        if mode not in _INPUT_ARG_MODES:
            continue
        name = ""
        if arg_names and index < len(arg_names) and arg_names[index]:
            name = arg_names[index]
        pairs.append((name, type_name))
    return pairs


def _decode_trigger_type(tgtype: int) -> tuple[str, list[str]]:
    """Return ``(timing, events)`` decoded from a raw ``pg_trigger.tgtype`` bitmask."""
    if tgtype & _TRIGGER_INSTEAD:
        timing = "instead of"
    elif tgtype & _TRIGGER_BEFORE:
        timing = "before"
    else:
        timing = "after"
    events: list[str] = []
    if tgtype & _TRIGGER_INSERT:
        events.append("insert")
    if tgtype & _TRIGGER_UPDATE:
        events.append("update")
    if tgtype & _TRIGGER_DELETE:
        events.append("delete")
    if tgtype & _TRIGGER_TRUNCATE:
        events.append("truncate")
    return timing, events


def run_queries(
    params: ConnectionParams,
    sql_list: list[str],
    connect_timeout: int = 10,
) -> list[Rows]:
    """Open ONE connection, run each SQL, and return a list of row-lists.

    The ONLY function that touches psycopg — imported here, lazily, so the rest
    of the package (and the test suite) loads without the driver installed.

    ``connect_timeout`` (seconds) bounds the connect attempt so an unreachable
    or slow host fails fast instead of blocking on the OS TCP timeout. This
    matters even when the call runs off the GUI thread — it caps how long a
    worker lingers.
    """
    import psycopg  # noqa: PLC0415 — lazy on purpose (see module docstring)

    connection = psycopg.connect(
        host=params.host or None,
        port=params.port or None,
        dbname=params.database or None,
        user=params.user or None,
        password=params.password or None,
        connect_timeout=connect_timeout,
    )
    try:
        results: list[Rows] = []
        for sql in sql_list:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                results.append(cursor.fetchall())
        return results
    finally:
        connection.close()


def _build_tables(
    relation_rows: Rows,
    column_rows: Rows,
    constraint_rows: Rows,
    view_definition_rows: Rows | None = None,
) -> dict[str, TableInfo]:
    """Assemble ``{"schema.table": TableInfo}`` from `SCHEMA_SQL`'s three
    row-lists. Shared by `fetch_schema` and `fetch_routines_and_triggers`
    (§18.6) so the one table/column-assembly implementation backs both.

    `view_definition_rows` (from `_VIEWDEFS_SQL`, one row per `("v", "m")`
    relation) is optional and additive -- both existing callers omit it and
    get `view_definition=None` on every `TableInfo` exactly as before;
    `snapshot_for_baseline` is the only caller that supplies it.
    """
    # Tolerant of the pre-2026-08-09 3-tuple row shape on purpose (the same
    # posture `_build_constraints` takes): a relation row without a 4th value
    # simply carries no comment, so canned rows across the suite keep working.
    kinds: dict[str, str] = {}
    comments: dict[str, str | None] = {}
    for schema_name, rel_name, relkind, *rest in relation_rows:
        key = f"{schema_name}.{rel_name}"
        kinds[key] = _KIND_BY_RELKIND.get(relkind, "table")
        comments[key] = rest[0] if rest else None

    # Constraint membership: (table_key, column_name) -> contype set. FK rows
    # also carry the referenced "schema.table.column" (None for PKs).
    pk_columns: set[tuple[str, str]] = set()
    fk_columns: set[tuple[str, str]] = set()
    fk_targets: dict[tuple[str, str], str] = {}
    for schema_name, rel_name, col_name, contype, *rest in constraint_rows:
        key = (f"{schema_name}.{rel_name}", col_name)
        if contype == "p":
            pk_columns.add(key)
        elif contype == "f":
            fk_columns.add(key)
            ref_target = rest[0] if rest else None
            if ref_target and key not in fk_targets:
                fk_targets[key] = ref_target

    columns_by_table: dict[str, list[ColumnInfo]] = {name: [] for name in kinds}
    for schema_name, rel_name, col_name, data_type, notnull, default, comment in column_rows:
        table_key = f"{schema_name}.{rel_name}"
        if table_key not in columns_by_table:
            continue
        columns_by_table[table_key].append(
            ColumnInfo(
                name=col_name,
                data_type=data_type,
                is_pk=(table_key, col_name) in pk_columns,
                is_fk=(table_key, col_name) in fk_columns,
                is_nullable=not notnull,
                default=default,
                fk_target=fk_targets.get((table_key, col_name)),
                comment=comment,
            )
        )

    view_definitions: dict[str, str] = {}
    for schema_name, rel_name, definition in view_definition_rows or []:
        view_definitions[f"{schema_name}.{rel_name}"] = definition

    return {
        name: TableInfo(
            name=name,
            kind=kind,
            columns=columns_by_table.get(name, []),
            view_definition=view_definitions.get(name),
            comment=comments.get(name),
        )
        for name, kind in kinds.items()
    }


def _build_constraints(constraint_rows: Rows) -> dict[str, ConstraintInfo]:
    """Assemble ``{"schema.table.name": ConstraintInfo}`` from the SAME
    `_CONSTRAINTS_SQL` rows `_build_tables` reads for its PK/FK column flags
    (FQ-025) -- one query, two views of it, never a second round trip.

    `_CONSTRAINTS_SQL` emits one row per (constraint, column); the columns are
    regrouped here, in arrival order, which the query's
    ``ORDER BY … , k.i`` makes `conkey` order -- so a multi-column key reads
    ``(a, b)``, not an arbitrary permutation.

    **Tolerant of the pre-FQ-025 row shape on purpose**: a row without a
    6th value (`conname`) is skipped rather than unpacked into an error, so
    the many canned 4-/5-tuple constraint rows across the suite keep working
    unchanged and simply contribute no named constraints.
    """
    kinds: dict[str, str] = {}
    definitions: dict[str, str] = {}
    identities: dict[str, tuple[str, str, str]] = {}
    columns: dict[str, list[str]] = {}
    for schema_name, rel_name, col_name, contype, *rest in constraint_rows:
        name = rest[1] if len(rest) > 1 else None
        kind = _KIND_BY_CONTYPE.get(contype)
        if not name or kind is None:
            continue
        key = f"{schema_name}.{rel_name}.{name}"
        if key not in identities:
            identities[key] = (schema_name, rel_name, name)
            kinds[key] = kind
            definitions[key] = (rest[2] if len(rest) > 2 else None) or ""
            columns[key] = []
        if col_name and col_name not in columns[key]:
            columns[key].append(col_name)

    return {
        key: ConstraintInfo(
            schema=schema_name,
            table=rel_name,
            name=name,
            kind=kinds[key],
            columns=columns[key],
            definition=definitions[key],
        )
        for key, (schema_name, rel_name, name) in identities.items()
    }


def _build_indexes(index_rows: Rows) -> dict[str, IndexInfo]:
    """Assemble ``{"schema.index_name": IndexInfo}`` from `INDEX_SQL`'s rows
    (FQ-025).

    Constraint-backed indexes are kept and MARKED (`constraint_name`), not
    filtered out -- see `IndexInfo` for why a `Drop index` picker must be the
    thing that excludes them.
    """
    indexes: dict[str, IndexInfo] = {}
    for (
        schema_name,
        table_name,
        index_name,
        method,
        is_unique,
        is_primary,
        definition,
        index_columns,
        constraint_name,
    ) in index_rows:
        info = IndexInfo(
            schema=schema_name,
            table=table_name,
            name=index_name,
            columns=list(index_columns or []),
            is_unique=bool(is_unique),
            is_primary=bool(is_primary),
            method=method or "",
            definition=definition or "",
            constraint_name=constraint_name,
        )
        indexes[info.qualified_name] = info
    return indexes


def _build_types(type_rows: Rows) -> dict[str, TypeInfo]:
    """Assemble ``{"schema.name": TypeInfo}`` from `_TYPES_SQL`'s rows
    (§18.5 D2's "recorded gap" closure)."""
    types: dict[str, TypeInfo] = {}
    for schema_name, type_name, typtype, base_type, not_null, attr_names, attr_types in type_rows:
        kind = "domain" if typtype == "d" else "composite"
        attributes = list(zip(attr_names or [], attr_types or [], strict=True))
        info = TypeInfo(
            schema=schema_name,
            name=type_name,
            kind=kind,
            base_type=base_type if kind == "domain" else None,
            not_null=bool(not_null) if kind == "domain" else False,
            attributes=attributes if kind == "composite" else [],
        )
        types[info.qualified_name] = info
    return types


def fetch_schema(params: ConnectionParams, runner: Runner = run_queries) -> DatabaseSchema:
    """Introspect the database into a `DatabaseSchema` keyed by ``schema.table``."""
    _log.info("db: fetch_schema started %s", debuglog.redacted(params))
    started = time.monotonic()
    relation_rows, column_rows, constraint_rows = runner(params, list(SCHEMA_SQL))
    tables = _build_tables(relation_rows, column_rows, constraint_rows)
    # Named constraints come free from rows already fetched (FQ-025) -- the
    # query list is unchanged, so this stays the same 3-query contract.
    constraints = _build_constraints(constraint_rows)
    elapsed = time.monotonic() - started
    _log.info(
        "db: fetch_schema finished %.3fs tables=%d", elapsed, len(tables)
    )
    return DatabaseSchema(tables=tables, constraints=constraints)


def fetch_routines_and_triggers(
    params: ConnectionParams, runner: Runner = run_queries
) -> DatabaseSchema:
    """Introspect functions/procedures + triggers **and** tables/columns into
    one `DatabaseSchema` (§18.1, widened by §18.6).

    Runs `ROUTINE_TRIGGER_SQL` (routines/triggers) and `SCHEMA_SQL` (the same
    three queries `fetch_schema` runs) in the same round trip, so the DDL
    Explorer's one connect-time fetch now populates `.routines`, `.triggers`
    **and** `.tables`. This supersedes the earlier "`.tables` is always empty"
    behavior (§28 Supersession Ledger, 2026-08-04): `db/schema_index.py`
    (§18.6) is built from the `.tables` this now returns, for schema-aware
    Ctrl+Space completion in the DDL object editor.

    Widened again by FQ-025 with `INDEX_SQL`, in the same round trip: the
    DDL Explorer's `Drop index` picker is the only consumer of index data, so
    the query rides along here rather than in `fetch_schema` or
    `snapshot_for_baseline`. `.constraints` (named constraints) is filled too,
    from the `SCHEMA_SQL` rows already being fetched.

    `fetch_schema` itself is UNCHANGED -- its own 3-query contract and tests
    are untouched, and DB Check keeps calling it directly. This is one
    widened fetch serving two consumers, never a second parallel fetch.
    """
    _log.info("db: fetch_routines_and_triggers started %s", debuglog.redacted(params))
    started = time.monotonic()
    (
        routine_rows,
        trigger_rows,
        relation_rows,
        column_rows,
        constraint_rows,
        index_rows,
    ) = runner(params, list(ROUTINE_TRIGGER_SQL) + list(SCHEMA_SQL) + list(INDEX_SQL))

    routines, triggers = _build_routines_and_triggers(routine_rows, trigger_rows)
    tables = _build_tables(relation_rows, column_rows, constraint_rows)
    constraints = _build_constraints(constraint_rows)
    indexes = _build_indexes(index_rows)

    elapsed = time.monotonic() - started
    _log.info(
        "db: fetch_routines_and_triggers finished %.3fs "
        "routines=%d triggers=%d tables=%d constraints=%d indexes=%d",
        elapsed,
        len(routines),
        len(triggers),
        len(tables),
        len(constraints),
        len(indexes),
    )
    return DatabaseSchema(
        routines=routines,
        triggers=triggers,
        tables=tables,
        constraints=constraints,
        indexes=indexes,
    )


def _build_routines_and_triggers(
    routine_rows: Rows, trigger_rows: Rows
) -> tuple[dict[str, RoutineInfo], dict[str, TriggerInfo]]:
    """Assemble the `.routines`/`.triggers` dicts from `ROUTINE_TRIGGER_SQL`'s
    two row-lists. Factored out of `fetch_routines_and_triggers` so
    `snapshot_for_baseline` (§18.5 D2) can build the identical shape from one
    shared implementation rather than a second parallel loop."""
    routines: dict[str, RoutineInfo] = {}
    for (
        schema_name,
        name,
        prokind,
        return_type,
        language,
        source,
        arg_types,
        all_arg_types,
        arg_names,
        arg_modes,
    ) in routine_rows:
        routine = RoutineInfo(
            schema=schema_name,
            name=name,
            arg_types=list(arg_types or []),
            return_type=return_type,
            language=language,
            source=source,
            kind="function" if prokind == "f" else "procedure",
            args=_input_args(all_arg_types, arg_names, arg_modes),
        )
        # Keyed by the full signature, not `schema.name`: `pg_proc` holds one
        # row per overload, so `public.fmt(integer)` and `public.fmt(text)`
        # arrive as two rows that would collapse onto one key (BUG-018). Built
        # first, then keyed off `routine.signature`, so the string has exactly
        # one implementation.
        routines[routine.signature] = routine

    triggers: dict[str, TriggerInfo] = {}
    for schema_name, table_name, name, tgtype, function_name, definition in trigger_rows:
        timing, events = _decode_trigger_type(tgtype)
        triggers[f"{schema_name}.{table_name}.{name}"] = TriggerInfo(
            schema=schema_name,
            table=table_name,
            name=name,
            timing=timing,
            events=events,
            function_name=function_name,
            definition=definition,
        )
    return routines, triggers


@dataclass(frozen=True)
class BaselineSnapshot:
    """A `DatabaseSchema` widened with the two "recorded gap" queries
    (§18.5 D2) that `build_baseline_sql` (`db/sandbox.py`) needs but neither
    `fetch_schema` nor `fetch_routines_and_triggers` fetches: view/matview
    definitions (already carried on `TableInfo.view_definition`) and
    domain/composite types (`DatabaseSchema.types`).

    A thin wrapper, not a re-invented model -- `DatabaseSchema` stays the one
    shared shape; this only exists because `snapshot_for_baseline` is a
    distinct entry point (one specific extra round trip) worth naming
    separately from the general-purpose `fetch_*` functions above.
    """

    schema: DatabaseSchema = field(default_factory=DatabaseSchema)


def snapshot_for_baseline(
    target_params: ConnectionParams, runner: Runner = run_queries
) -> BaselineSnapshot:
    """Introspect the **target** database into a `BaselineSnapshot` -- the
    input `db/sandbox.py::build_baseline_sql` consumes to provision a fresh
    sandbox (§18.5 D2).

    Reuses `SCHEMA_SQL` + `ROUTINE_TRIGGER_SQL` + `BASELINE_EXTRA_SQL` (the
    view-definition and domain/composite-type queries) in **one** round trip,
    mirroring `fetch_routines_and_triggers`'s "one widened fetch" precedent
    rather than issuing several separate connections.

    Qt-free, and -- like every other function here -- never imports psycopg
    directly: only the injectable `runner` (defaulting to `run_queries`,
    the sole psycopg touchpoint) ever opens a connection.
    """
    _log.info("db: snapshot_for_baseline started %s", debuglog.redacted(target_params))
    started = time.monotonic()
    (
        routine_rows,
        trigger_rows,
        relation_rows,
        column_rows,
        constraint_rows,
        viewdef_rows,
        type_rows,
    ) = runner(target_params, list(ROUTINE_TRIGGER_SQL) + list(SCHEMA_SQL) + list(BASELINE_EXTRA_SQL))

    routines, triggers = _build_routines_and_triggers(routine_rows, trigger_rows)
    tables = _build_tables(relation_rows, column_rows, constraint_rows, viewdef_rows)
    constraints = _build_constraints(constraint_rows)
    types = _build_types(type_rows)

    elapsed = time.monotonic() - started
    _log.info(
        "db: snapshot_for_baseline finished %.3fs tables=%d routines=%d triggers=%d types=%d",
        elapsed,
        len(tables),
        len(routines),
        len(triggers),
        len(types),
    )
    return BaselineSnapshot(
        schema=DatabaseSchema(
            tables=tables,
            routines=routines,
            triggers=triggers,
            types=types,
            constraints=constraints,
        )
    )


def test_connection(params: ConnectionParams, runner: Runner = run_queries) -> tuple[bool, str]:
    """Run ``SELECT 1``; return ``(True, "Connected.")`` or ``(False, <error>)``.

    Never raises — driver/connection failures are captured as the message.
    """
    _log.info("db: test_connection started %s", debuglog.redacted(params))
    started = time.monotonic()
    try:
        runner(params, ["SELECT 1"])
    except Exception as exc:  # noqa: BLE001 — surface any failure as a message
        _log.info(
            "db: test_connection finished %.3fs error=%s",
            time.monotonic() - started,
            exc,
        )
        return False, str(exc)
    _log.info("db: test_connection finished %.3fs ok", time.monotonic() - started)
    return True, "Connected."
