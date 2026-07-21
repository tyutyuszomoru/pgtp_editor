# tests/analysis/test_reused_tables.py
"""Unit tests for the Qt-free reused-tables analyzer."""
from pgtp_editor.analysis.reused_tables import TableUsage, collect_table_usages
from pgtp_editor.model.nodes import ChildElement, ColumnNode, DetailNode, PageNode, ProjectModel


def _column(field_name, lookup_table=None):
    lookup = None
    if lookup_table is not None:
        lookup = ChildElement(attrib={"tableName": lookup_table})
    return ColumnNode(
        identity=field_name,
        attrib={"fieldName": field_name},
        sourceline=1,
        lookup=lookup,
    )


def test_page_table_used_by_two_pages_is_grouped():
    page_a = PageNode(identity="A", attrib={"tableName": "shared", "caption": "Alpha"})
    page_b = PageNode(identity="B", attrib={"tableName": "shared", "caption": "Beta"})
    usages = collect_table_usages(ProjectModel(pages=[page_a, page_b]))

    assert [u.name for u in usages] == ["shared"]
    assert usages[0].breadcrumbs == ["Page 'Alpha'", "Page 'Beta'"]


def test_page_label_falls_back_to_file_name_then_table_name():
    page = PageNode(identity="P", attrib={"tableName": "t", "fileName": "orders.php"})
    usages = collect_table_usages(ProjectModel(pages=[page]))
    assert usages[0].breadcrumbs == ["Page 'orders.php'"]


def test_nested_detail_table_breadcrumb_path():
    inner = DetailNode(identity="d2", attrib={"tableName": "line_items", "caption": "Lines"})
    outer = DetailNode(
        identity="d1",
        attrib={"tableName": "order_items", "caption": "Items"},
        details=[inner],
    )
    page = PageNode(
        identity="P",
        attrib={"tableName": "orders", "caption": "Orders"},
        details=[outer],
    )
    usages = {u.name: u.breadcrumbs for u in collect_table_usages(ProjectModel(pages=[page]))}

    assert usages["order_items"] == ["Page 'Orders' ▸ Detail 'Items'"]
    assert usages["line_items"] == [
        "Page 'Orders' ▸ Detail 'Items' ▸ Detail 'Lines'"
    ]


def test_column_lookup_table_recorded_with_lookup_breadcrumb():
    page = PageNode(
        identity="P",
        attrib={"tableName": "orders", "caption": "Orders"},
        columns=[_column("customer_id", lookup_table="customers")],
    )
    usages = {u.name: u.breadcrumbs for u in collect_table_usages(ProjectModel(pages=[page]))}

    assert usages["customers"] == ["Page 'Orders' ▸ Column 'customer_id' (lookup)"]


def test_detail_column_lookup_includes_full_path():
    detail = DetailNode(
        identity="d1",
        attrib={"tableName": "order_items", "caption": "Items"},
        columns=[_column("product_id", lookup_table="products")],
    )
    page = PageNode(
        identity="P",
        attrib={"tableName": "orders", "caption": "Orders"},
        details=[detail],
    )
    usages = {u.name: u.breadcrumbs for u in collect_table_usages(ProjectModel(pages=[page]))}
    assert usages["products"] == [
        "Page 'Orders' ▸ Detail 'Items' ▸ Column 'product_id' (lookup)"
    ]


def test_result_sorted_by_name_case_sensitive():
    page = PageNode(
        identity="P",
        attrib={"tableName": "Zebra", "caption": "P"},
        columns=[_column("a", lookup_table="apple"), _column("b", lookup_table="Banana")],
    )
    usages = collect_table_usages(ProjectModel(pages=[page]))
    # Capitalized names sort before lowercase in case-sensitive ordering.
    assert [u.name for u in usages] == ["Banana", "Zebra", "apple"]


