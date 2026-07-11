# pgtp_editor/ui/project_tree.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from pgtp_editor.ui._stub_action import add_stub_action

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
    def __init__(self, parent=None, on_stub_action=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self._on_stub_action = on_stub_action or (lambda label: None)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
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

    def _add_stub_action(self, menu, label):
        return add_stub_action(menu, label, self._on_stub_action)

    def build_page_menu(self, item):
        menu = QMenu(self)
        self._add_stub_action(menu, "Edit Properties")
        menu.addSeparator()
        self._add_stub_action(menu, "Copy")
        self._add_stub_action(menu, "Paste")
        self._add_stub_action(menu, "Duplicate")
        self._add_stub_action(menu, "Copy to Other Open Project...")
        menu.addSeparator()
        self._add_stub_action(menu, "Add Detail...")
        menu.addSeparator()
        self._add_stub_action(menu, "Create Client (Readonly) Page")
        self._add_stub_action(menu, "Compare This Page With...")
        menu.addSeparator()
        self._add_stub_action(menu, "Find Field Usages...")
        self._add_stub_action(menu, "Rename / Unify Captions...")
        menu.addSeparator()
        self._add_stub_action(menu, "Delete Page")
        return menu

    def build_detail_menu(self, item):
        menu = QMenu(self)
        self._add_stub_action(menu, "Edit Properties")
        menu.addSeparator()
        self._add_stub_action(menu, "Cut")
        self._add_stub_action(menu, "Copy")
        self._add_stub_action(menu, "Paste")
        self._add_stub_action(menu, "Duplicate")
        self._add_stub_action(menu, "Move to Parent Page...")
        self._add_stub_action(menu, "Copy to Other Open Project...")
        menu.addSeparator()
        self._add_stub_action(menu, "Add Nested Detail...")
        menu.addSeparator()
        self._add_stub_action(menu, "Create Client (Readonly) Page")
        self._add_stub_action(menu, "Compare This Detail With...")
        if self.has_duplicate_table(item):
            self._add_stub_action(menu, "Compare with Other Instance...")
        menu.addSeparator()
        self._add_stub_action(menu, "Delete Detail (+ nested)")
        return menu

    def build_field_menu(self, item):
        menu = QMenu(self)
        self._add_stub_action(menu, "Edit Caption / Hint / Short Caption")
        menu.addSeparator()
        self._add_stub_action(menu, "Find All Usages of This Field")
        self._add_stub_action(menu, "Unify Captions Across Pages...")
        menu.addSeparator()
        self._add_stub_action(menu, "Delete Field")
        return menu

    def build_multi_select_menu(self):
        menu = QMenu(self)
        self._add_stub_action(menu, "Compare Selected")
        self._add_stub_action(menu, "Create Client Pages for Selected")
        self._add_stub_action(menu, "Copy Selected to...")
        return menu

    def menu_for_position(self, pos):
        if len(self.selectedItems()) > 1:
            return self.build_multi_select_menu()
        item = self.itemAt(pos)
        if item is None:
            return None
        kind = item.data(0, NODE_KIND_ROLE)
        if kind == "page":
            return self.build_page_menu(item)
        if kind == "detail":
            return self.build_detail_menu(item)
        if kind == "field":
            return self.build_field_menu(item)
        return None

    def _show_context_menu(self, pos):
        menu = self.menu_for_position(pos)
        if menu is not None:
            menu.exec(self.viewport().mapToGlobal(pos))
