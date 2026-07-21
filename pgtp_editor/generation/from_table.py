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

# pgtp_editor/generation/from_table.py
"""Synthesize a <Page>/<Detail>/<Lookup> from a DB table or view.

Pure: consumes `db.introspect` dataclasses + `type_map`, produces lxml elements
and a deterministic tab-indented serialization. No Qt, no I/O — the UI layer
routes the result (insert into the buffer, or copy to clipboard).

See docs/superpowers/specs/2026-07-19-create-from-db-table-design.md.
"""
from __future__ import annotations

from lxml import etree

from pgtp_editor.db.introspect import DatabaseSchema, TableInfo
from pgtp_editor.generation import type_map


class GenerationError(Exception):
    """Raised when a table/view cannot be turned into an element (missing, empty)."""


# -- name helpers -----------------------------------------------------------

def _short_name(table_key: str) -> str:
    """Last path segment of ``schema.table`` -> ``table``."""
    return table_key.split(".")[-1]


def _file_name(table_key: str) -> str:
    """PHP Generator's derived fileName is the BARE table name (last segment),
    not schema-qualified: ``public.newtable_1`` -> ``newtable_1`` (confirmed by
    the golden_newtable_1 capture — the generated file is ``newtable_1.php`` even
    though the page class is ``public_newtable_1Page``)."""
    return table_key.split(".")[-1]


def _require_table(schema: DatabaseSchema, table_key: str) -> TableInfo:
    table = schema.table(table_key)
    if table is None:
        raise GenerationError(f"No table/view '{table_key}' in the schema.")
    if not table.columns:
        raise GenerationError(f"Table/view '{table_key}' has no columns.")
    return table


# -- column presentations & representation lists ----------------------------

def _append_column_presentation(parent: etree._Element, col) -> None:
    spec = type_map.column_spec(col.name, col.data_type)
    cp = etree.SubElement(parent, "ColumnPresentation")
    # Attribute order matches real phpgen output: fieldName, caption,
    # [showColumnFilter], [canSetNull], selectedFilterOperators.
    cp.set("fieldName", col.name)
    cp.set("caption", spec.caption)
    if spec.emit_show_column_filter_false:
        cp.set("showColumnFilter", "false")
    if col.is_nullable:
        cp.set("canSetNull", "true")
    cp.set("selectedFilterOperators", spec.selected_filter_operators)

    view = etree.SubElement(cp, "ViewProperties")
    view.set("type", spec.view_type)
    for key, value in spec.view_extra.items():
        view.set(key, value)
    if spec.format_type is not None:
        fmt = etree.SubElement(view, "Format")
        fmt.set("type", spec.format_type)
        for key, value in spec.format_extra.items():
            fmt.set(key, value)

    edit = etree.SubElement(cp, "EditProperties")
    edit.set("type", spec.edit_type)
    for key, value in spec.edit_extra.items():
        edit.set(key, value)


def _build_columns_block(parent: etree._Element, table: TableInfo) -> None:
    columns = etree.SubElement(parent, "Columns")
    pk_names = {c.name for c in table.columns if c.is_pk}
    for rep in type_map.REPRESENTATION_NAMES:
        rep_el = etree.SubElement(columns, rep)
        hide_pk = rep in type_map.PK_HIDDEN_IN
        for col in table.columns:
            entry = etree.SubElement(rep_el, "Column")
            entry.set("fieldName", col.name)
            if hide_pk and col.name in pk_names:
                entry.set("visible", "false")


def _build_page_element(table: TableInfo, tag: str, *, file_name: str) -> etree._Element:
    """Common <Page> body used by both top-level pages and detail pages."""
    page = etree.Element(tag)
    page.set("type", "table")
    page.set("tableName", table.name)
    # numberByDataSource sits immediately after tableName in real phpgen output.
    page.set("numberByDataSource", "0")
    page.set("fileName", file_name)
    short = _short_name(table.name)
    caption = type_map.humanize(short)
    page.set("caption", caption)
    page.set("shortCaption", caption)
    for key, value in type_map.PAGE_DEFAULTS:
        page.set(key, value)

    etree.SubElement(page, "BeforeGridText")
    etree.SubElement(page, "DetailedDescription")
    cps = etree.SubElement(page, "ColumnPresentations")
    for col in table.columns:
        _append_column_presentation(cps, col)
    _build_columns_block(page, table)
    etree.SubElement(page, "Details")
    return page


