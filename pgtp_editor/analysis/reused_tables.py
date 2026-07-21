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


@dataclass(frozen=True)
class TableReference:
    """One place a table/view is referenced, with enough context to navigate.

    breadcrumb: human-readable path, e.g. "Page 'X' ▸ Column 'y' (lookup)".
    node:       the owning model node (PageNode | DetailNode | ColumnNode).
    kind:       "page" | "detail" | "column" (the Properties-panel node kind).
    line:       1-based source line to jump to, or None.
    ref_type:   "table" | "lookup" | "lookup with insert".
    """
    breadcrumb: str
    node: object
    kind: str
    line: "int | None"
    ref_type: str


@dataclass
class TableUsage:
    name: str
    references: list[TableReference] = field(default_factory=list)

    @property
    def breadcrumbs(self) -> list[str]:
        """The reference breadcrumbs as plain strings (convenience/back-compat)."""
        return [ref.breadcrumb for ref in self.references]


def _page_label(page) -> str:
    return page.attrib.get("caption") or page.file_name or page.table_name or ""


def _detail_label(detail) -> str:
    return detail.attrib.get("caption") or detail.table_name or ""


def _lookup_ref_type(lookup) -> str:
    """"lookup with insert" when the <Lookup> has a child <OnTheFlyInsertPage>,
    else "lookup". Falls back to "lookup" when the lxml element was not retained
    (e.g. a hand-built ChildElement in a unit test)."""
    element = getattr(lookup, "element", None)
    if element is not None and element.find("OnTheFlyInsertPage") is not None:
        return "lookup with insert"
    return "lookup"


def collect_table_usages(project) -> list[TableUsage]:
    """Return the table usages of ``project`` grouped by table name.

    References with a ``None``/empty table name are skipped. The list is sorted
    by table name; each table's references stay in document (traversal) order.
    """
    grouped: dict[str, list[TableReference]] = {}

    def record(name: str | None, ref: TableReference) -> None:
        if not name:
            return
        grouped.setdefault(name, []).append(ref)

    def visit_columns(columns, prefix: str) -> None:
        for column in columns:
            lookup = column.lookup
            if lookup is None:
                continue
            table = lookup.attrib.get("tableName")
            field_name = column.field_name or ""
            ref_type = _lookup_ref_type(lookup)
            line = lookup.sourceline if lookup.sourceline is not None else column.sourceline
            crumb = f"{prefix}{_SEP}Column '{field_name}' ({ref_type})"
            record(table, TableReference(crumb, column, "column", line, ref_type))

    def visit_detail(detail, prefix: str) -> None:
        crumb = f"{prefix}{_SEP}Detail '{_detail_label(detail)}'"
        record(
            detail.table_name,
            TableReference(crumb, detail, "detail", detail.sourceline, "table"),
        )
        visit_columns(detail.columns, crumb)
        for child in detail.details:
            visit_detail(child, crumb)

    for page in project.pages:
        crumb = f"Page '{_page_label(page)}'"
        record(
            page.table_name,
            TableReference(crumb, page, "page", page.sourceline, "table"),
        )
        visit_columns(page.columns, crumb)
        for detail in page.details:
            visit_detail(detail, crumb)

    return [TableUsage(name=name, references=grouped[name]) for name in sorted(grouped)]
