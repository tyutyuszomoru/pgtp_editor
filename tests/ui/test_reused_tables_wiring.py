# tests/ui/test_reused_tables_wiring.py
from pgtp_editor.analysis.reused_tables import collect_table_usages
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._sample_project import build_sample_project


def test_open_reused_tables_populates_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    project = build_sample_project()
    window._current_project = project

    window._open_reused_tables()

    tree = window._reused_tables_window.tree
    expected = collect_table_usages(project)
    assert tree.topLevelItemCount() == len(expected)

    # pr.r_characteristic is referenced by two pages' details.
    by_name = {u.name: u for u in expected}
    shared = by_name["pr.r_characteristic"]
    assert shared.breadcrumbs and len(shared.breadcrumbs) == 2
    row = next(
        tree.topLevelItem(i)
        for i in range(tree.topLevelItemCount())
        if tree.topLevelItem(i).text(0).startswith("pr.r_characteristic")
    )
    assert row.childCount() == 2


def test_open_reused_tables_without_project_does_nothing(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._current_project is None

    window._open_reused_tables()  # must not raise

    assert window._reused_tables_window is None
