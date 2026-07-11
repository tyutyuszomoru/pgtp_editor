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
