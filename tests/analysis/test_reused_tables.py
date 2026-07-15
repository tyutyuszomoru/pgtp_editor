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
