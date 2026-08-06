# tests/ui/test_db_check_wiring.py
"""MainWindow wiring for the merged Database/XML Coherence view (§17, FQ-003):
the single Database-menu toggle, `run_check`, rename and jump handlers.

The lane lives on `window._db_ui` (`ui/coherence_controller.py`); no live DB
(patched `fetch_schema`), no modal (the rename prompt goes through the
`prompt_rename` seam).

Successor to the two-direction Database Check wiring: the direction argument
and the `_last_db_check_direction` cache are gone with the direction toggle."""
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


def _node_shape(node):
    """A comparable rendering of a CoherenceNode subtree.

    CoherenceNode carries the live model node, so two trees built from two
    parses of the same text are never `==` even when they display identically.
    Everything the panel actually shows is captured here."""
    return (
        node.kind,
        node.label,
        node.badges,
        node.flagged,
        node.table_name,
        node.line,
        tuple(_node_shape(child) for child in node.children),
    )


def _shape(tree):
    return tuple(_node_shape(branch) for branch in tree.branches)


def _sync_run(fn, on_result, on_error=None):
    """Synchronous stand-in for run_async: keeps run_check deterministic and
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
    window._db_ui.fetch_schema = lambda params: _schema()
    window._run_async = _sync_run
    return window


def test_database_menu_offers_the_coherence_toggle_only(qtbot):
    """§26: one checkable "Database/XML Coherence" entry, and neither of the
    two direction items it replaced."""
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Database")
    action = find_action(menu, "Database/XML Coherence")
    assert action is not None
    assert action.isCheckable() is True
    assert action.isChecked() is False
    assert action.shortcut().isEmpty()  # deliberately unshortcut (§26)
    assert find_action(menu, "Check: XML → Database") is None
    assert find_action(menu, "Check: Database → XML") is None


def test_run_db_check_populates_and_reveals(qtbot):
    window = _window_with_project(qtbot)
    window._db_ui.run_check()

    panel = window.coherence_panel
    # Both branches ("Tables and Views" + "Pages") are top-level roots.
    assert panel.tree.topLevelItemCount() == 2
    assert panel.result is not None
    assert window.left_tabs.isTabVisible(window.coherence_tab_index)
    assert window.left_tabs.currentWidget() is panel


def test_close_project_hides_db_check_tab_and_clears_caches(qtbot):
    # BUG-011: the Database Check results are project-tied -- committing a
    # close hides the tab, clears the panel and drops the cached schema/summary.
    window = _window_with_project(qtbot)
    window._db_ui.run_check()
    assert window.left_tabs.isTabVisible(window.coherence_tab_index)

    window._close_project(confirm="discard")

    assert not window.left_tabs.isTabVisible(window.coherence_tab_index)
    assert window._db_ui.last_schema is None
    assert window._db_ui.last_summary is None


def test_close_clean_buffer_hides_db_check_tab_and_clears_caches(qtbot):
    # BUG-011 gap: closing a CLEAN buffer (confirm=None, treated as discard)
    # is also a committed close and must tear down the db-check surface.
    window = _window_with_project(qtbot)
    window._db_ui.run_check()
    window._set_dirty(False)
    assert window.left_tabs.isTabVisible(window.coherence_tab_index)

    window._close_project()  # clean: no confirm seam consulted, no modal

    assert not window.left_tabs.isTabVisible(window.coherence_tab_index)
    assert window._db_ui.last_schema is None
    assert window._db_ui.last_summary is None


def test_close_via_successful_save_hides_db_check_tab(qtbot):
    # BUG-011 gap: confirm="save" with a save that succeeds (dirty -> False)
    # commits the close and tears down the db-check surface.
    window = _window_with_project(qtbot)
    window._db_ui.run_check()
    window._set_dirty(True)
    window._save_project = lambda: window._set_dirty(False)  # save succeeds

    window._close_project(confirm="save")

    assert not window.left_tabs.isTabVisible(window.coherence_tab_index)
    assert window._db_ui.last_schema is None
    assert window._db_ui.last_summary is None


def test_close_via_cancelled_save_keeps_db_check_tab_and_caches(qtbot):
    # BUG-011 gap: confirm="save" whose save is cancelled (dirty stays True,
    # e.g. Save-As dialog dismissed) aborts the close -- the still-open
    # project's tab and caches must survive.
    window = _window_with_project(qtbot)
    window._db_ui.run_check()
    window._set_dirty(True)
    window._save_project = lambda: None  # save cancelled: stays dirty

    window._close_project(confirm="save")

    assert window._dirty is True  # close aborted
    assert window.left_tabs.isTabVisible(window.coherence_tab_index)
    assert window._db_ui.last_schema is not None
    assert window._db_ui.last_summary is not None


def test_fresh_db_check_after_close_reveals_and_repopulates(qtbot):
    # BUG-011 gap: after close-teardown, opening a new project and running a
    # fresh check re-reveals the tab and repopulates the panel + caches.
    window = _window_with_project(qtbot)
    window._db_ui.run_check()
    window._close_project(confirm="discard")
    assert not window.left_tabs.isTabVisible(window.coherence_tab_index)

    # "Open" a new project (same seams as _window_with_project).
    window._current_project = _project()
    window.center_stage.xml_editor.setPlainText(_RAW_XML)
    window._db_ui.run_check()

    assert window.left_tabs.isTabVisible(window.coherence_tab_index)
    assert window.coherence_panel.tree.topLevelItemCount() == 2
    assert window._db_ui.last_schema is not None
    assert window._db_ui.last_summary == "u@h:5432/d"


def test_cancelled_close_leaves_db_check_tab_and_caches(qtbot):
    # A cancelled close must leave the still-open project's tab and caches
    # alone (BUG-011 gotcha: teardown only on the committed-close path).
    window = _window_with_project(qtbot)
    window._db_ui.run_check()
    window._set_dirty(True)  # dirty so the confirm seam is consulted

    window._close_project(confirm="cancel")

    assert window.left_tabs.isTabVisible(window.coherence_tab_index)
    assert window._db_ui.last_schema is not None
    assert window._db_ui.last_summary is not None


def test_run_db_check_lists_every_db_relation(qtbot):
    """The Tables and Views branch is DB-sourced: every live relation is a row,
    including one the XML never mentions (formerly the db_to_xml direction)."""
    window = _window_with_project(qtbot)
    window._db_ui.run_check()
    tables_branch = window.coherence_panel.tree.topLevelItem(0)
    names = [
        tables_branch.child(i).text(0) for i in range(tables_branch.childCount())
    ]
    assert any("pr.a" in n for n in names)
    assert any("pr.b" in n for n in names)


def test_run_db_check_no_project(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._current_project is None
    window._db_ui.run_check()  # must not crash
    assert window.coherence_panel.tree.topLevelItemCount() == 0
    assert not window.left_tabs.isTabVisible(window.coherence_tab_index)


def test_toggle_on_without_a_buffer_unchecks_itself(qtbot):
    """BUG-021 shape: driven through the real triggered/toggled signal. An
    empty buffer refuses the run, so the menu must not keep claiming the view
    is open."""
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Database")
    find_action(menu, "Database/XML Coherence").trigger()

    assert window._db_ui.toggle_action.isChecked() is False
    assert not window.left_tabs.isTabVisible(window.coherence_tab_index)


def test_toggle_on_via_the_real_action_fetches_populates_and_reveals(qtbot):
    """The whole point of BUG-021: go through action.trigger(), which delivers
    the checked state, rather than calling the slot directly."""
    window = _window_with_project(qtbot)
    menu = find_top_menu(window, "Database")
    action = find_action(menu, "Database/XML Coherence")

    action.trigger()

    assert action.isChecked() is True
    assert window.left_tabs.isTabVisible(window.coherence_tab_index)
    assert window.left_tabs.currentWidget() is window.coherence_panel
    assert window.coherence_panel.result is not None
    assert window._db_ui.last_schema is not None


def test_toggle_off_via_the_real_action_hides_the_tab(qtbot):
    window = _window_with_project(qtbot)
    action = find_action(find_top_menu(window, "Database"), "Database/XML Coherence")
    action.trigger()
    assert window.left_tabs.isTabVisible(window.coherence_tab_index)

    action.trigger()

    assert action.isChecked() is False
    assert not window.left_tabs.isTabVisible(window.coherence_tab_index)


def test_toggle_off_then_on_re_runs_and_re_reveals(qtbot):
    window = _window_with_project(qtbot)
    fetches = []
    base = window._db_ui.fetch_schema
    window._db_ui.fetch_schema = lambda p: (fetches.append(1), base(p))[1]
    action = find_action(find_top_menu(window, "Database"), "Database/XML Coherence")

    action.trigger()
    action.trigger()
    action.trigger()

    assert fetches == [1, 1]  # toggling back on is a fresh run, not a redisplay
    assert window.left_tabs.isTabVisible(window.coherence_tab_index)


def test_view_menu_no_longer_offers_find_table_reference(qtbot):
    """FQ-003: the standalone Table References entry point is gone; the merged
    view is the only way in."""
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert find_action(view_menu, "Find table reference") is None
    assert not hasattr(window, "_table_refs_action")
    assert not hasattr(window, "table_refs_tab_index")


_RAW_XML_NO_CONNECTION = (
    '<Project>\n'
    '  <Presentation><Pages>\n'
    '    <Page fileName="a" tableName="pr.a">\n'
    '      <ColumnPresentations>\n'
    '        <ColumnPresentation fieldName="id"/>\n'
    '      </ColumnPresentations>\n'
    '    </Page>\n'
    '  </Pages></Presentation>\n'
    '</Project>\n'
)


def _project_no_connection():
    tree = etree.ElementTree(etree.fromstring(_RAW_XML_NO_CONNECTION.encode()))
    page = PageNode(
        identity="p",
        attrib={"tableName": "pr.a"},
        columns=[ColumnNode(identity="id", attrib={"fieldName": "id"})],
    )
    return ProjectModel(pages=[page], tree=tree)


def test_run_db_check_without_connection_opens_standalone_setup(qtbot):
    """BUG-024: standalone mode (no §18.2 project active), a missing
    connection opens the app-level Connection Setup dialog -- unchanged
    behavior."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project = _project_no_connection()
    window.center_stage.xml_editor.setPlainText(_RAW_XML_NO_CONNECTION)
    fetches = []
    window._db_ui.fetch_schema = lambda params: fetches.append(1) or _schema()
    window._run_async = _sync_run

    window._db_ui.run_check()

    assert window._connection_dialog is not None
    assert fetches == []
    assert window.coherence_panel.tree.topLevelItemCount() == 0


