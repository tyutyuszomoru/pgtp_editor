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


@dataclass(frozen=True)
class TableInfo:
    name: str  # "schema.table"
    kind: str  # "table" | "view" | "matview"
    columns: list[ColumnInfo] = field(default_factory=list)


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
class DatabaseSchema:
    tables: dict[str, TableInfo] = field(default_factory=dict)
    routines: dict[str, RoutineInfo] = field(default_factory=dict)
    triggers: dict[str, TriggerInfo] = field(default_factory=dict)

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


# --- pg_catalog queries -----------------------------------------------------
# Non-system schemas only (exclude pg_catalog / information_schema / pg_toast).
# Order of the three queries is load-bearing: fetch_schema unpacks them
# positionally as [relations, columns, constraints].

_RELATIONS_SQL = """
SELECT n.nspname, c.relname, c.relkind
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
       pg_catalog.pg_get_expr(d.adbin, d.adrelid)
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

_CONSTRAINTS_SQL = """
SELECT n.nspname, c.relname, lc.attname, con.contype,
       CASE WHEN con.contype = 'f' THEN rn.nspname || '.' || rc.relname || '.' || rc_att.attname END
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN generate_subscripts(con.conkey, 1) AS k(i) ON true
JOIN pg_catalog.pg_attribute lc
     ON lc.attrelid = con.conrelid AND lc.attnum = con.conkey[k.i]
LEFT JOIN pg_catalog.pg_class rc ON rc.oid = con.confrelid
LEFT JOIN pg_catalog.pg_namespace rn ON rn.oid = rc.relnamespace
LEFT JOIN pg_catalog.pg_attribute rc_att
     ON rc_att.attrelid = con.confrelid AND rc_att.attnum = con.confkey[k.i]
WHERE con.contype IN ('p', 'f')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
"""

SCHEMA_SQL: list[str] = [_RELATIONS_SQL, _COLUMNS_SQL, _CONSTRAINTS_SQL]

_KIND_BY_RELKIND = {"r": "table", "p": "table", "v": "view", "m": "matview"}

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
    relation_rows: Rows, column_rows: Rows, constraint_rows: Rows
) -> dict[str, TableInfo]:
    """Assemble ``{"schema.table": TableInfo}`` from `SCHEMA_SQL`'s three
    row-lists. Shared by `fetch_schema` and `fetch_routines_and_triggers`
    (§18.6) so the one table/column-assembly implementation backs both."""
    kinds: dict[str, str] = {}
    for schema_name, rel_name, relkind in relation_rows:
        kinds[f"{schema_name}.{rel_name}"] = _KIND_BY_RELKIND.get(relkind, "table")

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
    for schema_name, rel_name, col_name, data_type, notnull, default in column_rows:
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
            )
        )

    return {
        name: TableInfo(name=name, kind=kind, columns=columns_by_table.get(name, []))
        for name, kind in kinds.items()
    }


def fetch_schema(params: ConnectionParams, runner: Runner = run_queries) -> DatabaseSchema:
    """Introspect the database into a `DatabaseSchema` keyed by ``schema.table``."""
    _log.info("db: fetch_schema started %s", debuglog.redacted(params))
    started = time.monotonic()
    relation_rows, column_rows, constraint_rows = runner(params, list(SCHEMA_SQL))
    tables = _build_tables(relation_rows, column_rows, constraint_rows)
    elapsed = time.monotonic() - started
    _log.info(
        "db: fetch_schema finished %.3fs tables=%d", elapsed, len(tables)
    )
    return DatabaseSchema(tables=tables)


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

    `fetch_schema` itself is UNCHANGED -- its own 3-query contract and tests
    are untouched, and DB Check keeps calling it directly. This is one
    widened fetch serving two consumers, never a second parallel fetch.
    """
    _log.info("db: fetch_routines_and_triggers started %s", debuglog.redacted(params))
    started = time.monotonic()
    routine_rows, trigger_rows, relation_rows, column_rows, constraint_rows = runner(
        params, list(ROUTINE_TRIGGER_SQL) + list(SCHEMA_SQL)
    )

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

    tables = _build_tables(relation_rows, column_rows, constraint_rows)

    elapsed = time.monotonic() - started
    _log.info(
        "db: fetch_routines_and_triggers finished %.3fs routines=%d triggers=%d tables=%d",
        elapsed,
        len(routines),
        len(triggers),
        len(tables),
    )
    return DatabaseSchema(routines=routines, triggers=triggers, tables=tables)


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
