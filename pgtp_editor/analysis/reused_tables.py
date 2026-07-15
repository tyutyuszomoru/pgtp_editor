"""Find tables/views referenced from more than one place in a project.

Pure, Qt-free analysis over a parsed :class:`ProjectModel`. Every reference to
a table -- a page's ``tableName``, a (possibly nested) detail's ``tableName``,
and every column lookup's target ``tableName`` -- contributes one breadcrumb
describing where it is used. Breadcrumbs are grouped by table name; the result
is sorted by table name (case-sensitive, as stored) and, within a table, kept
in document order.

The column-lookup table attribute is ``Lookup@tableName`` (confirmed against
the real sample ``sample/dev_Ferrara.pgtp``: e.g.
``<Lookup tableName="pr.x_wbs" .../>``), surfaced as
``ColumnNode.lookup.attrib["tableName"]``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_SEP = " ▸ "  # " ▸ "


@dataclass
class TableUsage:
    name: str
    breadcrumbs: list[str] = field(default_factory=list)


def _page_label(page) -> str:
    return page.attrib.get("caption") or page.file_name or page.table_name or ""


def _detail_label(detail) -> str:
    return detail.attrib.get("caption") or detail.table_name or ""


def collect_table_usages(project) -> list[TableUsage]:
    """Return the reused-table usages of ``project`` grouped by table name.

    References with a ``None``/empty table name are skipped. The list is sorted
    by table name; each table's breadcrumbs stay in document (traversal) order.
    """
    grouped: dict[str, list[str]] = {}

    def record(name: str | None, breadcrumb: str) -> None:
        if not name:
            return
        grouped.setdefault(name, []).append(breadcrumb)

    def visit_columns(columns, prefix: str) -> None:
        for column in columns:
            lookup = column.lookup
            if lookup is None:
                continue
            table = lookup.attrib.get("tableName")
            field_name = column.field_name or ""
            record(table, f"{prefix}{_SEP}Column '{field_name}' (lookup)")

    def visit_detail(detail, prefix: str) -> None:
        crumb = f"{prefix}{_SEP}Detail '{_detail_label(detail)}'"
        record(detail.table_name, crumb)
        visit_columns(detail.columns, crumb)
        for child in detail.details:
            visit_detail(child, crumb)

    for page in project.pages:
        crumb = f"Page '{_page_label(page)}'"
        record(page.table_name, crumb)
        visit_columns(page.columns, crumb)
        for detail in page.details:
            visit_detail(detail, crumb)

    return [TableUsage(name=name, breadcrumbs=grouped[name]) for name in sorted(grouped)]