def test_run_db_check_without_connection_and_project_open_reroutes_to_project_settings(qtbot, tmp_path):
    """BUG-024: with a §18.2 project open, run_check's missing-connection
    path must point at Project Settings instead of the meaningless standalone
    Connection Setup dialog -- the same _prompt_missing_connection reroute
    already covered for _open_ddl_explorer in test_ddl_explorer_wiring.py."""
    from pgtp_editor.db.ddl_project import ProjectSettings

    window = MainWindow()
    qtbot.addWidget(window)
    window._set_active_ddl_project(tmp_path / "proj", ProjectSettings())
    window._current_project = _project_no_connection()
    window.center_stage.xml_editor.setPlainText(_RAW_XML_NO_CONNECTION)
    fetches = []
    window._db_ui.fetch_schema = lambda params: fetches.append(1) or _schema()
    window._run_async = _sync_run

    window._db_ui.run_check()

    assert window._connection_dialog is None  # standalone Connection Setup NOT opened
    assert window._project_settings_dialog is not None  # Project Settings opened instead
    assert fetches == []
    assert window.coherence_panel.tree.topLevelItemCount() == 0


def test_run_db_check_fetch_error_shows_status(qtbot):
    window = _window_with_project(qtbot)

    def _boom(params):
        raise RuntimeError("no route to host")

    window._db_ui.fetch_schema = _boom
    window._db_ui.run_check()  # must not crash
    assert window.coherence_panel.tree.topLevelItemCount() == 0
    # The fetch error routes to on_error -> a status message, no crash.
    assert "no route to host" in window.statusBar().currentMessage()


