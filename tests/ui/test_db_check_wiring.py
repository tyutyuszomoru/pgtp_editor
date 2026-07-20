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
    '  <Presentation><Pages>\n'
    '    <Page fileName="a" tableName="pr.a">\n'
    '      <ColumnPresentations>\n'
    '        <ColumnPresentation fieldName="id"/>\n'
    '      </ColumnPresentations>\n'
    '    </Page>\n'
    '  </Pages></Presentation>\n'
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


def _sync_run(fn, on_result, on_error=None):
    """Synchronous stand-in for run_async: keeps _run_db_check deterministic and
    modal-free while still exercising the busy-state + result path. Production
    runs the schema fetch on a threadpool worker."""
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def _window_with_project(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project = _project()
    window.center_stage.xml_editor.setPlainText(_RAW_XML)
    window._fetch_db_schema = lambda params: _schema()
    window._run_async = _sync_run
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
    # The fetch error routes to on_error -> a status message, no crash.
    assert "no route to host" in window.statusBar().currentMessage()


def test_run_db_check_shows_busy_status_then_populates_on_result(qtbot):
    """With a deferred runner, _run_db_check sets the 'Checking…' busy status and
    leaves the panel empty until the schema is delivered; delivering it (on the
    GUI thread) populates the panel and reveals the tab -- both directions."""
    for direction in ("xml_to_db", "db_to_xml"):
        window = _window_with_project(qtbot)
        captured = {}

        def deferred(fn, on_result, on_error=None, _c=captured):
            _c["fn"] = fn
            _c["on_result"] = on_result

        window._run_async = deferred
        window._run_db_check(direction)

        assert "Checking database" in window.statusBar().currentMessage()
        assert window.db_check_panel.tree.topLevelItemCount() == 0
        assert not window.left_tabs.isTabVisible(window.db_check_tab_index)

        # Deliver the schema back on the GUI thread.
        captured["on_result"](captured["fn"]())
        assert window.db_check_panel.tree.topLevelItemCount() >= 1
        assert window.left_tabs.isTabVisible(window.db_check_tab_index)
        assert window._last_db_check_direction == direction


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
    assert navigated == [6]  # fieldName="id" is on line 6
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index

    navigated.clear()
    window._on_db_jump_requested("table", "pr.a")
    assert navigated == [4]  # tableName="pr.a" is on line 4


_RENAME_XML = (
    '<Project>\n'
    '  <ConnectionOptions host="h" port="5432" login="u" database="d"/>\n'
    '  <Presentation><Pages>\n'
    '    <Page fileName="a" tableName="pr.a">\n'
    '      <ColumnPresentations>\n'
    '        <ColumnPresentation fieldName="old_col"/>\n'
    '      </ColumnPresentations>\n'
    '    </Page>\n'
    '  </Pages></Presentation>\n'
    '</Project>\n'
)


def test_rename_resolves_mismatch_on_rerun_from_buffer(qtbot):
    """The reconcile loop must actually work: after renaming a not-found column
    to the DB name, the re-run (parsed from the edited buffer) flips it ✗→✓."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_RENAME_XML)
    window._run_async = _sync_run
    # DB has 'new_col', not 'old_col'.
    schema = DatabaseSchema(tables={
        "pr.a": TableInfo(
            name="pr.a", kind="table",
            columns=[ColumnInfo("new_col", "integer", False, False, True, None)],
        )
    })
    window._fetch_db_schema = lambda params: schema

    window._run_db_check("xml_to_db")
    assert window.db_check_panel._mismatch_count() >= 1  # old_col not found

    # Rename old_col -> new_col (rewrites the buffer + re-runs the check).
    window._prompt_rename = lambda old: "new_col"
    window._on_db_rename_requested("column", "old_col")

    assert 'fieldName="new_col"' in window.center_stage.xml_editor.toPlainText()
    assert window.db_check_panel._mismatch_count() == 0  # resolved from the buffer


def _run_initial_check(window, direction="xml_to_db"):
    """Do one real (patched-fetch) check so the cache + panel are populated
    and the tab is revealed."""
    window._run_db_check(direction)


def test_run_db_check_captures_summary(qtbot):
    window = _window_with_project(qtbot)
    _run_initial_check(window)
    assert window._last_db_check_direction == "xml_to_db"
    assert window._last_db_schema is not None
    assert window._last_db_summary == "u@h:5432/d"


def test_reparse_refreshes_open_db_check_with_cached_schema(qtbot):
    window = _window_with_project(qtbot)
    fetches = []
    base_fetch = window._fetch_db_schema
    window._fetch_db_schema = lambda params: (fetches.append(1), base_fetch(params))[1]
    _run_initial_check(window)
    assert fetches == [1]                      # one fetch for the initial check

    # Edit the buffer (add a column that IS in the schema was already; instead
    # remove the page's only column reference to change the mismatch set), then
    # spy on set_result so we see only the reparse-driven repopulate.
    calls = []
    real_set = window.db_check_panel.set_result
    window.db_check_panel.set_result = lambda *a: (calls.append(a), real_set(*a))[1]

    edited = _RAW_XML.replace('fieldName="id"', 'fieldName="nonexistent"')
    window.center_stage.xml_editor.setPlainText(edited)

    window._reparse_raw_xml()

    assert fetches == [1]                       # NO re-query — cached schema reused
    assert len(calls) == 1                       # panel repopulated once by reparse
    direction, checks, summary = calls[0]
    assert direction == "xml_to_db"
    assert summary == "u@h:5432/d"
    # checks reflect the EDITED buffer against the cached schema:
    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.db.compare import check_xml_against_db
    proj = load_project_from_text(edited, source_description="<editor>")
    assert checks == check_xml_against_db(proj, window._last_db_schema)


def test_reparse_no_refresh_when_db_tab_hidden(qtbot):
    window = _window_with_project(qtbot)
    _run_initial_check(window)
    window.left_tabs.setTabVisible(window.db_check_tab_index, False)
    calls = []
    window.db_check_panel.set_result = lambda *a: calls.append(a)
    window._reparse_raw_xml()
    assert calls == []


def test_reparse_no_refresh_without_prior_check(qtbot):
    window = _window_with_project(qtbot)
    # no check run: cache empty, tab hidden by default
    calls = []
    window.db_check_panel.set_result = lambda *a: calls.append(a)
    window._reparse_raw_xml()
    assert calls == []
