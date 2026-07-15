# pgtp_editor/ui/project_tree.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from pgtp_editor.ui._stub_action import add_stub_action

NODE_KIND_ROLE = Qt.ItemDataRole.UserRole
TABLE_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
MODEL_NODE_ROLE = Qt.ItemDataRole.UserRole + 2


class ProjectTreePanel(QTreeWidget):
    def __init__(
        self,
        parent=None,
        on_stub_action=None,
        on_compare_page=None,
        on_compare_detail=None,
        on_selection_changed=None,
        on_activate_node=None,
        on_jump_to_xml=None,
        on_select_xml_block=None,
        on_see_table_in_caption=None,
        on_see_table_details_in_caption=None,
        on_jump_to_column_visibility=None,
        on_see_column_in_caption=None,
    ):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self._on_stub_action = on_stub_action or (lambda label: None)
        self._on_compare_page = on_compare_page or (lambda page_node: None)
        self._on_compare_detail = on_compare_detail or (lambda detail_node, source_path: None)
        self._on_selection_changed = on_selection_changed or (lambda node, kind: None)
        # Phase D callbacks (default no-ops so the panel is usable standalone).
        self._on_activate_node = on_activate_node or (lambda node, kind: None)
        self._on_jump_to_xml = on_jump_to_xml or (lambda node: None)
        self._on_select_xml_block = on_select_xml_block or (lambda node: None)
        self._on_see_table_in_caption = on_see_table_in_caption or (lambda node: None)
        self._on_see_table_details_in_caption = (
            on_see_table_details_in_caption or (lambda node: None)
        )
        self._on_jump_to_column_visibility = (
            on_jump_to_column_visibility or (lambda node: None)
        )
        self._on_see_column_in_caption = on_see_column_in_caption or (lambda node: None)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.currentItemChanged.connect(self._on_current_item_changed)
        # Single-click / current-item change still only updates Properties; the
        # editor jumps ONLY on an explicit double-click (Phase D.1).
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _on_current_item_changed(self, current, _previous):
        if current is None:
            self._on_selection_changed(None, None)
            return
        node = current.data(0, MODEL_NODE_ROLE)
        kind = current.data(0, NODE_KIND_ROLE)
        self._on_selection_changed(node, kind)

    def _on_item_double_clicked(self, item, _column=0):
        if item is None:
            return
        node = item.data(0, MODEL_NODE_ROLE)
        kind = item.data(0, NODE_KIND_ROLE)
        self._on_activate_node(node, kind)

    def populate_from_project(self, project):
        """Populate the tree from a parsed ProjectModel (see
        pgtp_editor.model.parser.load_project). Replaces any existing
        content — call this after a successful File -> Open.
        """
        self.clear()
        self._item_by_node_id = {}
        for page in project.pages:
            page_name = page.attrib.get("caption") or page.file_name or page.identity
            page_table = page.table_name or ""
            page_item = QTreeWidgetItem([f"(P) {page_name} [{page_table}]"])
            page_item.setData(0, NODE_KIND_ROLE, "page")
            page_item.setData(0, TABLE_NAME_ROLE, page_table)
            page_item.setData(0, MODEL_NODE_ROLE, page)
            self._item_by_node_id[id(page)] = page_item
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
            detail_item.setData(0, MODEL_NODE_ROLE, detail)
            self._item_by_node_id[id(detail)] = detail_item
            parent_item.addChild(detail_item)
            self._populate_details_and_events(detail_item, detail)
        for column in node.columns:
            column_item = QTreeWidgetItem([f"(C) {column.field_name}"])
            column_item.setData(0, NODE_KIND_ROLE, "column")
            column_item.setData(0, MODEL_NODE_ROLE, column)
            self._item_by_node_id[id(column)] = column_item
            parent_item.addChild(column_item)
        for event in node.events:
            event_item = QTreeWidgetItem([f"(E) {event.side}.{event.tag_name}"])
            event_item.setData(0, NODE_KIND_ROLE, "event")
            event_item.setData(0, MODEL_NODE_ROLE, event)
            self._item_by_node_id[id(event)] = event_item
            parent_item.addChild(event_item)

    def select_node(self, node) -> bool:
        """Select the tree item backing `node`, if present. Returns True if a
        matching item was found and selected, False otherwise (e.g. node is
        None, or is from a stale/other model). Setting the current item fires
        the existing currentItemChanged -> _on_selection_changed -> Properties
        flow; no extra Properties wiring is needed here."""
        if node is None:
            return False
        item = getattr(self, "_item_by_node_id", {}).get(id(node))
        if item is None:
            return False
        self.setCurrentItem(item)
        return True

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
        node = item.data(0, MODEL_NODE_ROLE)
        menu = QMenu(self)
        jump_action = menu.addAction("Jump to page xml")
        jump_action.triggered.connect(
            lambda checked=False, n=node: self._on_jump_to_xml(n)
        )
        select_action = menu.addAction("Select page xml")
        select_action.triggered.connect(
            lambda checked=False, n=node: self._on_select_xml_block(n)
        )
        self._add_stub_action(menu, "Add Event Handler")
        see_action = menu.addAction("See database table in caption mode")
        see_action.triggered.connect(
            lambda checked=False, n=node: self._on_see_table_in_caption(n)
        )
        return menu

    def build_detail_menu(self, item):
        node = item.data(0, MODEL_NODE_ROLE)
        menu = QMenu(self)
        jump_action = menu.addAction("Jump to detail xml")
        jump_action.triggered.connect(
            lambda checked=False, n=node: self._on_jump_to_xml(n)
        )
        select_action = menu.addAction("Select detail xml")
        select_action.triggered.connect(
            lambda checked=False, n=node: self._on_select_xml_block(n)
        )
        see_action = menu.addAction("See database table in caption mode")
        see_action.triggered.connect(
            lambda checked=False, n=node: self._on_see_table_details_in_caption(n)
        )
        return menu

    def build_column_menu(self, item):
        node = item.data(0, MODEL_NODE_ROLE)
        menu = QMenu(self)
        visibility_action = menu.addAction("Jump to column visibility in xml")
        visibility_action.triggered.connect(
            lambda checked=False, n=node: self._on_jump_to_column_visibility(n)
        )
        presentation_action = menu.addAction("Jump to column presentation in xml")
        presentation_action.triggered.connect(
            lambda checked=False, n=node: self._on_jump_to_xml(n)
        )
        see_action = menu.addAction("See column in caption mode")
        see_action.triggered.connect(
            lambda checked=False, n=node: self._on_see_column_in_caption(n)
        )
        return menu

    def build_multi_select_menu(self):
        menu = QMenu(self)
        self._add_stub_action(menu, "Compare Selected")
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