def test_run_db_check_shows_busy_status_then_populates_on_result(qtbot):
    """With a deferred runner, run_check sets the 'Checking…' busy status and
    leaves the panel empty until the schema is delivered; delivering it (on the
    GUI thread) populates the panel and reveals the tab."""
    window = _window_with_project(qtbot)
    captured = {}

    def deferred(fn, on_result, on_error=None, _c=captured):
        _c["fn"] = fn
        _c["on_result"] = on_result

    window._run_async = deferred
    window._db_ui.run_check()

    assert "Checking database" in window.statusBar().currentMessage()
    assert window.coherence_panel.tree.topLevelItemCount() == 0
    assert not window.left_tabs.isTabVisible(window.coherence_tab_index)

    # Deliver the schema back on the GUI thread.
    captured["on_result"](captured["fn"]())
    assert window.coherence_panel.tree.topLevelItemCount() == 2
    assert window.left_tabs.isTabVisible(window.coherence_tab_index)
    assert window._db_ui.toggle_action.isChecked() is True


def test_on_db_rename_requested_updates_buffer_marks_dirty_and_reruns(qtbot):
    window = _window_with_project(qtbot)
    window._db_ui.run_check()
    window._set_dirty(False)

    window._db_ui.prompt_rename = lambda old: "pr.renamed"

    calls = []
    original = window._db_ui.run_check
    window._db_ui.run_check = lambda: calls.append(1) or original()

    window._db_ui.on_rename_requested("table", "pr.a")

    assert 'tableName="pr.renamed"' in window.center_stage.xml_editor.toPlainText()
    assert 'tableName="pr.a"' not in window.center_stage.xml_editor.toPlainText()
    assert window._dirty is True
    assert calls == [1]  # re-ran the coherence check


