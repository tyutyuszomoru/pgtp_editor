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


@dataclass(frozen=True)
class TableInfo:
    name: str  # "schema.table"
    kind: str  # "table" | "view" | "matview"
    columns: list[ColumnInfo] = field(default_factory=list)


@dataclass(frozen=True)
class DatabaseSchema:
    tables: dict[str, TableInfo] = field(default_factory=dict)

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
SELECT n.nspname, c.relname, a.attname, con.contype
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute a
     ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
WHERE con.contype IN ('p', 'f')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
"""

SCHEMA_SQL: list[str] = [_RELATIONS_SQL, _COLUMNS_SQL, _CONSTRAINTS_SQL]

_KIND_BY_RELKIND = {"r": "table", "p": "table", "v": "view", "m": "matview"}


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


def fetch_schema(params: ConnectionParams, runner: Runner = run_queries) -> DatabaseSchema:
    """Introspect the database into a `DatabaseSchema` keyed by ``schema.table``."""
    _log.info("db: fetch_schema started %s", debuglog.redacted(params))
    started = time.monotonic()
    relation_rows, column_rows, constraint_rows = runner(params, list(SCHEMA_SQL))

    kinds: dict[str, str] = {}
    for schema_name, rel_name, relkind in relation_rows:
        kinds[f"{schema_name}.{rel_name}"] = _KIND_BY_RELKIND.get(relkind, "table")

    # Constraint membership: (table_key, column_name) -> contype set.
    pk_columns: set[tuple[str, str]] = set()
    fk_columns: set[tuple[str, str]] = set()
    for schema_name, rel_name, col_name, contype in constraint_rows:
        key = (f"{schema_name}.{rel_name}", col_name)
        if contype == "p":
            pk_columns.add(key)
        elif contype == "f":
            fk_columns.add(key)

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
            )
        )

    tables = {
        name: TableInfo(name=name, kind=kind, columns=columns_by_table.get(name, []))
        for name, kind in kinds.items()
    }
    elapsed = time.monotonic() - started
    _log.info(
        "db: fetch_schema finished %.3fs tables=%d", elapsed, len(tables)
    )
    return DatabaseSchema(tables=tables)


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
