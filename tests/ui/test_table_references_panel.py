from PySide6.QtCore import Qt

from pgtp_editor.analysis.reused_tables import TableReference, TableUsage
from pgtp_editor.ui.table_references_panel import TableReferencesPanel


def _usage():
    ref = TableReference(
        breadcrumb="Page 'O' ▸ Column 'objecttype' (lookup with insert)",
        node=object(), kind="column", line=5, ref_type="lookup with insert",
    )
    return TableUsage(name="kb.x_objecttype", references=[ref]), ref


def test_set_usages_builds_table_row_with_count_and_child(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, ref = _usage()

    panel.set_usages([usage])

    assert panel.tree.topLevelItemCount() == 1
    top = panel.tree.topLevelItem(0)
    assert top.text(0) == "kb.x_objecttype  (1)"
    assert top.childCount() == 1
    child = top.child(0)
    assert child.text(0) == ref.breadcrumb
    assert child.data(0, Qt.ItemDataRole.UserRole) is ref


def test_selection_of_reference_emits_node_and_kind(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, ref = _usage()
    panel.set_usages([usage])
    got = []
    panel.selection_changed.connect(lambda node, kind: got.append((node, kind)))

    child = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(child)

    assert got and got[-1] == (ref.node, "column")


def test_selection_of_table_row_emits_none(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, _ref = _usage()
    panel.set_usages([usage])
    got = []
    panel.selection_changed.connect(lambda node, kind: got.append((node, kind)))

    panel.tree.setCurrentItem(panel.tree.topLevelItem(0))

    assert got and got[-1] == (None, None)


def test_double_click_reference_emits_jump_with_line(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, ref = _usage()
    panel.set_usages([usage])
    got = []
    panel.jump_requested.connect(lambda line: got.append(line))

    child = panel.tree.topLevelItem(0).child(0)
    panel.tree.itemDoubleClicked.emit(child, 0)

    assert got == [5]


def test_set_usages_clears_previous_rows(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, _ = _usage()
    panel.set_usages([usage])
    panel.set_usages([])
    assert panel.tree.topLevelItemCount() == 0