def test_on_db_rename_requested_cancelled_prompt_no_change(qtbot):
    window = _window_with_project(qtbot)
    window._db_ui.prompt_rename = lambda old: None
    before = window.center_stage.xml_editor.toPlainText()
    window._db_ui.on_rename_requested("table", "pr.a")
    assert window.center_stage.xml_editor.toPlainText() == before


def _drain_find_all(window):
    """Synchronously exhaust the streaming Find-all timer (mirrors the pattern in
    test_main_window): stop the 0ms QTimer and step until the summary lands."""
    if window._find_ui.find_all_timer is not None:
        window._find_ui.find_all_timer.stop()
    for _ in range(10):
        if window._find_ui.find_all_iter is None:
            break
        window._find_ui._find_all_step()


def test_on_db_jump_requested_lists_all_and_selects_first(qtbot):
    window = _window_with_project(qtbot)
    bar = window.center_stage.find_replace_bar
    editor = window.center_stage.xml_editor

    window._db_ui.on_jump_requested("column", "id")

    # Raw tab active; Find bar seeded with the fieldName token so F3 can step.
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index
    assert bar._find_field.text() == 'fieldName="id"'
    # First occurrence selected in the editor.
    assert editor.textCursor().selectedText() == 'fieldName="id"'
    # Find-all streaming started for the same token; results land in the panel.
    assert window._find_ui.find_all_term == 'fieldName="id"'
    _drain_find_all(window)
    find_rows = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any(t.startswith("[Find] ") and 'fieldName="id"' in t for t in find_rows)


