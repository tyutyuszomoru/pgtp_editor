from pgtp_editor.ui.project_tree import ProjectTreePanel
from PySide6.QtCore import Qt


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
