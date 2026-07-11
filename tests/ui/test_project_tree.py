from pgtp_editor.ui.project_tree import ProjectTreePanel
from PySide6.QtCore import Qt

from tests.ui._menu_helpers import action_labels, find_action


def test_tree_has_no_columns_header(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    assert tree.isHeaderHidden() is True


def test_two_placeholder_pages(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    assert tree.topLevelItemCount() == 2
    assert tree.topLevelItem(0).text(0) == "(P) Equipment [pr.equipment]"
    assert tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole) == "page"
    assert tree.topLevelItem(1).text(0) == "(P) Work Orders [pr.x_workorder]"


def test_equipment_page_has_details_then_events(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    assert equipment.childCount() == 4
    assert equipment.child(0).text(0) == "(D) Sub-item [pr.attachment]"
    assert equipment.child(0).data(0, Qt.ItemDataRole.UserRole) == "detail"
    assert equipment.child(1).text(0) == "(D) Attachments [pr.r_characteristic]"
    assert equipment.child(1).data(0, Qt.ItemDataRole.UserRole) == "detail"
    assert equipment.child(2).text(0) == "(E) S.OnPreparePage"
    assert equipment.child(2).data(0, Qt.ItemDataRole.UserRole) == "event"
    assert equipment.child(3).text(0) == "(E) C.OnRowProcess"
    assert equipment.child(3).data(0, Qt.ItemDataRole.UserRole) == "event"


def test_work_orders_page_has_detail_then_event(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    work_orders = tree.topLevelItem(1)
    assert work_orders.childCount() == 2
    assert work_orders.child(0).text(0) == "(D) Characteristics [pr.r_characteristic]"
    assert work_orders.child(0).data(0, Qt.ItemDataRole.UserRole) == "detail"
    assert work_orders.child(1).text(0) == "(E) C.OnRowProcess"
    assert work_orders.child(1).data(0, Qt.ItemDataRole.UserRole) == "event"


def test_sub_item_detail_has_columns_then_event(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    sub_item = equipment.child(0)
    assert sub_item.childCount() == 3
    assert sub_item.child(0).text(0) == "(C) tag"
    assert sub_item.child(0).data(0, Qt.ItemDataRole.UserRole) == "column"
    assert sub_item.child(1).text(0) == "(C) description"
    assert sub_item.child(1).data(0, Qt.ItemDataRole.UserRole) == "column"
    assert sub_item.child(2).text(0) == "(E) S.OnPreparePage"
    assert sub_item.child(2).data(0, Qt.ItemDataRole.UserRole) == "event"


def test_attachments_detail_has_one_column(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    attachments = equipment.child(1)
    assert attachments.childCount() == 1
    assert attachments.child(0).text(0) == "(C) cvalue"
    assert attachments.child(0).data(0, Qt.ItemDataRole.UserRole) == "column"


def test_characteristics_detail_has_one_column(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    work_orders = tree.topLevelItem(1)
    characteristics = work_orders.child(0)
    assert characteristics.childCount() == 1
    assert characteristics.child(0).text(0) == "(C) cvalue"
    assert characteristics.child(0).data(0, Qt.ItemDataRole.UserRole) == "column"


def test_reused_table_detected_across_pages(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    attachments_detail = equipment.child(1)
    assert tree.has_duplicate_table(attachments_detail) is True

    sub_item_detail = equipment.child(0)
    assert tree.has_duplicate_table(sub_item_detail) is False


def test_has_duplicate_table_not_confused_by_event_siblings(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    work_orders = tree.topLevelItem(1)
    characteristics_detail = work_orders.child(0)
    assert work_orders.child(1).data(0, Qt.ItemDataRole.UserRole) == "event"
    assert tree.has_duplicate_table(characteristics_detail) is True


def test_page_context_menu(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    menu = tree.build_page_menu(tree.topLevelItem(0))
    assert action_labels(menu) == [
        "Edit Properties", "―",
        "Copy", "Paste", "Duplicate", "Copy to Other Open Project...", "―",
        "Add Detail...", "―",
        "Create Client (Readonly) Page", "Compare This Page With...", "―",
        "Find Column Usages...", "Rename / Unify Captions...", "―",
        "Delete Page",
    ]


def test_detail_context_menu_shows_compare_instance_when_table_reused(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    attachments_detail = tree.topLevelItem(0).child(1)
    menu = tree.build_detail_menu(attachments_detail)
    assert action_labels(menu) == [
        "Edit Properties", "―",
        "Cut", "Copy", "Paste", "Duplicate", "Move to Parent Page...", "Copy to Other Open Project...", "―",
        "Add Nested Detail...", "―",
        "Create Client (Readonly) Page", "Compare This Detail With...", "Compare with Other Instance...", "―",
        "Delete Detail (+ nested)",
    ]


def test_detail_context_menu_hides_compare_instance_when_table_unique(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    sub_item_detail = tree.topLevelItem(0).child(0)
    menu = tree.build_detail_menu(sub_item_detail)
    assert "Compare with Other Instance..." not in action_labels(menu)


def test_column_context_menu(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    column_item = tree.topLevelItem(0).child(0).child(0)
    menu = tree.build_column_menu(column_item)
    assert action_labels(menu) == [
        "Edit Caption / Hint / Short Caption", "―",
        "Find All Usages of This Column", "Unify Captions Across Pages...", "―",
        "Delete Column",
    ]


def test_multi_select_menu(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    menu = tree.build_multi_select_menu()
    assert action_labels(menu) == [
        "Compare Selected", "Create Client Pages for Selected", "Copy Selected to...",
    ]


def test_stub_action_callback_invoked(qtbot):
    calls = []
    tree = ProjectTreePanel(on_stub_action=calls.append)
    qtbot.addWidget(tree)
    menu = tree.build_page_menu(tree.topLevelItem(0))
    find_action(menu, "Delete Page").trigger()
    assert calls == ["Delete Page"]


def test_menu_for_position_dispatches_by_kind(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    page_item = tree.topLevelItem(0)
    rect = tree.visualItemRect(page_item)
    menu = tree.menu_for_position(rect.center())
    assert action_labels(menu)[0] == "Edit Properties"


def test_menu_for_position_dispatches_detail(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    tree.expandAll()
    detail_item = tree.topLevelItem(0).child(0)
    rect = tree.visualItemRect(detail_item)
    menu = tree.menu_for_position(rect.center())
    assert action_labels(menu)[0] == "Edit Properties"


def test_menu_for_position_dispatches_column(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    tree.expandAll()
    column_item = tree.topLevelItem(0).child(0).child(0)
    rect = tree.visualItemRect(column_item)
    menu = tree.menu_for_position(rect.center())
    assert action_labels(menu)[0] == "Edit Caption / Hint / Short Caption"


def test_menu_for_position_returns_none_for_event(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    tree.expandAll()
    event_item = tree.topLevelItem(0).child(2)
    assert event_item.data(0, Qt.ItemDataRole.UserRole) == "event"
    rect = tree.visualItemRect(event_item)
    menu = tree.menu_for_position(rect.center())
    assert menu is None