def test_on_db_jump_requested_table_token(qtbot):
    window = _window_with_project(qtbot)
    editor = window.center_stage.xml_editor
    window._db_ui.on_jump_requested("table", "pr.a")
    assert window.center_stage.find_replace_bar._find_field.text() == 'tableName="pr.a"'
    assert editor.textCursor().selectedText() == 'tableName="pr.a"'


def test_on_db_jump_requested_missing_token_shows_status(qtbot):
    window = _window_with_project(qtbot)
    window._db_ui.on_jump_requested("table", "pr.absent")
    # BUG-032 facet A: the miss names the token searched and what a miss means
    # (the XML references the relation nowhere) instead of a bare "not found".
    message = window.statusBar().currentMessage()
    assert 'No tableName="pr.absent" in the buffer' in message
    assert "the XML does not reference pr.absent" in message


def test_on_db_jump_requested_accepts_the_internal_relation_kind(qtbot):
    """Hardening for BUG-032 facet A: CoherencePanel normalizes "relation" ->
    "table" at the emit site, but the slot must build the tableName= token for
    the internal spelling too, so a future caller cannot silently reintroduce a
    fieldName= search for a table name."""
    window = _window_with_project(qtbot)
    editor = window.center_stage.xml_editor
    window._db_ui.on_jump_requested("relation", "pr.a")
    assert window.center_stage.find_replace_bar._find_field.text() == 'tableName="pr.a"'
    assert editor.textCursor().selectedText() == 'tableName="pr.a"'


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

    window._db_ui.on_jump_requested("table", "pr.a")
    # First occurrence selected (line 3).
    first = editor.textCursor().selectionStart()

    window._find_ui.find_next()  # F3
    second = editor.textCursor().selectionStart()
    assert second > first
    assert editor.textCursor().selectedText() == 'tableName="pr.a"'

    window._find_ui.find_next()  # F3 -> third
    third = editor.textCursor().selectionStart()
    assert third > second

    window._find_ui.find_next()  # F3 -> wraps back to first
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

    window._db_ui.on_jump_requested("column", "dup")

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

    window._find_ui.find_next()  # F3 -> 2nd
    second = editor.textCursor().selectionStart()
    assert second > first
    window._find_ui.find_next()  # F3 -> 3rd
    third = editor.textCursor().selectionStart()
    assert third > second
    window._find_ui.find_next()  # F3 -> wraps to 1st
    assert editor.textCursor().selectionStart() == first


def test_f3_single_occurrence_wraps_to_itself(qtbot):
    """A token appearing exactly once: F3 re-selects the same single occurrence
    (wrap lands back on itself), never losing the selection."""
    window = _window_with_project(qtbot)
    editor = window.center_stage.xml_editor

    window._db_ui.on_jump_requested("column", "id")  # fieldName="id" occurs once
    start = editor.textCursor().selectionStart()
    assert editor.textCursor().selectedText() == 'fieldName="id"'

    window._find_ui.find_next()  # F3 -> wraps back to the same match
    assert editor.textCursor().selectionStart() == start
    assert editor.textCursor().selectedText() == 'fieldName="id"'


