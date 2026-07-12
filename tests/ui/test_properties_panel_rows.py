from pgtp_editor.model.nodes import ColumnNode, DetailNode, PageNode
from pgtp_editor.ui.properties_panel import (
    RowSpec,
    _rows_for_attrib_node,
    _rows_for_detail,
)


def test_rows_for_page_one_row_per_attrib_key():
    page = PageNode(
        identity="equipment",
        attrib={"fileName": "development_equipment", "tableName": "pr.equipment"},
        sourceline=5,
    )
    rows = _rows_for_attrib_node(page)
    assert rows == [
        RowSpec(property_label="fileName", value="development_equipment", target_line=5, attr_name="fileName"),
        RowSpec(property_label="tableName", value="pr.equipment", target_line=5, attr_name="tableName"),
    ]


def test_rows_for_column_one_row_per_attrib_key():
    column = ColumnNode(identity="tag", attrib={"fieldName": "tag", "caption": "Tag"}, sourceline=42)
    rows = _rows_for_attrib_node(column)
    assert rows == [
        RowSpec(property_label="fieldName", value="tag", target_line=42, attr_name="fieldName"),
        RowSpec(property_label="caption", value="Tag", target_line=42, attr_name="caption"),
    ]


def test_rows_for_detail_caption_uses_outer_sourceline_others_use_inner():
    detail = DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment", "viewAbilityMode": "1"},
        sourceline=10,
        inner_sourceline=25,
    )
    rows = _rows_for_detail(detail)
    assert rows == [
        RowSpec(property_label="caption", value="Sub-item", target_line=10, attr_name="caption"),
        RowSpec(property_label="tableName", value="pr.attachment", target_line=25, attr_name="tableName"),
        RowSpec(property_label="viewAbilityMode", value="1", target_line=25, attr_name="viewAbilityMode"),
    ]


def test_rows_for_detail_missing_inner_sourceline_falls_back_to_none():
    detail = DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment"},
        sourceline=10,
        inner_sourceline=None,
    )
    rows = _rows_for_detail(detail)
    caption_row = next(r for r in rows if r.property_label == "caption")
    table_name_row = next(r for r in rows if r.property_label == "tableName")
    assert caption_row.target_line == 10
    assert table_name_row.target_line is None
