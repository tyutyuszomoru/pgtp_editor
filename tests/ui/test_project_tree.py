from pgtp_editor.ui.project_tree import ProjectTreePanel
from PySide6.QtCore import Qt

from tests.ui._menu_helpers import action_labels, find_action
from tests.ui._sample_project import build_sample_project


def make_populated_tree(qtbot, on_stub_action=None):
    tree = ProjectTreePanel(on_stub_action=on_stub_action)
    qtbot.addWidget(tree)
    tree.populate_from_project(build_sample_project())
    return tree


def test_tree_has_no_columns_header(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    assert tree.isHeaderHidden() is True


def test_empty_tree_before_populate(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    assert tree.topLevelItemCount() == 0


def test_two_pages(qtbot):
    tree = make_populated_tree(qtbot)
    assert tree.topLevelItemCount() == 2
    assert tree.topLevelItem(0).text(0) == "(P) Equipment [pr.equipment]"
    assert tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole) == "page"
    assert tree.topLevelItem(1).text(0) == "(P) Work Orders [pr.x_workorder]"


def test_equipment_page_has_details_then_events(qtbot):
    tree = make_populated_tree(qtbot)
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
    tree = make_populated_tree(qtbot)
    work_orders = tree.topLevelItem(1)
    assert work_orders.childCount() == 2
    assert work_orders.child(0).text(0) == "(D) Characteristics [pr.r_characteristic]"
    assert work_orders.child(0).data(0, Qt.ItemDataRole.UserRole) == "detail"
    assert work_orders.child(1).text(0) == "(E) C.OnRowProcess"
    assert work_orders.child(1).data(0, Qt.ItemDataRole.UserRole) == "event"


def test_sub_item_detail_has_columns_then_event(qtbot):
    tree = make_populated_tree(qtbot)
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
    tree = make_populated_tree(qtbot)
    equipment = tree.topLevelItem(0)
    attachments = equipment.child(1)
    assert attachments.childCount() == 1
    assert attachments.child(0).text(0) == "(C) cvalue"
    assert attachments.child(0).data(0, Qt.ItemDataRole.UserRole) == "column"


def test_characteristics_detail_has_one_column(qtbot):
    tree = make_populated_tree(qtbot)
    work_orders = tree.topLevelItem(1)
    characteristics = work_orders.child(0)
    assert characteristics.childCount() == 1
    assert characteristics.child(0).text(0) == "(C) cvalue"
    assert characteristics.child(0).data(0, Qt.ItemDataRole.UserRole) == "column"


def test_reused_table_detected_across_pages(qtbot):
    tree = make_populated_tree(qtbot)
    equipment = tree.topLevelItem(0)
    attachments_detail = equipment.child(1)
    assert tree.has_duplicate_table(attachments_detail) is True

    sub_item_detail = equipment.child(0)
    assert tree.has_duplicate_table(sub_item_detail) is False


def test_has_duplicate_table_not_confused_by_event_siblings(qtbot):
    tree = make_populated_tree(qtbot)
    work_orders = tree.topLevelItem(1)
    characteristics_detail = work_orders.child(0)
    assert work_orders.child(1).data(0, Qt.ItemDataRole.UserRole) == "event"
    assert tree.has_duplicate_table(characteristics_detail) is True


def test_populate_from_project_clears_previous_content(qtbot):
    tree = make_populated_tree(qtbot)
    assert tree.topLevelItemCount() == 2
    tree.populate_from_project(build_sample_project())
    assert tree.topLevelItemCount() == 2


def test_page_context_menu(qtbot):
    tree = make_populated_tree(qtbot, on_stub_action=lambda label: None)
    menu = tree.build_page_menu(tree.topLevelItem(0))
    assert action_labels(menu) == [
        "Edit Properties", "―",
        "Copy", "Paste", "Duplicate", "Copy to Other Open Project...", "―",
        "Add Detail...", "―",
        "Compare This Page With...", "―",
        "Find Column Usages...", "Rename / Unify Captions...", "―",
        "Delete Page",
    ]


def test_detail_context_menu_shows_compare_instance_when_table_reused(qtbot):
    tree = make_populated_tree(qtbot, on_stub_action=lambda label: None)
    attachments_detail = tree.topLevelItem(0).child(1)
    menu = tree.build_detail_menu(attachments_detail)
    assert action_labels(menu) == [
        "Edit Properties", "―",
        "Cut", "Copy", "Paste", "Duplicate", "Copy to Other Open Project...", "―",
        "Add Nested Detail...", "―",
        "Compare This Detail With...", "Compare with Other Instance...", "―",
        "Delete Detail (+ nested)",
    ]


def test_detail_context_menu_hides_compare_instance_when_table_unique(qtbot):
    tree = make_populated_tree(qtbot, on_stub_action=lambda label: None)
    sub_item_detail = tree.topLevelItem(0).child(0)
    menu = tree.build_detail_menu(sub_item_detail)
    assert "Compare with Other Instance..." not in action_labels(menu)


def test_column_context_menu(qtbot):
    tree = make_populated_tree(qtbot, on_stub_action=lambda label: None)
    column_item = tree.topLevelItem(0).child(0).child(0)
    menu = tree.build_column_menu(column_item)
    assert action_labels(menu) == [
        "Edit Caption / Hint / Short Caption", "―",
        "Find All Usages of This Column", "Unify Captions Across Pages...", "―",
        "Delete Column",
    ]


def test_multi_select_menu(qtbot):
    tree = make_populated_tree(qtbot, on_stub_action=lambda label: None)
    menu = tree.build_multi_select_menu()
    assert action_labels(menu) == [
        "Compare Selected", "Copy Selected to...",
    ]


def test_stub_action_callback_invoked(qtbot):
    calls = []
    tree = make_populated_tree(qtbot, on_stub_action=calls.append)
    menu = tree.build_page_menu(tree.topLevelItem(0))
    find_action(menu, "Delete Page").trigger()
    assert calls == ["Delete Page"]


def test_menu_for_position_dispatches_by_kind(qtbot):
    tree = make_populated_tree(qtbot, on_stub_action=lambda label: None)
    page_item = tree.topLevelItem(0)
    rect = tree.visualItemRect(page_item)
    menu = tree.menu_for_position(rect.center())
    assert action_labels(menu)[0] == "Edit Properties"


def test_menu_for_position_dispatches_detail(qtbot):
    tree = make_populated_tree(qtbot, on_stub_action=lambda label: None)
    tree.expandAll()
    detail_item = tree.topLevelItem(0).child(0)
    rect = tree.visualItemRect(detail_item)
    menu = tree.menu_for_position(rect.center())
    assert action_labels(menu)[0] == "Edit Properties"


def test_menu_for_position_dispatches_column(qtbot):
    tree = make_populated_tree(qtbot, on_stub_action=lambda label: None)
    tree.expandAll()
    column_item = tree.topLevelItem(0).child(0).child(0)
    rect = tree.visualItemRect(column_item)
    menu = tree.menu_for_position(rect.center())
    assert action_labels(menu)[0] == "Edit Caption / Hint / Short Caption"


def test_menu_for_position_returns_none_for_event(qtbot):
    tree = make_populated_tree(qtbot, on_stub_action=lambda label: None)
    tree.expandAll()
    event_item = tree.topLevelItem(0).child(2)
    assert event_item.data(0, Qt.ItemDataRole.UserRole) == "event"
    rect = tree.visualItemRect(event_item)
    menu = tree.menu_for_position(rect.center())
    assert menu is None


from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE


def test_page_item_carries_model_node(qtbot):
    tree = make_populated_tree(qtbot)
    page_item = tree.topLevelItem(0)
    node = page_item.data(0, MODEL_NODE_ROLE)
    assert node.file_name == "development_equipment" or node.attrib.get("caption") == "Equipment"
    assert node.table_name == "pr.equipment"


def test_detail_item_carries_model_node(qtbot):
    tree = make_populated_tree(qtbot)
    detail_item = tree.topLevelItem(0).child(0)
    node = detail_item.data(0, MODEL_NODE_ROLE)
    assert node.table_name == "pr.attachment"
    assert node.attrib.get("caption") == "Sub-item"


def test_column_item_carries_model_node(qtbot):
    tree = make_populated_tree(qtbot)
    column_item = tree.topLevelItem(0).child(0).child(0)
    node = column_item.data(0, MODEL_NODE_ROLE)
    assert node.field_name == "tag"


def test_event_item_carries_model_node(qtbot):
    tree = make_populated_tree(qtbot)
    event_item = tree.topLevelItem(0).child(2)
    node = event_item.data(0, MODEL_NODE_ROLE)
    assert node.tag_name == "OnPreparePage"
    assert node.side == "S"


def test_selection_changed_callback_invoked_with_node_and_kind(qtbot):
    calls = []
    tree = ProjectTreePanel(on_selection_changed=lambda node, kind: calls.append((node, kind)))
    qtbot.addWidget(tree)
    tree.populate_from_project(build_sample_project())

    page_item = tree.topLevelItem(0)
    tree.setCurrentItem(page_item)

    assert len(calls) == 1
    node, kind = calls[0]
    assert kind == "page"
    assert node.table_name == "pr.equipment"


def test_selection_changed_callback_invoked_with_none_when_cleared(qtbot):
    calls = []
    tree = ProjectTreePanel(on_selection_changed=lambda node, kind: calls.append((node, kind)))
    qtbot.addWidget(tree)
    tree.populate_from_project(build_sample_project())

    tree.setCurrentItem(tree.topLevelItem(0))
    tree.setCurrentItem(None)

    assert calls[-1] == (None, None)


def test_selection_changed_callback_defaults_to_noop(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(build_sample_project())
    # Must not raise even though no callback was supplied.
    tree.setCurrentItem(tree.topLevelItem(0))


def test_select_node_selects_the_backing_item_and_returns_true(qtbot):
    project = build_sample_project()
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(project)

    page_node = project.pages[0]
    assert tree.select_node(page_node) is True
    current = tree.currentItem()
    assert current is not None
    assert current.data(0, MODEL_NODE_ROLE) is page_node


def test_select_node_selects_a_deep_column_node(qtbot):
    project = build_sample_project()
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(project)

    # Equipment page -> first Detail ("Sub-item") -> first Column ("tag").
    column_node = project.pages[0].details[0].columns[0]
    assert tree.select_node(column_node) is True
    assert tree.currentItem().data(0, MODEL_NODE_ROLE) is column_node


def test_select_node_fires_selection_changed_to_properties(qtbot):
    calls = []
    project = build_sample_project()
    tree = ProjectTreePanel(on_selection_changed=lambda node, kind: calls.append((node, kind)))
    qtbot.addWidget(tree)
    tree.populate_from_project(project)

    detail_node = project.pages[0].details[0]
    tree.select_node(detail_node)
    assert calls[-1][0] is detail_node
    assert calls[-1][1] == "detail"


def test_select_node_none_returns_false_and_changes_nothing(qtbot):
    project = build_sample_project()
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(project)
    tree.setCurrentItem(tree.topLevelItem(0))
    before = tree.currentItem()

    assert tree.select_node(None) is False
    assert tree.currentItem() is before


def test_select_node_foreign_node_returns_false_and_changes_nothing(qtbot):
    project = build_sample_project()
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(project)
    tree.setCurrentItem(tree.topLevelItem(0))
    before = tree.currentItem()

    # A node object never inserted into this tree (from a different model).
    foreign = build_sample_project().pages[0]
    assert tree.select_node(foreign) is False
    assert tree.currentItem() is before


def test_index_is_rebuilt_on_repopulate(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)

    first_project = build_sample_project()
    tree.populate_from_project(first_project)
    stale_node = first_project.pages[0]

    second_project = build_sample_project()
    tree.populate_from_project(second_project)

    # The stale node from the first populate is no longer in the index.
    assert tree.select_node(stale_node) is False
    # The fresh node from the second populate is.
    assert tree.select_node(second_project.pages[0]) is True