def test_empty_and_none_table_names_skipped():
    page = PageNode(
        identity="P",
        attrib={"tableName": "", "caption": "P"},
        columns=[_column("a"), _column("b", lookup_table="")],
    )
    assert collect_table_usages(ProjectModel(pages=[page])) == []


def test_returns_table_usage_instances():
    page = PageNode(identity="P", attrib={"tableName": "t", "caption": "P"})
    usages = collect_table_usages(ProjectModel(pages=[page]))
    assert isinstance(usages[0], TableUsage)


from lxml import etree

from pgtp_editor.analysis.reused_tables import TableReference


def _lookup_child(table, sourceline=None, with_insert=False):
    xml = f'<Lookup tableName="{table}">'
    xml += "<OnTheFlyInsertPage/>" if with_insert else ""
    xml += "</Lookup>"
    element = etree.fromstring(xml)
    return ChildElement(attrib=dict(element.attrib), sourceline=sourceline, element=element)


def test_page_reference_carries_node_kind_and_line():
    page = PageNode(identity="P", attrib={"tableName": "t", "caption": "P"}, sourceline=7)
    usage = collect_table_usages(ProjectModel(pages=[page]))[0]
    ref = usage.references[0]
    assert isinstance(ref, TableReference)
    assert ref.node is page
    assert ref.kind == "page"
    assert ref.line == 7
    assert ref.ref_type == "table"


def test_detail_reference_carries_detail_node_and_kind():
    detail = DetailNode(identity="d", attrib={"tableName": "lines", "caption": "L"}, sourceline=12)
    page = PageNode(identity="P", attrib={"tableName": "orders", "caption": "O"}, details=[detail])
    usages = {u.name: u for u in collect_table_usages(ProjectModel(pages=[page]))}
    ref = usages["lines"].references[0]
    assert ref.node is detail
    assert ref.kind == "detail"
    assert ref.line == 12


def test_lookup_reference_uses_lookup_line_and_column_node():
    col = ColumnNode(
        identity="c", attrib={"fieldName": "objecttype"}, sourceline=3,
        lookup=_lookup_child("kb.x_objecttype", sourceline=5),
    )
    page = PageNode(identity="P", attrib={"tableName": "orders", "caption": "O"}, columns=[col])
    usage = collect_table_usages(ProjectModel(pages=[page]))[0]
    ref = usage.references[0]
    assert ref.node is col
    assert ref.kind == "column"
    assert ref.line == 5              # the <Lookup> line, not the column's line 3
    assert ref.ref_type == "lookup"
    assert ref.breadcrumb == "Page 'O' ▸ Column 'objecttype' (lookup)"


def test_lookup_with_insert_reference_type_and_breadcrumb():
    col = ColumnNode(
        identity="c", attrib={"fieldName": "objecttype"}, sourceline=3,
        lookup=_lookup_child("kb.x_objecttype", sourceline=5, with_insert=True),
    )
    page = PageNode(identity="P", attrib={"tableName": "orders", "caption": "O"}, columns=[col])
    ref = collect_table_usages(ProjectModel(pages=[page]))[0].references[0]
    assert ref.ref_type == "lookup with insert"
    assert ref.breadcrumb == "Page 'O' ▸ Column 'objecttype' (lookup with insert)"


def test_lookup_line_falls_back_to_column_line_when_lookup_line_missing():
    col = ColumnNode(
        identity="c", attrib={"fieldName": "f"}, sourceline=9,
        lookup=_lookup_child("a_lookup", sourceline=None),
    )
    page = PageNode(identity="P", attrib={"tableName": "orders", "caption": "O"}, columns=[col])
    ref = collect_table_usages(ProjectModel(pages=[page]))[0].references[0]
    assert ref.line == 9


def test_breadcrumbs_property_still_returns_strings():
    page = PageNode(identity="P", attrib={"tableName": "t", "caption": "P"}, sourceline=1)
    usage = collect_table_usages(ProjectModel(pages=[page]))[0]
    assert usage.breadcrumbs == ["Page 'P'"]
