from PySide6.QtCore import Qt

from pgtp_editor.diff.records import Difference
from pgtp_editor.ui.diff_merge_panel import DIFFERENCE_ROLE, DiffMergePanel


def make_diff(path, node_kind, kind, attribute=None, old_value=None, new_value=None, ambiguous=False):
    return Difference(
        kind=kind,
        path=path,
        node_kind=node_kind,
        attribute=attribute,
        old_value=old_value,
        new_value=new_value,
        ambiguous=ambiguous,
    )


def test_show_differences_builds_shared_prefix_hierarchy(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(
            ["development_equipment", "pr.r_characteristic/Attachment", "caption"],
            node_kind="detail", kind="changed", attribute="caption",
            old_value="Old", new_value="New",
        ),
        make_diff(
            ["development_equipment", "pr.r_characteristic/Attachment", "ability"],
            node_kind="detail", kind="changed", attribute="ability",
            old_value="view", new_value="insert",
        ),
    ]

    panel.show_differences(diffs)

    assert panel.tree.topLevelItemCount() == 1
    page_item = panel.tree.topLevelItem(0)
    assert page_item.text(0) == "development_equipment"
    assert page_item.childCount() == 1
    detail_item = page_item.child(0)
    assert detail_item.text(0) == "pr.r_characteristic/Attachment"
    assert detail_item.childCount() == 2


def test_show_differences_clears_previous_content(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]

    panel.show_differences(diffs)
    assert panel.tree.topLevelItemCount() == 1

    panel.show_differences(diffs)
    assert panel.tree.topLevelItemCount() == 1


from pgtp_editor.ui.diff_merge_panel import leaf_label


def test_leaf_label_attribute_changed():
    diff = make_diff(
        ["development_equipment", "pr.attachment/Sub-item", "caption"],
        node_kind="detail", kind="changed", attribute="caption",
        old_value="Old", new_value="New",
    )
    assert leaf_label(diff) == "caption: changed"


def test_leaf_label_event_added_uses_last_path_segment():
    diff = make_diff(
        ["development_equipment", "OnRowProcess"],
        node_kind="event", kind="added", attribute=None,
        old_value=None, new_value=object(),
    )
    assert leaf_label(diff) == "OnRowProcess: added"


def test_leaf_label_detail_removed_uses_last_path_segment():
    diff = make_diff(
        ["development_equipment", "pr.attachment/Sub-item"],
        node_kind="detail", kind="removed", attribute=None,
        old_value=object(), new_value=None,
    )
    assert leaf_label(diff) == "pr.attachment/Sub-item: removed"


def test_leaf_items_are_checkable_and_unchecked_by_default(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]

    panel.show_differences(diffs)

    page_item = panel.tree.topLevelItem(0)
    leaf = page_item.child(0)
    assert bool(leaf.flags() & Qt.ItemFlag.ItemIsUserCheckable)
    assert leaf.checkState(0) == Qt.CheckState.Unchecked


def test_group_prefix_items_are_not_checkable(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]

    panel.show_differences(diffs)

    page_item = panel.tree.topLevelItem(0)
    assert not bool(page_item.flags() & Qt.ItemFlag.ItemIsUserCheckable)


def test_ambiguous_leaf_gets_warning_marker(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(
            ["page_a", "pr.operation/Operation", "caption"],
            node_kind="detail", kind="changed", attribute="caption",
            old_value="Old", new_value="New", ambiguous=True,
        )
    ]

    panel.show_differences(diffs)

    leaf = panel.tree.topLevelItem(0).child(0).child(0)
    assert leaf.text(0) == "⚠ caption: changed"


def test_non_ambiguous_leaf_has_no_marker(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]

    panel.show_differences(diffs)

    leaf = panel.tree.topLevelItem(0).child(0)
    assert leaf.text(0) == "caption: changed"


def test_group_prefix_items_not_marked_even_if_all_children_ambiguous(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(
            ["page_a", "pr.operation/Operation", "caption"],
            node_kind="detail", kind="changed", attribute="caption",
            ambiguous=True,
        )
    ]

    panel.show_differences(diffs)

    detail_group_item = panel.tree.topLevelItem(0).child(0)
    assert detail_group_item.text(0) == "pr.operation/Operation"


from pgtp_editor.model.nodes import DetailNode, EventNode


