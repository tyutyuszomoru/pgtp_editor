# tests/ui/test_reused_tables_window.py
from pgtp_editor.analysis.reused_tables import TableUsage
from pgtp_editor.ui.reused_tables_window import ReusedTablesWindow


def test_set_usages_populates_tree(qtbot):
    window = ReusedTablesWindow()
    qtbot.addWidget(window)
    window.set_usages(
        [
            TableUsage(name="customers", breadcrumbs=["Page 'Orders' ▸ Column 'x' (lookup)"]),
            TableUsage(
                name="orders",
                breadcrumbs=["Page 'Orders'", "Page 'Orders' ▸ Detail 'Items'"],
            ),
        ]
    )

    tree = window.tree
    assert tree.topLevelItemCount() == 2

    first = tree.topLevelItem(0)
    assert first.text(0) == "customers  (1)"
    assert first.childCount() == 1

    second = tree.topLevelItem(1)
    assert second.text(0) == "orders  (2)"
    assert second.childCount() == 2
    assert second.child(1).text(0) == "Page 'Orders' ▸ Detail 'Items'"


def test_set_usages_replaces_previous_content(qtbot):
    window = ReusedTablesWindow()
    qtbot.addWidget(window)
    window.set_usages([TableUsage(name="a", breadcrumbs=["Page 'A'"])])
    window.set_usages([TableUsage(name="b", breadcrumbs=["Page 'B'"])])

    assert window.tree.topLevelItemCount() == 1
    assert window.tree.topLevelItem(0).text(0) == "b  (1)"
