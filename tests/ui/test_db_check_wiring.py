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


def _drain_find_all(window):
    """Synchronously exhaust the streaming Find-all timer (mirrors the pattern in
    test_main_window): stop the 0ms QTimer and step until the summary lands."""
    if window._find_all_timer is not None:
        window._find_all_timer.stop()
    for _ in range(10):
        if window._find_all_iter is None:
            break
        window._find_all_step()


def test_on_db_jump_requested_lists_all_and_selects_first(qtbot):
    window = _window_with_project(qtbot)
    bar = window.center_stage.find_replace_bar
    editor = window.center_stage.xml_editor

    window._on_db_jump_requested("column", "id")

    # Raw tab active; Find bar seeded with the fieldName token so F3 can step.
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index
    assert bar._find_field.text() == 'fieldName="id"'
    # First occurrence selected in the editor.
    assert editor.textCursor().selectedText() == 'fieldName="id"'
    # Find-all streaming started for the same token; results land in the panel.
    assert window._find_all_term == 'fieldName="id"'
    _drain_find_all(window)
    find_rows = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any(t.startswith("[Find] ") and 'fieldName="id"' in t for t in find_rows)


def test_on_db_jump_requested_table_token(qtbot):
    window = _window_with_project(qtbot)
    editor = window.center_stage.xml_editor
    window._on_db_jump_requested("table", "pr.a")
    assert window.center_stage.find_replace_bar._find_field.text() == 'tableName="pr.a"'
    assert editor.textCursor().selectedText() == 'tableName="pr.a"'


def test_on_db_jump_requested_missing_token_shows_status(qtbot):
    window = _window_with_project(qtbot)
    window._on_db_jump_requested("table", "pr.absent")
    assert "not found" in window.statusBar().currentMessage()


_MULTI_XML = (
    '<Project>\n'
    '  <Presentation><Pages>\n'
    '    <Page fileName="a" tableName="pr.a"/>\n'
    '    <Page fileName="b" tableName="pr.a"/>\n'
    '    <Page fileName="c" tableName="pr.a"/>\n'
    '  </Pages></Presentation>\n'
    '</Project>\n'
)


def test_f3_steps_through_occurrences_after_db_jump(qtbot):
    """After a DB double-click, F3 (Find Next) walks to each next occurrence of
    the token and wraps — reusing the existing find-next machinery."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_MULTI_XML)
    editor = window.center_stage.xml_editor

    window._on_db_jump_requested("table", "pr.a")
    # First occurrence selected (line 3).
    first = editor.textCursor().selectionStart()

    window._find_next()  # F3
    second = editor.textCursor().selectionStart()
    assert second > first
    assert editor.textCursor().selectedText() == 'tableName="pr.a"'

    window._find_next()  # F3 -> third
    third = editor.textCursor().selectionStart()
    assert third > second

    window._find_next()  # F3 -> wraps back to first
    assert editor.textCursor().selectionStart() == first


_MULTI_COL_XML = (
    '<Project>\n'
    '  <Presentation><Pages>\n'
    '    <Page fileName="a" tableName="pr.a">\n'
    '      <ColumnPresentations>\n'
    '        <ColumnPresentation fieldName="dup"/>\n'
    '        <ColumnPresentation fieldName="dup"/>\n'
    '        <ColumnPresentation fieldName="dup"/>\n'
    '      </ColumnPresentations>\n'
    '    </Page>\n'
    '  </Pages></Presentation>\n'
    '</Project>\n'
)


def test_on_db_jump_column_lists_all_and_f3_steps(qtbot):
    """Double-clicking a COLUMN node seeds the fieldName token, selects the first
    occurrence, lists every occurrence, and F3 walks 1->2->3->wrap."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_MULTI_COL_XML)
    editor = window.center_stage.xml_editor
    bar = window.center_stage.find_replace_bar

    window._on_db_jump_requested("column", "dup")

    assert bar._find_field.text() == 'fieldName="dup"'
    assert editor.textCursor().selectedText() == 'fieldName="dup"'
    first = editor.textCursor().selectionStart()

    # Every occurrence is listed in the panel.
    _drain_find_all(window)
    find_rows = [
        window.audit_panel.item(i).text()
        for i in range(window.audit_panel.count())
        if window.audit_panel.item(i).text().startswith("[Find] ")
    ]
    # 3 occurrence rows + 1 summary row.
    assert sum('fieldName="dup"' in r and "line" in r for r in find_rows) == 3

    window._find_next()  # F3 -> 2nd
    second = editor.textCursor().selectionStart()
    assert second > first
    window._find_next()  # F3 -> 3rd
    third = editor.textCursor().selectionStart()
    assert third > second
    window._find_next()  # F3 -> wraps to 1st
    assert editor.textCursor().selectionStart() == first


def test_f3_single_occurrence_wraps_to_itself(qtbot):
    """A token appearing exactly once: F3 re-selects the same single occurrence
    (wrap lands back on itself), never losing the selection."""
    window = _window_with_project(qtbot)
    editor = window.center_stage.xml_editor

    window._on_db_jump_requested("column", "id")  # fieldName="id" occurs once
    start = editor.textCursor().selectionStart()
    assert editor.textCursor().selectedText() == 'fieldName="id"'

    window._find_next()  # F3 -> wraps back to the same match
    assert editor.textCursor().selectionStart() == start
    assert editor.textCursor().selectedText() == 'fieldName="id"'


def test_second_db_jump_does_not_accumulate_find_rows(qtbot):
    """A second double-click re-runs Find All, which clears prior [Find] rows so
    results don't pile up across double-clicks."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_MULTI_XML)  # 3x tableName="pr.a"

    window._on_db_jump_requested("table", "pr.a")
    _drain_find_all(window)
    first_count = sum(
        window.audit_panel.item(i).text().startswith("[Find] ")
        for i in range(window.audit_panel.count())
    )

    window._on_db_jump_requested("table", "pr.a")
    _drain_find_all(window)
    second_count = sum(
        window.audit_panel.item(i).text().startswith("[Find] ")
        for i in range(window.audit_panel.count())
    )

    assert first_count > 0
    assert second_count == first_count  # cleared + re-added, not accumulated


def test_missing_token_leaves_find_field_and_selection_untouched(qtbot):
    """Zero occurrences: the guard shows a status message and does NOT re-seed
    the Find bar, move the selection, or start a Find All."""
    window = _window_with_project(qtbot)
    bar = window.center_stage.find_replace_bar
    editor = window.center_stage.xml_editor

    # Pre-seed a distinct find term and a selection to prove they survive.
    bar.set_find_text("SENTINEL")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, cursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    pre_sel = editor.textCursor().selectedText()

    window._on_db_jump_requested("table", "pr.absent")

    assert "not found" in window.statusBar().currentMessage()
    assert bar._find_field.text() == "SENTINEL"  # untouched
    assert editor.textCursor().selectedText() == pre_sel  # untouched
    assert window._find_all_term != 'tableName="pr.absent"'


def test_db_jump_reveals_hidden_audit_dock(qtbot):
    """If a prior action left the Audit dock hidden, a DB double-click reveals it
    so the listed occurrences are visible."""
    window = _window_with_project(qtbot)
    window.audit_dock.setVisible(False)
    assert window.audit_dock.isHidden()

    window._on_db_jump_requested("column", "id")

    # The offscreen top-level window is never shown, so isVisible() would be
    # False regardless; assert the explicit hidden flag the handler toggles.
    assert not window.audit_dock.isHidden()


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