def test_second_db_jump_does_not_accumulate_find_rows(qtbot):
    """A second double-click re-runs Find All, which clears prior [Find] rows so
    results don't pile up across double-clicks."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_MULTI_XML)  # 3x tableName="pr.a"

    window._db_ui.on_jump_requested("table", "pr.a")
    _drain_find_all(window)
    first_count = sum(
        window.audit_panel.item(i).text().startswith("[Find] ")
        for i in range(window.audit_panel.count())
    )

    window._db_ui.on_jump_requested("table", "pr.a")
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

    window._db_ui.on_jump_requested("table", "pr.absent")

    assert 'No tableName="pr.absent" in the buffer' in window.statusBar().currentMessage()
    assert bar._find_field.text() == "SENTINEL"  # untouched
    assert editor.textCursor().selectedText() == pre_sel  # untouched
    assert window._find_ui.find_all_term != 'tableName="pr.absent"'


def test_db_jump_reveals_hidden_audit_dock(qtbot):
    """If a prior action left the Audit dock hidden, a DB double-click reveals it
    so the listed occurrences are visible."""
    window = _window_with_project(qtbot)
    window.audit_dock.setVisible(False)
    assert window.audit_dock.isHidden()

    window._db_ui.on_jump_requested("column", "id")

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
    window._db_ui.fetch_schema = lambda params: schema

    window._db_ui.run_check()
    assert window.coherence_panel.result.flagged_count >= 1  # old_col not found

    # Rename old_col -> new_col (rewrites the buffer + re-runs the check).
    window._db_ui.prompt_rename = lambda old: "new_col"
    window._db_ui.on_rename_requested("column", "old_col")

    assert 'fieldName="new_col"' in window.center_stage.xml_editor.toPlainText()
    assert window.coherence_panel.result.flagged_count == 0  # resolved from the buffer


def _run_initial_check(window):
    """Do one real (patched-fetch) run so the cache + panel are populated
    and the tab is revealed."""
    window._db_ui.run_check()


def test_run_db_check_captures_summary(qtbot):
    window = _window_with_project(qtbot)
    _run_initial_check(window)
    assert window._db_ui.last_schema is not None
    assert window._db_ui.last_summary == "u@h:5432/d"


def test_reparse_refreshes_open_db_check_with_cached_schema(qtbot):
    window = _window_with_project(qtbot)
    fetches = []
    base_fetch = window._db_ui.fetch_schema
    window._db_ui.fetch_schema = lambda params: (fetches.append(1), base_fetch(params))[1]
    _run_initial_check(window)
    assert fetches == [1]                      # one fetch for the initial check

    # Edit the buffer (add a column that IS in the schema was already; instead
    # remove the page's only column reference to change the mismatch set), then
    # spy on set_result so we see only the reparse-driven repopulate.
    calls = []
    real_set = window.coherence_panel.set_result
    window.coherence_panel.set_result = lambda *a: (calls.append(a), real_set(*a))[1]

    edited = _RAW_XML.replace('fieldName="id"', 'fieldName="nonexistent"')
    window.center_stage.xml_editor.setPlainText(edited)

    window._reparse_raw_xml()

    assert fetches == [1]                       # NO re-query — cached schema reused
    assert len(calls) == 1                       # panel repopulated once by reparse
    tree, summary = calls[0]
    assert summary == "u@h:5432/d"
    # The tree reflects the EDITED buffer against the cached schema:
    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.db.coherence import build_coherence_tree
    proj = load_project_from_text(edited, source_description="<editor>")
    expected = build_coherence_tree(proj, window._db_ui.last_schema)
    assert _shape(tree) == _shape(expected)


def test_reparse_no_refresh_when_db_tab_hidden(qtbot):
    window = _window_with_project(qtbot)
    _run_initial_check(window)
    window.left_tabs.setTabVisible(window.coherence_tab_index, False)
    calls = []
    window.coherence_panel.set_result = lambda *a: calls.append(a)
    window._reparse_raw_xml()
    assert calls == []


def test_reparse_no_refresh_without_prior_check(qtbot):
    window = _window_with_project(qtbot)
    # no check run: cache empty, tab hidden by default
    calls = []
    window.coherence_panel.set_result = lambda *a: calls.append(a)
    window._reparse_raw_xml()
    assert calls == []


def test_reparse_refresh_covers_both_branches(qtbot):
    """The refresh rebuilds the WHOLE merged tree — the DB-sourced Tables and
    Views branch and the XML-sourced Pages branch — from the cached schema.
    Successor to the direction-specific refresh test: there is one tree now, so
    the assertion is that both branches come back, not which direction ran."""
    window = _window_with_project(qtbot)
    _run_initial_check(window)

    calls = []
    real_set = window.coherence_panel.set_result
    window.coherence_panel.set_result = lambda *a: (calls.append(a), real_set(*a))[1]

    edited = _RAW_XML.replace('fieldName="id"', 'fieldName="renamed"')
    window.center_stage.xml_editor.setPlainText(edited)
    window._reparse_raw_xml()

    assert len(calls) == 1
    tree, _summary = calls[0]
    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.db.coherence import build_coherence_tree
    proj = load_project_from_text(edited, source_description="<editor>")
    assert _shape(tree) == _shape(build_coherence_tree(proj, window._db_ui.last_schema))
    assert tree.tables_and_views.children  # DB-sourced branch present
    assert tree.pages.children             # XML-sourced branch present


def test_reparse_edit_resolving_mismatch_shows_fewer_problems(qtbot):
    """A reparse whose edit fixes a not-found column drops the mismatch count
    relative to the pre-edit refresh (cached schema, no re-query)."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_RENAME_XML)  # references old_col
    window._run_async = _sync_run
    schema = DatabaseSchema(tables={
        "pr.a": TableInfo(
            name="pr.a", kind="table",
            columns=[ColumnInfo("new_col", "integer", False, False, True, None)],
        )
    })
    window._db_ui.fetch_schema = lambda params: schema
    window._db_ui.run_check()
    before = window.coherence_panel.result.flagged_count
    assert before >= 1  # old_col not found

    # Fix the buffer: old_col -> new_col, then reparse (refresh uses cache).
    edited = _RENAME_XML.replace('fieldName="old_col"', 'fieldName="new_col"')
    window.center_stage.xml_editor.setPlainText(edited)
    window._reparse_raw_xml()

    assert window.coherence_panel.result.flagged_count < before
    assert window.coherence_panel.result.flagged_count == 0


