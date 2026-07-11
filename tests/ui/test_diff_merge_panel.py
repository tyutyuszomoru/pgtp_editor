from PySide6.QtCore import Qt

from pgtp_editor.diff.records import Difference
from pgtp_editor.ui.diff_merge_panel import DiffMergePanel


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
