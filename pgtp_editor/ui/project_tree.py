# pgtp_editor/ui/project_tree.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

NODE_KIND_ROLE = Qt.ItemDataRole.UserRole
TABLE_NAME_ROLE = Qt.ItemDataRole.UserRole + 1

# Placeholder data only — replaced wholesale once the real lxml-backed
# model exists. "Attachments" and "Characteristics" intentionally share
# a tableName to exercise the reused-table detection below.
PLACEHOLDER_PROJECT = {
    "Equipment": {
        "table": "pr.equipment",
        "details": {
            "Sub-item": {"table": "pr.attachment", "fields": ["tag", "description"]},
            "Attachments": {"table": "pr.r_characteristic", "fields": ["cvalue"]},
        },
    },
    "Work Orders": {
        "table": "pr.x_workorder",
        "details": {
            "Characteristics": {"table": "pr.r_characteristic", "fields": ["cvalue"]},
        },
    },
}


class ProjectTreePanel(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self._populate_placeholder()

    def _populate_placeholder(self):
        for page_name, page_data in PLACEHOLDER_PROJECT.items():
            page_item = QTreeWidgetItem([page_name])
            page_item.setData(0, NODE_KIND_ROLE, "page")
            self.addTopLevelItem(page_item)
            for detail_name, detail_data in page_data["details"].items():
                detail_item = QTreeWidgetItem([detail_name])
                detail_item.setData(0, NODE_KIND_ROLE, "detail")
                detail_item.setData(0, TABLE_NAME_ROLE, detail_data["table"])
                page_item.addChild(detail_item)
                for field_name in detail_data["fields"]:
                    field_item = QTreeWidgetItem([field_name])
                    field_item.setData(0, NODE_KIND_ROLE, "field")
                    detail_item.addChild(field_item)

    def iter_detail_items(self):
        for i in range(self.topLevelItemCount()):
            page_item = self.topLevelItem(i)
            for j in range(page_item.childCount()):
                yield page_item.child(j)

    def has_duplicate_table(self, detail_item):
        table_name = detail_item.data(0, TABLE_NAME_ROLE)
        count = sum(
            1 for item in self.iter_detail_items()
            if item.data(0, TABLE_NAME_ROLE) == table_name
        )
        return count > 1
