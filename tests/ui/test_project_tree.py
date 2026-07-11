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
    assert tree.topLevelItem(0).text(0) == "Equipment"
    assert tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole) == "page"
    assert tree.topLevelItem(1).text(0) == "Work Orders"


def test_equipment_page_has_two_details(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    assert equipment.childCount() == 2
    assert equipment.child(0).text(0) == "Sub-item"
    assert equipment.child(0).data(0, Qt.ItemDataRole.UserRole) == "detail"
    assert equipment.child(1).text(0) == "Attachments"


def test_detail_has_field_children(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    sub_item = equipment.child(0)
    assert sub_item.childCount() == 2
    assert sub_item.child(0).text(0) == "tag"
    assert sub_item.child(0).data(0, Qt.ItemDataRole.UserRole) == "field"


def test_reused_table_detected_across_pages(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    attachments_detail = equipment.child(1)
    assert tree.has_duplicate_table(attachments_detail) is True

    sub_item_detail = equipment.child(0)
    assert tree.has_duplicate_table(sub_item_detail) is False


def test_page_context_menu(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    menu = tree.build_page_menu(tree.topLevelItem(0))
    assert action_labels(menu) == [
        "Edit Properties", "―",
        "Copy", "Paste", "Duplicate", "Copy to Other Open Project...", "―",
        "Add Detail...", "―",
        "Create Client (Readonly) Page", "Compare This Page With...", "―",
        "Find Field Usages...", "Rename / Unify Captions...", "―",
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


def test_field_context_menu(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    field_item = tree.topLevelItem(0).child(0).child(0)
    menu = tree.build_field_menu(field_item)
    assert action_labels(menu) == [
        "Edit Caption / Hint / Short Caption", "―",
        "Find All Usages of This Field", "Unify Captions Across Pages...", "―",
        "Delete Field",
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
