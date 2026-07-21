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


def test_double_click_table_row_does_not_emit_jump(qtbot):
    # A top-level (table) row carries no TableReference, so double-clicking it
    # must not fire jump_requested (there is nothing to navigate to).
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, _ = _usage()
    panel.set_usages([usage])
    got = []
    panel.jump_requested.connect(lambda line: got.append(line))

    top = panel.tree.topLevelItem(0)
    panel.tree.itemDoubleClicked.emit(top, 0)

    assert got == []


def test_double_click_reference_with_none_line_emits_none(qtbot):
    # line may be None (e.g. an element with no sourceline); the panel still
    # emits it and MainWindow's _tree_jump_to_line no-ops downstream.
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    ref = TableReference(
        breadcrumb="Page 'O'", node=object(), kind="page",
        line=None, ref_type="table",
    )
    panel.set_usages([TableUsage(name="t", references=[ref])])
    got = []
    panel.jump_requested.connect(lambda line: got.append(line))

    child = panel.tree.topLevelItem(0).child(0)
    panel.tree.itemDoubleClicked.emit(child, 0)

    assert got == [None]


def test_set_usages_preserves_multiple_table_order_and_counts(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    ref_a = TableReference("Page 'A'", object(), "page", 1, "table")
    ref_b1 = TableReference("Page 'B'", object(), "page", 2, "table")
    ref_b2 = TableReference("Page 'C'", object(), "page", 3, "table")
    usages = [
        TableUsage(name="alpha", references=[ref_a]),
        TableUsage(name="beta", references=[ref_b1, ref_b2]),
    ]

    panel.set_usages(usages)

    assert panel.tree.topLevelItemCount() == 2
    assert panel.tree.topLevelItem(0).text(0) == "alpha  (1)"
    assert panel.tree.topLevelItem(1).text(0) == "beta  (2)"
    assert panel.tree.topLevelItem(1).childCount() == 2