def test_selecting_attribute_changed_leaf_shows_old_and_new(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diff = make_diff(
        ["page_a", "caption"], node_kind="page", kind="changed",
        attribute="caption", old_value="Old Caption", new_value="New Caption",
    )
    panel.show_differences([diff])

    leaf = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(leaf)

    assert panel.detail_stack.currentWidget() is panel.attribute_view
    assert panel.attribute_old_label.text() == "Old: Old Caption"
    assert panel.attribute_new_label.text() == "New: New Caption"


def test_selecting_whole_subtree_added_leaf_shows_attrib_table(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    detail = DetailNode(identity="d1", attrib={"tableName": "pr.attachment", "caption": "Sub-item"})
    diff = make_diff(
        ["page_a", "pr.attachment/Sub-item"], node_kind="detail", kind="added",
        attribute=None, old_value=None, new_value=detail,
    )
    panel.show_differences([diff])

    leaf = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(leaf)

    assert panel.detail_stack.currentWidget() is panel.subtree_view
    assert panel.subtree_table.rowCount() == 2
    values = {
        panel.subtree_table.item(row, 0).text(): panel.subtree_table.item(row, 1).text()
        for row in range(panel.subtree_table.rowCount())
    }
    assert values == {"tableName": "pr.attachment", "caption": "Sub-item"}


def test_selecting_event_text_changed_leaf_shows_unified_diff(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diff = make_diff(
        ["page_a", "OnRowProcess"], node_kind="event", kind="changed",
        attribute=None, old_value="echo 'old';", new_value="echo 'new';",
    )
    panel.show_differences([diff])

    leaf = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(leaf)

    assert panel.detail_stack.currentWidget() is panel.event_diff_view
    text = panel.event_diff_text.toPlainText()
    assert "-echo 'old';" in text
    assert "+echo 'new';" in text


def test_selecting_group_node_clears_detail_view(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diff = make_diff(
        ["page_a", "pr.attachment/Sub-item", "caption"], node_kind="detail",
        kind="changed", attribute="caption", old_value="Old", new_value="New",
    )
    panel.show_differences([diff])

    leaf = panel.tree.topLevelItem(0).child(0).child(0)
    panel.tree.setCurrentItem(leaf)
    assert panel.detail_stack.currentWidget() is panel.attribute_view

    group_item = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(group_item)
    assert panel.detail_stack.currentWidget() is panel.empty_view


def test_select_next_difference_walks_leaves_in_display_order(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption"),
        make_diff(["page_a", "ability"], node_kind="page", kind="changed", attribute="ability"),
        make_diff(["page_b", "caption"], node_kind="page", kind="changed", attribute="caption"),
    ]
    panel.show_differences(diffs)

    panel.select_next_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[0]

    panel.select_next_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[1]

    panel.select_next_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[2]

    # Stops at the last leaf — no wraparound required.
    panel.select_next_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[2]


def test_select_previous_difference_walks_leaves_backward(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption"),
        make_diff(["page_a", "ability"], node_kind="page", kind="changed", attribute="ability"),
    ]
    panel.show_differences(diffs)

    panel.tree.setCurrentItem(panel.tree.topLevelItem(0).child(1))
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[1]

    panel.select_previous_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[0]

    # Stops at the first leaf — no wraparound required.
    panel.select_previous_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[0]


def test_checked_differences_returns_only_checked_leaves_in_tree_order(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption"),
        make_diff(["page_a", "ability"], node_kind="page", kind="changed", attribute="ability"),
        make_diff(["page_b", "caption"], node_kind="page", kind="changed", attribute="caption"),
    ]
    panel.show_differences(diffs)

    leaves = panel._flattened_leaves()
    leaves[0].setCheckState(0, Qt.CheckState.Checked)
    leaves[2].setCheckState(0, Qt.CheckState.Checked)
    # leaves[1] stays Unchecked (default).

    checked = panel.checked_differences()

    assert checked == [diffs[0], diffs[2]]


def test_checked_differences_returns_empty_list_when_nothing_checked(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]
    panel.show_differences(diffs)

    assert panel.checked_differences() == []


def test_checked_differences_never_includes_group_prefix_nodes(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(
            ["development_equipment", "pr.attachment/Sub-item", "caption"],
            node_kind="detail", kind="changed", attribute="caption",
        ),
    ]
    panel.show_differences(diffs)

    leaves = panel._flattened_leaves()
    leaves[0].setCheckState(0, Qt.CheckState.Checked)

    checked = panel.checked_differences()

    assert checked == [diffs[0]]
    assert len(checked) == 1
