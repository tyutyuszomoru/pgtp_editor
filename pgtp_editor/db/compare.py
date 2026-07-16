# pgtp_editor/db/compare.py
"""Compare a parsed `.pgtp` project against a live `DatabaseSchema` (pure).

Two directions:

* `check_xml_against_db` (#5): every table/column the XML references, marked
  found/missing against the DB (found columns carry the DB `ColumnInfo`).
* `check_db_against_xml` (#6): every DB table/column, marked present/absent in
  the XML (each carries its DB `ColumnInfo`).

Found/missing is name-based only; the datatype, PK, FK, nullability and default
in `ColumnInfo` are informational (see the design's non-goals). Qt-free.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pgtp_editor.analysis.reused_tables import collect_table_usages

from .introspect import ColumnInfo, DatabaseSchema


@dataclass(frozen=True)
class ColumnCheck:
    name: str
    ok: bool
    info: ColumnInfo | None = None


@dataclass(frozen=True)
class TableCheck:
    name: str
    ok: bool
    kind: str | None
    invocations: int
    columns: list[ColumnCheck] = field(default_factory=list)


def xml_table_columns(project) -> dict[str, set[str]]:
    """Map each bound ``tableName`` to the set of column ``fieldName``s under it.

    Pages and (recursively) details bound to the same table union their
    columns. Empty table/field names are skipped. A table bound with no columns
    still appears (empty set).
    """
    result: dict[str, set[str]] = {}

    def add(name: str | None, columns) -> None:
        if not name:
            return
        bucket = result.setdefault(name, set())
        for column in columns:
            field_name = column.field_name
            if field_name:
                bucket.add(field_name)

    def visit_detail(detail) -> None:
        add(detail.table_name, detail.columns)
        for child in detail.details:
            visit_detail(child)

    for page in project.pages:
        add(page.table_name, page.columns)
        for detail in page.details:
            visit_detail(detail)

    return result


def xml_table_invocations(project) -> dict[str, int]:
    """Map each table to its XML reference count (reused-tables usage count)."""
    return {usage.name: len(usage.breadcrumbs) for usage in collect_table_usages(project)}


def check_xml_against_db(project, schema: DatabaseSchema) -> list[TableCheck]:
    """For each XML-referenced table/column, mark found/missing against the DB."""
    columns_by_table = xml_table_columns(project)
    invocations = xml_table_invocations(project)

    checks: list[TableCheck] = []
    for table_name in sorted(columns_by_table):
        table_info = schema.table(table_name)
        column_checks = [
            ColumnCheck(
                name=col,
                ok=schema.column(table_name, col) is not None,
                info=schema.column(table_name, col),
            )
            for col in sorted(columns_by_table[table_name])
        ]
        checks.append(
            TableCheck(
                name=table_name,
                ok=schema.has_table(table_name),
                kind=table_info.kind if table_info is not None else None,
                invocations=invocations.get(table_name, 0),
                columns=column_checks,
            )
        )
    return checks


def check_db_against_xml(project, schema: DatabaseSchema) -> list[TableCheck]:
    """For each DB table/column, mark present/absent in the XML."""
    columns_by_table = xml_table_columns(project)
    invocations = xml_table_invocations(project)

    checks: list[TableCheck] = []
    for table_name in sorted(schema.tables):
        table_info = schema.tables[table_name]
        xml_columns = columns_by_table.get(table_name, set())
        column_checks = [
            ColumnCheck(
                name=column.name,
                ok=column.name in xml_columns,
                info=column,
            )
            for column in sorted(table_info.columns, key=lambda c: c.name)
        ]
        checks.append(
            TableCheck(
                name=table_name,
                ok=table_name in columns_by_table,
                kind=table_info.kind,
                invocations=invocations.get(table_name, 0),
                columns=column_checks,
            )
        )
    return checks
