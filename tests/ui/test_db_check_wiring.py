# tests/ui/test_db_check_wiring.py
"""MainWindow wiring for the Database Check (SP2): menu items, _run_db_check,
rename and jump handlers. No live DB (patched `_fetch_db_schema`), no modal
(the rename prompt goes through the `_prompt_rename` seam)."""
from lxml import etree

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.model.nodes import ColumnNode, PageNode, ProjectModel
from pgtp_editor.ui.main_window import MainWindow

from ._menu_helpers import find_action, find_top_menu

_RAW_XML = (
    '<Project>\n'
    '  <ConnectionOptions host="h" port="5432" login="u" database="d"/>\n'
    '  <Page tableName="pr.a">\n'
    '    <Column fieldName="id"/>\n'
    '  </Page>\n'
    '</Project>\n'
)


def _project():
    tree = etree.ElementTree(etree.fromstring(_RAW_XML.encode()))
    page = PageNode(
        identity="p",
        attrib={"tableName": "pr.a"},
        columns=[ColumnNode(identity="id", attrib={"fieldName": "id"})],
    )
    return ProjectModel(pages=[page], tree=tree)


def _schema():
    a = TableInfo(
        name="pr.a", kind="table",
        columns=[ColumnInfo("id", "integer", True, False, False, None)],
    )
    missing_xml = TableInfo(
        name="pr.b", kind="view",
        columns=[ColumnInfo("c", "text", False, False, True, None)],
    )
    return DatabaseSchema(tables={"pr.a": a, "pr.b": missing_xml})


def _window_with_project(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project = _project()
    window.center_stage.xml_editor.setPlainText(_RAW_XML)
    window._fetch_db_schema = lambda params: _schema()
    return window


def test_check_menu_items_exist(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Database")
    assert find_action(menu, "Check: XML → Database") is not None
    assert find_action(menu, "Check: Database → XML") is not None


def test_run_db_check_xml_to_db_populates_and_reveals(qtbot):
    window = _window_with_project(qtbot)
    window._run_db_check("xml_to_db")

    panel = window.db_check_panel
    assert panel.tree.topLevelItemCount() >= 1
    assert window.left_tabs.isTabVisible(window.db_check_tab_index)
    assert window.left_tabs.currentWidget() is panel
    assert window._last_db_check_direction == "xml_to_db"


def test_run_db_check_db_to_xml_populates(qtbot):
    window = _window_with_project(qtbot)
    window._run_db_check("db_to_xml")
    # Both DB tables listed.
    names = [
        window.db_check_panel.tree.topLevelItem(i).text(0)
        for i in range(window.db_check_panel.tree.topLevelItemCount())
    ]
    assert any("pr.a" in n for n in names)
    assert any("pr.b" in n for n in names)


def test_run_db_check_no_project(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._current_project is None
    window._run_db_check("xml_to_db")  # must not crash
    assert window.db_check_panel.tree.topLevelItemCount() == 0
    assert not window.left_tabs.isTabVisible(window.db_check_tab_index)


def test_run_db_check_fetch_error_shows_status(qtbot):
    window = _window_with_project(qtbot)

    def _boom(params):
        raise RuntimeError("no route to host")

    window._fetch_db_schema = _boom
    window._run_db_check("xml_to_db")  # must not crash
    assert window.db_check_panel.tree.topLevelItemCount() == 0


def test_on_db_rename_requested_updates_buffer_marks_dirty_and_reruns(qtbot):
    window = _window_with_project(qtbot)
    window._run_db_check("xml_to_db")
    window._set_dirty(False)

    window._prompt_rename = lambda old: "pr.renamed"

    calls = []
    original = window._run_db_check
    window._run_db_check = lambda direction: calls.append(direction) or original(direction)

    window._on_db_rename_requested("table", "pr.a")

    assert 'tableName="pr.renamed"' in window.center_stage.xml_editor.toPlainText()
    assert 'tableName="pr.a"' not in window.center_stage.xml_editor.toPlainText()
    assert window._dirty is True
    assert calls == ["xml_to_db"]  # re-ran the last check


def test_on_db_rename_requested_cancelled_prompt_no_change(qtbot):
    window = _window_with_project(qtbot)
    window._prompt_rename = lambda old: None
    before = window.center_stage.xml_editor.toPlainText()
    window._on_db_rename_requested("table", "pr.a")
    assert window.center_stage.xml_editor.toPlainText() == before


def test_on_db_jump_requested_navigates_to_line(qtbot):
    window = _window_with_project(qtbot)
    navigated = []
    window.center_stage.xml_editor.navigate_to_line = lambda line: navigated.append(line)

    window._on_db_jump_requested("column", "id")
    assert navigated == [4]  # fieldName="id" is on line 4
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index

    navigated.clear()
    window._on_db_jump_requested("table", "pr.a")
    assert navigated == [3]  # tableName="pr.a" is on line 3
