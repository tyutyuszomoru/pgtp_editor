"""A small synthetic ProjectModel used by UI tests, mirroring the shape of
the old PLACEHOLDER_PROJECT dict (two pages; "Attachments" and
"Characteristics" intentionally share a tableName to exercise the
reused-table detection in ProjectTreePanel.has_duplicate_table).
"""
from pgtp_editor.model.nodes import ColumnNode, DetailNode, EventNode, PageNode, ProjectModel


def _column(field_name):
    return ColumnNode(identity=field_name, attrib={"fieldName": field_name}, sourceline=1)


def _event(tag_name, side):
    return EventNode(identity=tag_name, tag_name=tag_name, side=side, text="", sourceline=1)


def build_sample_project() -> ProjectModel:
    sub_item = DetailNode(
        identity="equipment/pr.attachment",
        attrib={"tableName": "pr.attachment", "caption": "Sub-item"},
        sourceline=1,
        columns=[_column("tag"), _column("description")],
        events=[_event("OnPreparePage", "S")],
    )
    attachments = DetailNode(
        identity="equipment/pr.r_characteristic",
        attrib={"tableName": "pr.r_characteristic", "caption": "Attachments"},
        sourceline=1,
        columns=[_column("cvalue")],
        events=[],
    )
    equipment = PageNode(
        identity="Equipment",
        attrib={"tableName": "pr.equipment", "caption": "Equipment"},
        sourceline=1,
        details=[sub_item, attachments],
        columns=[],
        events=[_event("OnPreparePage", "S"), _event("OnRowProcess", "C")],
    )

    characteristics = DetailNode(
        identity="work_orders/pr.r_characteristic",
        attrib={"tableName": "pr.r_characteristic", "caption": "Characteristics"},
        sourceline=1,
        columns=[_column("cvalue")],
        events=[],
    )
    work_orders = PageNode(
        identity="Work Orders",
        attrib={"tableName": "pr.x_workorder", "caption": "Work Orders"},
        sourceline=1,
        details=[characteristics],
        columns=[],
        events=[_event("OnRowProcess", "C")],
    )

    return ProjectModel(pages=[equipment, work_orders])