# -- public builders --------------------------------------------------------

def build_page(schema: DatabaseSchema, table_key: str) -> etree._Element:
    """A full top-level <Page> for the given table/view."""
    table = _require_table(schema, table_key)
    return _build_page_element(table, "Page", file_name=_file_name(table_key))


def build_detail(schema: DatabaseSchema, table_key: str) -> etree._Element:
    """A <Detail> wrapping a nested <Page> (fileName="") plus a
    <MasterForeignKeyColumnMap>. The master/foreign columns are inferred from a
    single unambiguous FK on the child table, else left as empty placeholders."""
    table = _require_table(schema, table_key)
    caption = type_map.humanize(_short_name(table.name))

    detail = etree.Element("Detail")
    detail.set("caption", caption)
    detail.append(_build_page_element(table, "Page", file_name=""))

    master_col, foreign_col = _infer_master_foreign(table)
    fk_map = etree.SubElement(detail, "MasterForeignKeyColumnMap")
    field_map = etree.SubElement(fk_map, "FieldMap")
    # NOTE: "foreginColumnName" reproduces the vendor's misspelling (required).
    field_map.set("masterColumnName", master_col)
    field_map.set("foreginColumnName", foreign_col)
    return detail


def build_lookup(schema: DatabaseSchema, table_key: str) -> etree._Element:
    """A <Lookup> whose source is the given table; linkFieldName = the single PK,
    displayFieldName = the first text-like non-PK column (best effort)."""
    table = _require_table(schema, table_key)
    pk_names = [c.name for c in table.columns if c.is_pk]
    link_field = pk_names[0] if len(pk_names) == 1 else ""
    display_field = _guess_display_field(table, pk_names)

    lookup = etree.Element("Lookup")
    lookup.set("tableName", table.name)
    lookup.set("linkFieldName", link_field)
    lookup.set("displayFieldName", display_field)
    lookup.set("lookupFilter", "")
    lookup.set("useLookupOrdering", "true")
    lookup.set("lookupOrdering", "0")
    return lookup


# -- inference helpers ------------------------------------------------------

def _infer_master_foreign(table: TableInfo) -> tuple[str, str]:
    """Return ``(masterColumnName, foreginColumnName)`` for the detail link.
    Only inferable when the child table has exactly one FK column whose target
    column is known; otherwise both are empty placeholders."""
    fks = [c for c in table.columns if c.is_fk]
    if len(fks) != 1:
        return "", ""
    fk = fks[0]
    target = getattr(fk, "fk_target", None)
    master_col = target.split(".")[-1] if target else ""
    return master_col, fk.name


def _guess_display_field(table: TableInfo, pk_names: list[str]) -> str:
    """First non-PK, non-FK text-ish column; else first non-PK column; else the
    PK; else empty."""
    non_pk = [c for c in table.columns if c.name not in pk_names]
    for col in non_pk:
        base = type_map._base_type(col.data_type)
        if not col.is_fk and (
            "char" in base or base in ("text", "citext", "name")
        ):
            return col.name
    if non_pk:
        return non_pk[0].name
    if pk_names:
        return pk_names[0]
    return ""


# -- serialization ----------------------------------------------------------

def serialize(element: etree._Element, indent: int = 0) -> str:
    """Deterministic, tab-indented serialization of a synthesized fragment.

    ``indent`` is the number of leading tabs applied to the root element (so the
    caller can splice the fragment at the right depth, e.g. 3 tabs to sit inside
    <Presentation><Pages>). Empty elements render as ``<Tag/>``.
    """
    lines: list[str] = []
    _serialize_into(element, indent, lines)
    return "\n".join(lines)


def _serialize_into(element: etree._Element, depth: int, lines: list[str]) -> None:
    pad = "\t" * depth
    tag = element.tag
    attrs = "".join(f' {k}="{_escape_attr(v)}"' for k, v in element.attrib.items())
    children = list(element)
    text = (element.text or "").strip()

    if not children and not text:
        lines.append(f"{pad}<{tag}{attrs}/>")
        return
    if not children and text:
        lines.append(f"{pad}<{tag}{attrs}>{_escape_text(element.text)}</{tag}>")
        return

    lines.append(f"{pad}<{tag}{attrs}>")
    for child in children:
        _serialize_into(child, depth + 1, lines)
    lines.append(f"{pad}</{tag}>")


def _escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _escape_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