def test_reparse_refresh_does_not_mutate_cache(qtbot):
    """The refresh reuses the cached schema/summary; it must never overwrite the
    cache (that only happens on a fresh run_check)."""
    window = _window_with_project(qtbot)
    _run_initial_check(window)
    cached_schema = window._db_ui.last_schema
    cached_summary = window._db_ui.last_summary

    edited = _RAW_XML.replace('fieldName="id"', 'fieldName="nonexistent"')
    window.center_stage.xml_editor.setPlainText(edited)
    window._reparse_raw_xml()

    assert window._db_ui.last_schema is cached_schema      # same object, not re-fetched
    assert window._db_ui.last_summary == cached_summary


def test_reparse_refresh_passes_cached_summary_to_panel(qtbot):
    """The panel is repopulated with the cached summary line, verbatim."""
    window = _window_with_project(qtbot)
    _run_initial_check(window)
    window._db_ui.last_summary = "custom@snapshot:1/db"  # simulate a prior snapshot

    calls = []
    real_set = window.coherence_panel.set_result
    window.coherence_panel.set_result = lambda *a: (calls.append(a), real_set(*a))[1]
    window._reparse_raw_xml()

    assert len(calls) == 1
    assert calls[0][1] == "custom@snapshot:1/db"


def test_reparse_invalid_buffer_leaves_panel_untouched(qtbot, monkeypatch):
    """An unparseable buffer: the tree reparse surfaces its own error and the
    DB-check refresh is skipped -- panel keeps its previous contents, no crash."""
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    window = _window_with_project(qtbot)
    _run_initial_check(window)
    populated = window.coherence_panel.tree.topLevelItemCount()
    assert populated == 2

    calls = []
    window.coherence_panel.set_result = lambda *a: calls.append(a)
    window.center_stage.xml_editor.setPlainText("<Project><broken")
    window._reparse_raw_xml()  # must not raise

    assert calls == []  # refresh skipped
    assert window.coherence_panel.tree.topLevelItemCount() == populated  # untouched
