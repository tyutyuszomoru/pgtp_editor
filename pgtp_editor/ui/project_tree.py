# pgtp_editor/ui/project_tree.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from pgtp_editor.ui._stub_action import add_stub_action

NODE_KIND_ROLE = Qt.ItemDataRole.UserRole
TABLE_NAME_ROLE = Qt.ItemDataRole.UserRole + 1


class ProjectTreePanel(QTreeWidget):
    def __init__(self, parent=None, on_stub_action=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self._on_stub_action = on_stub_action or (lambda label: None)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def populate_from_project(self, project):
        """Populate the tree from a parsed ProjectModel (see
        pgtp_editor.model.parser.load_project). Replaces any existing
        content — call this after a successful File -> Open.
        """
        self.clear()
        for page in project.pages:
            page_name = page.attrib.get("caption") or page.file_name or page.identity
            page_table = page.table_name or ""
            page_item = QTreeWidgetItem([f"(P) {page_name} [{page_table}]"])
            page_item.setData(0, NODE_KIND_ROLE, "page")
            page_item.setData(0, TABLE_NAME_ROLE, page_table)
            self.addTopLevelItem(page_item)
            self._populate_details_and_events(page_item, page)

    def _populate_details_and_events(self, parent_item, node):
        # Ordering matches the tree's established display shape: nested
        # Details first, then this node's own Columns, then its Events.
        for detail in node.details:
            detail_name = detail.attrib.get("caption") or detail.table_name or detail.identity
            detail_table = detail.table_name or ""
            detail_item = QTreeWidgetItem([f"(D) {detail_name} [{detail_table}]"])
            detail_item.setData(0, NODE_KIND_ROLE, "detail")
            detail_item.setData(0, TABLE_NAME_ROLE, detail_table)
            parent_item.addChild(detail_item)
            self._populate_details_and_events(detail_item, detail)
        for column in node.columns:
            column_item = QTreeWidgetItem([f"(C) {column.field_name}"])
            column_item.setData(0, NODE_KIND_ROLE, "column")
            parent_item.addChild(column_item)
        for event in node.events:
            event_item = QTreeWidgetItem([f"(E) {event.side}.{event.tag_name}"])
            event_item.setData(0, NODE_KIND_ROLE, "event")
            parent_item.addChild(event_item)

    def iter_detail_items(self):
        for i in range(self.topLevelItemCount()):
            page_item = self.topLevelItem(i)
            for j in range(page_item.childCount()):
                child = page_item.child(j)
                if child.data(0, NODE_KIND_ROLE) == "detail":
                    yield child

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
        self._add_stub_action(menu, "Find Column Usages...")
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

    def build_column_menu(self, item):
        menu = QMenu(self)
        self._add_stub_action(menu, "Edit Caption / Hint / Short Caption")
        menu.addSeparator()
        self._add_stub_action(menu, "Find All Usages of This Column")
        self._add_stub_action(menu, "Unify Captions Across Pages...")
        menu.addSeparator()
        self._add_stub_action(menu, "Delete Column")
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
        if kind == "column":
            return self.build_column_menu(item)
        return None

    def _show_context_menu(self, pos):
        menu = self.menu_for_position(pos)
        if menu is not None:
            menu.exec(self.viewport().mapToGlobal(pos))
