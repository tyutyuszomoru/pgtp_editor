import pytest
from PySide6.QtCore import Qt

from pgtp_editor.ui.main_window import MainWindow


def test_window_title(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "PGTP Editor"


def test_default_size(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.size().width() == 1400
    assert window.size().height() == 900


def test_tree_dock_on_left(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.dockWidgetArea(window.tree_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.tree_dock.windowTitle() == "Project Tree"


def test_audit_dock_on_bottom(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.dockWidgetArea(window.audit_dock) == Qt.DockWidgetArea.BottomDockWidgetArea
    # FQ-028 retired the "Audit / Problems" title: the dock now HOLDS the two
    # surfaces that replaced it, and keeps the objectName so saved layouts do.
    assert window.audit_dock.windowTitle() == "Activity Log / Messages"
    assert window.audit_dock.objectName() == "audit_dock"


def test_properties_dock_on_right(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.dockWidgetArea(window.properties_dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert window.properties_dock.windowTitle() == "Properties"


def test_center_stage_sits_below_the_editor_menu_bar_in_the_central_widget(qtbot):
    """FQ-016 deliberately broke the old `centralWidget() is center_stage`
    coupling: the central widget is now a container holding the Editor menu bar
    ABOVE the stage (a QMainWindow's own menu/toolbar areas span the docks too,
    so a bar strictly above the central pane cannot use them). What every other
    caller depends on -- `window.center_stage` being the `CenterStage` -- is
    unchanged."""
    window = MainWindow()
    qtbot.addWidget(window)
    container = window.centralWidget()
    assert container is not window.center_stage
    assert window.center_stage.parent() is container
    layout = container.layout()
    assert layout.itemAt(0).widget() is window.editor_menu_bar
    assert layout.itemAt(1).widget() is window.center_stage


def test_not_implemented_shows_status_message(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._not_implemented("Delete Page")
    assert window.statusBar().currentMessage() == "Not yet implemented: Delete Page"


from pgtp_editor.ui.properties_panel import PropertiesPanel


def test_properties_panel_is_a_real_properties_panel(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert isinstance(window.properties_panel, PropertiesPanel)
    assert window.properties_dock.widget() is window.properties_panel


def test_selecting_tree_item_populates_properties_panel(qtbot):
    from tests.ui._sample_project import build_sample_project

    window = MainWindow()
    qtbot.addWidget(window)
    window.project_tree.populate_from_project(build_sample_project())

    page_item = window.project_tree.topLevelItem(0)
    window.project_tree.setCurrentItem(page_item)

    assert window.properties_panel.is_showing_empty_state() is False
    assert window.properties_panel.header_text().startswith("Page:")


def test_clearing_tree_selection_returns_properties_panel_to_empty_state(qtbot):
    from tests.ui._sample_project import build_sample_project

    window = MainWindow()
    qtbot.addWidget(window)
    window.project_tree.populate_from_project(build_sample_project())
    window.project_tree.setCurrentItem(window.project_tree.topLevelItem(0))
    window.project_tree.setCurrentItem(None)

    assert window.properties_panel.is_showing_empty_state() is True


_CLICK_SYNC_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="equipment" tableName="pr.equipment" caption="Equipment">
        <ColumnPresentations>
          <ColumnPresentation fieldName="tag" caption="Tag"/>
        </ColumnPresentations>
        <Details>
          <Detail caption="Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item">
              <ColumnPresentations>
                <ColumnPresentation fieldName="cvalue" caption="Value"/>
              </ColumnPresentations>
            </Page>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def _load_click_sync_window(qtbot):
    import textwrap

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    project = load_project_from_text(textwrap.dedent(_CLICK_SYNC_PGTP))
    window._current_project = project
    window.project_tree.populate_from_project(project)
    return window, project


def test_editor_click_selects_enclosing_node_and_updates_properties(qtbot):
    window, project = _load_click_sync_window(qtbot)
    detail = project.pages[0].details[0]

    # A click on the outer <Detail> open line resolves to that Detail.
    window._on_editor_line_clicked(detail.sourceline)

    current = window.project_tree.currentItem()
    from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE

    assert current is not None
    assert current.data(0, MODEL_NODE_ROLE) is detail
    # Tree->Properties fired automatically through existing wiring.
    assert window.properties_panel.is_showing_empty_state() is False
    assert window.properties_panel.header_text().startswith("Detail:")


def test_editor_click_on_column_line_selects_column(qtbot):
    window, project = _load_click_sync_window(qtbot)
    column = project.pages[0].columns[0]
    window._on_editor_line_clicked(column.sourceline)

    from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE

    assert window.project_tree.currentItem().data(0, MODEL_NODE_ROLE) is column


def test_editor_click_above_first_page_is_noop(qtbot):
    window, project = _load_click_sync_window(qtbot)
    window.project_tree.setCurrentItem(window.project_tree.topLevelItem(0))
    before = window.project_tree.currentItem()

    window._on_editor_line_clicked(1)  # line 1 is the <?xml ...?> header
    assert window.project_tree.currentItem() is before


def test_editor_click_with_no_current_project_is_noop(qtbot):
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    assert window._current_project is None
    # Must not raise even with no project loaded.
    window._on_editor_line_clicked(5)


def test_line_clicked_signal_is_connected_to_handler(qtbot):
    window, project = _load_click_sync_window(qtbot)
    detail = project.pages[0].details[0]
    # Emitting the editor's signal drives the same end-to-end selection.
    window.center_stage.xml_editor.line_clicked.emit(detail.sourceline)

    from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE

    assert window.project_tree.currentItem().data(0, MODEL_NODE_ROLE) is detail


_REPARSE_ONE_PAGE = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="equipment" tableName="pr.equipment" caption="Equipment"/>
    </Pages>
  </Presentation>
</Project>
"""

_REPARSE_TWO_PAGES = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="equipment" tableName="pr.equipment" caption="Equipment"/>
      <Page fileName="work_orders" tableName="pr.x_workorder" caption="Work Orders"/>
    </Pages>
  </Presentation>
</Project>
"""


def _reparse_menu_action(window):
    from tests.ui._menu_helpers import find_action, find_top_menu

    menu = find_top_menu(window, "Tools")
    return find_action(menu, "Reparse Raw XML into Tree")


def test_reparse_action_exists_and_is_not_a_stub(qtbot):
    from unittest.mock import patch

    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    action = _reparse_menu_action(window)
    assert action is not None
    # A stub action would set the "Not yet implemented" status message.
    # The editor is empty here, so reparse takes the failure path, which shows
    # a modal QMessageBox.critical -- patch it, or the modal event loop blocks
    # the headless test run forever.
    with patch("pgtp_editor.ui.modals.QMessageBox.critical"):
        action.trigger()
    assert window.statusBar().currentMessage() != "Not yet implemented: Reparse Raw XML into Tree"


def test_reparse_success_rebuilds_tree_and_adopts_new_model(qtbot):
    import textwrap

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    # Start with a one-page model loaded.
    project = load_project_from_text(textwrap.dedent(_REPARSE_ONE_PAGE))
    window._current_project = project
    window.project_tree.populate_from_project(project)
    assert window.project_tree.topLevelItemCount() == 1

    # User edits the editor to a two-page document, then reparses.
    window.center_stage.xml_editor.setPlainText(textwrap.dedent(_REPARSE_TWO_PAGES))
    window._doc_ui.reparse()

    assert window.project_tree.topLevelItemCount() == 2
    assert window._current_project is not project
    assert len(window._current_project.pages) == 2
    # Properties reset to empty after the rebuild cleared the selection.
    assert window.properties_panel.is_showing_empty_state() is True


def test_reparse_failure_preserves_model_and_tree_and_highlights_line(qtbot, monkeypatch):
    import textwrap

    from PySide6.QtWidgets import QMessageBox

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    project = load_project_from_text(textwrap.dedent(_REPARSE_ONE_PAGE))
    window._current_project = project
    window.project_tree.populate_from_project(project)
    items_before = window.project_tree.topLevelItemCount()

    # Suppress the real modal dialog and record that it was shown.
    critical_calls = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: critical_calls.append(args)
    )
    # Spy on the editor's error-line highlight.
    highlighted = []
    monkeypatch.setattr(
        window.center_stage.xml_editor,
        "highlight_error_line",
        lambda line: highlighted.append(line),
    )

    window.center_stage.xml_editor.setPlainText(
        "<Project><Presentation><Pages><Page></Pages></Presentation></Project>"
    )
    window._doc_ui.reparse()

    assert critical_calls, "expected QMessageBox.critical to be shown"
    assert highlighted, "expected highlight_error_line to be called for the error line"
    # Last-good state survived: same model object, same tree contents.
    assert window._current_project is project
    assert window.project_tree.topLevelItemCount() == items_before


def test_reparse_failure_without_line_number_still_shows_dialog(qtbot, monkeypatch):
    import textwrap

    from PySide6.QtWidgets import QMessageBox

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    project = load_project_from_text(textwrap.dedent(_REPARSE_ONE_PAGE))
    window._current_project = project
    window.project_tree.populate_from_project(project)

    critical_calls = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: critical_calls.append(args)
    )
    highlighted = []
    monkeypatch.setattr(
        window.center_stage.xml_editor,
        "highlight_error_line",
        lambda line: highlighted.append(line),
    )

    # Force a PgtpParseError with line=None by monkeypatching the parser
    # entry point MainWindow calls.
    import pgtp_editor.ui.pgtp_document_controller as doc_module
    from pgtp_editor.model.parser import PgtpParseError

    def _raise_no_line(text, source_description="<editor>"):
        raise PgtpParseError("structural surprise", line=None)

    monkeypatch.setattr(doc_module, "load_project_from_text", _raise_no_line)
    window._doc_ui.reparse()

    assert critical_calls, "dialog still shown when line is unknown"
    assert highlighted == []  # no line to highlight
    assert window._current_project is project  # state preserved


def test_reparse_realigns_click_sync_after_line_shift(qtbot):
    import textwrap

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow
    from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE

    window = MainWindow()
    qtbot.addWidget(window)
    project = load_project_from_text(textwrap.dedent(_REPARSE_ONE_PAGE))
    window._current_project = project
    window.project_tree.populate_from_project(project)

    # Edit: insert two comment lines *after* the XML declaration so the <Page>
    # shifts down by 2 while the document stays valid (comments before the
    # <?xml?> declaration would make it malformed, so the reparse would fail
    # and this test's realign intent would never actually be exercised).
    one_page_lines = textwrap.dedent(_REPARSE_ONE_PAGE).split("\n")
    shifted = one_page_lines[0] + "\n<!-- a -->\n<!-- b -->\n" + "\n".join(one_page_lines[1:])
    window.center_stage.xml_editor.setPlainText(shifted)
    window._doc_ui.reparse()

    new_page = window._current_project.pages[0]
    # Clicking the page's (now-shifted) line resolves to the rebuilt node.
    window._on_editor_line_clicked(new_page.sourceline)
    assert window.project_tree.currentItem().data(0, MODEL_NODE_ROLE) is new_page


from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor


def test_find_all_populates_audit_panel_with_line_items_and_summary(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("first page\nsecond line\nthird page here")
    window._find_ui.find_all("page")
    qtbot.waitUntil(lambda: not window.center_stage.find_replace_bar._find_all_running, timeout=5000)

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert texts == [
        "[Find] line 1: first page",
        "[Find] line 3: third page here",
        '[Find] 2 match(es) for "page"',
    ]
    # Line data stored on result items, None on the summary line.
    assert window.audit_panel.item(0).data(Qt.ItemDataRole.UserRole) == 1
    assert window.audit_panel.item(1).data(Qt.ItemDataRole.UserRole) == 3
    assert window.audit_panel.item(2).data(Qt.ItemDataRole.UserRole) is None


def test_find_all_clears_only_prior_find_entries(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    # FQ-028: `[Schema]` learning chatter is journalled, not listed, so the
    # "survives a Find rerun" seed is a Results row -- which is the surface a
    # Find rerun must not touch.
    window.audit_panel.addItem("[Check] seeded entry")
    window.center_stage.xml_editor.setPlainText("page here")

    window._find_ui.find_all("page")
    window._find_ui.find_all("page")  # run again
    qtbot.waitUntil(lambda: not window.center_stage.find_replace_bar._find_all_running, timeout=5000)

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    # The seeded [Schema] entry survives exactly once; only ONE generation of
    # [Find] entries is present (result line + summary).
    assert texts.count("[Check] seeded entry") == 1
    assert texts == [
        "[Check] seeded entry",
        "[Find] line 1: page here",
        '[Find] 1 match(es) for "page"',
    ]


def test_clicking_find_result_navigates_editor_to_line(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("a\nb\npage on line 3\nd")
    window._find_ui.find_all("page")
    qtbot.waitUntil(lambda: not window.center_stage.find_replace_bar._find_all_running, timeout=5000)

    result_item = window.audit_panel.item(0)
    assert result_item.data(Qt.ItemDataRole.UserRole) == 3
    window._on_audit_item_clicked(result_item)

    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index
    # navigate_to_line moved the cursor to that block (1-based line 3).
    assert window.center_stage.xml_editor.textCursor().blockNumber() + 1 == 3


def test_clicking_non_find_entry_is_a_noop(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("a\nb\nc")
    # Put the cursor on line 1 and record it.
    window.center_stage.xml_editor.moveCursor(QTextCursor.MoveOperation.Start)
    before = window.center_stage.xml_editor.textCursor().blockNumber()

    window.audit_panel.addItem("[Check] not clickable to navigate")
    schema_item = window.audit_panel.item(window.audit_panel.count() - 1)
    window._on_audit_item_clicked(schema_item)  # no line data -> no-op

    after = window.center_stage.xml_editor.textCursor().blockNumber()
    assert after == before


def test_clicking_summary_line_is_a_noop(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("page\npage")
    window._find_ui.find_all("page")
    qtbot.waitUntil(lambda: not window.center_stage.find_replace_bar._find_all_running, timeout=5000)
    window.center_stage.xml_editor.moveCursor(QTextCursor.MoveOperation.Start)
    before = window.center_stage.xml_editor.textCursor().blockNumber()

    summary_item = window.audit_panel.item(window.audit_panel.count() - 1)
    assert summary_item.data(Qt.ItemDataRole.UserRole) is None
    window._on_audit_item_clicked(summary_item)

    after = window.center_stage.xml_editor.textCursor().blockNumber()
    assert after == before


def test_find_all_via_the_bars_button_populates_audit_panel(qtbot):
    """FQ-016: the bar's BUTTON is the only way to start a Find All -- the
    Edit-menu entry and its Ctrl+Shift+F are both deleted."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("alpha page beta")
    window.center_stage.find_replace_bar._find_field.setText("page")
    window.center_stage.find_replace_bar._find_all_button.click()
    qtbot.waitUntil(lambda: not window.center_stage.find_replace_bar._find_all_running, timeout=5000)

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert "[Find] line 1: alpha page beta" in texts
    assert '[Find] 1 match(es) for "page"' in texts


def test_replace_all_via_the_bars_button_mutates_document(qtbot):
    """Ctrl+Alt+Return is deleted too (§27): Replace All is a bulk edit and
    stays button-only."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("page page page")
    bar = window.center_stage.find_replace_bar
    bar._find_field.setText("page")
    bar._replace_field.setText("X")

    bar._replace_all_button.click()
    assert window.center_stage.xml_editor.toPlainText() == "X X X"


def test_find_all_streaming_completes_and_reports_final_count(qtbot):
    from PySide6.QtCore import Qt as _Qt
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("page one\nsecond\nthird page here")
    bar = window.center_stage.find_replace_bar

    window._find_ui.find_all("page")
    qtbot.waitUntil(lambda: not bar._find_all_running, timeout=5000)

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert texts == [
        "[Find] line 1: page one",
        "[Find] line 3: third page here",
        '[Find] 2 match(es) for "page"',
    ]
    assert window.audit_panel.item(0).data(_Qt.ItemDataRole.UserRole) == 1
    assert window.statusBar().currentMessage() == "Found 2 item(s)"
    assert bar._find_all_button.text() == "Find All"


def test_find_all_stop_keeps_partial_results(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    # Many matches so a single batch is a strict subset of the total.
    window.center_stage.xml_editor.setPlainText("\n".join(f"a{i}" for i in range(500)))
    bar = window.center_stage.find_replace_bar

    window._find_ui.find_all("a")
    # Take manual control of stepping so the test is deterministic (no timing).
    window._find_ui.find_all_timer.stop()
    window._find_ui._find_all_step()          # process exactly one batch
    partial = window._find_ui.find_all_count
    assert 0 < partial < 500
    results_before_summary = window.audit_panel.count()

    window._find_ui.stop_find_all()
    window._find_ui._find_all_step()          # observes the stop flag -> finishes

    assert bar._find_all_running is False
    assert bar._find_all_button.text() == "Find All"
    # Partial results kept; exactly one summary line appended after them.
    assert window.audit_panel.count() == results_before_summary + 1
    summary = window.audit_panel.item(window.audit_panel.count() - 1).text()
    assert summary == f'[Find] {partial} match(es) for "a"'
    assert window.statusBar().currentMessage() == f"Find All stopped — found {partial} item(s)"


def test_find_all_live_count_status_after_a_batch(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("\n".join(f"a{i}" for i in range(500)))

    window._find_ui.find_all("a")
    window._find_ui.find_all_timer.stop()
    window._find_ui._find_all_step()
    msg = window.statusBar().currentMessage()
    assert msg.startswith('Finding "a"… found ')


def test_find_all_restart_does_not_leak_a_second_timer(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("page page")
    bar = window.center_stage.find_replace_bar

    window._find_ui.find_all("page")
    first_timer = window._find_ui.find_all_timer
    window._find_ui.find_all("page")  # re-trigger while (nominally) active
    # The previous timer was stopped/dropped; a fresh one is in place.
    assert window._find_ui.find_all_timer is not first_timer
    assert not first_timer.isActive()
    qtbot.waitUntil(lambda: not bar._find_all_running, timeout=5000)


def test_find_all_state_properties_expose_the_live_iteration_objects(qtbot):
    """The streaming Find All is driven BY HAND above (stop the timer, step once,
    read the partial count), so `FindValidateController`'s state properties must
    hand back the very objects the controller will next act on -- not copies,
    snapshots or recomputed values. A property that returned a copy would leave
    those tests green while testing nothing."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("\n".join(f"a{i}" for i in range(500)))
    find_ui = window._find_ui

    find_ui.find_all("a")
    # The property IS the attribute every write in the controller lands on.
    assert find_ui.find_all_timer is find_ui._find_all_timer
    assert find_ui.find_all_iter is find_ui._find_all_iter

    # Stopping through the property stops the timer the controller owns.
    find_ui.find_all_timer.stop()
    assert not find_ui._find_all_timer.isActive()

    # Stepping by hand advances the very iterator the property exposed.
    iterator = find_ui.find_all_iter
    find_ui._find_all_step()
    assert find_ui.find_all_iter is iterator
    assert find_ui.find_all_count > 0
    assert find_ui.find_all_term == "a"
    assert find_ui.find_all_target == "raw"

    find_ui.stop_find_all()
    find_ui._find_all_step()
    # The finish path cleared both, through the same attributes.
    assert find_ui.find_all_timer is None
    assert find_ui.find_all_iter is None


def test_manage_captions_requires_non_empty_raw_xml(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    # No project / empty editor -> info message, no mode switch.
    window.center_stage.xml_editor.setPlainText("")
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()
    assert window.center_stage.isTabVisible(
        window.center_stage.caption_management_tab_index
    ) is False
    assert "Manage Captions" in window.statusBar().currentMessage()


def test_manage_captions_enters_mode_and_populates_grid(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()

    stage = window.center_stage
    # Phase 1: Raw XML stays visible but read-only in Caption Mode.
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.xml_editor.isReadOnly() is True
    assert stage.isTabVisible(stage.caption_management_tab_index) is True
    assert stage.currentIndex() == stage.caption_management_tab_index
    assert stage.caption_management_panel._model.rowCount() == 1
    # Value is now column 6 (read-only); New Value is column 7.
    assert stage.caption_management_panel._model.index(0, 6).data() == "Home"


def test_manage_captions_apply_writes_into_editor_buffer_and_reports_count(qtbot):
    from PySide6.QtCore import Qt
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()

    panel = window.center_stage.caption_management_panel
    # Edit the New Value column (7); Value column (6) is read-only.
    panel._model.setData(panel._model.index(0, 7), "Homepage", Qt.ItemDataRole.EditRole)
    panel.apply()

    assert window.center_stage.xml_editor.toPlainText() == (
        '<Root>\n  <Page caption="Homepage" fileName="home"/>\n</Root>'
    )
    assert "1" in window.statusBar().currentMessage()


def test_manage_captions_apply_with_no_edits_reports_zero(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()

    panel = window.center_stage.caption_management_panel
    panel.apply()
    assert window.center_stage.xml_editor.toPlainText() == (
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )
    assert "0" in window.statusBar().currentMessage()


def test_manage_captions_close_restores_raw_xml(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()
    window.center_stage.caption_management_panel.close_panel()

    stage = window.center_stage
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.isTabVisible(stage.caption_management_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index


def test_manage_captions_apply_then_reedit_uses_updated_snapshot(qtbot):
    from PySide6.QtCore import Qt
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()
    panel = window.center_stage.caption_management_panel

    panel._model.setData(panel._model.index(0, 7), "Homepage", Qt.ItemDataRole.EditRole)
    panel.apply()  # editor now has caption="Homepage"; snapshot updated

    # A second edit applies cleanly on the updated snapshot (line still valid).
    panel._model.setData(panel._model.index(0, 7), "Landing", Qt.ItemDataRole.EditRole)
    panel.apply()
    assert window.center_stage.xml_editor.toPlainText() == (
        '<Root>\n  <Page caption="Landing"/>\n</Root>'
    )


# --- Phase 1: mode indicator + read-only hint -----------------------------

def test_mode_label_states_the_major_mode_before_any_launcher_pick(qtbot):
    """FQ-028: the label is never blank. With no launcher column picked there is
    still a defined fact to state, and "Editing" was never a mode -- it is the
    absence of a minor one."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._mode_label.text() == "No Mode"
    assert window.toolbar_mode_indicator.text() == "No Mode"


def test_mode_label_flips_on_enter_and_close_caption_mode(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )
    window.set_workflow_mode("project")
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()
    # Major mode keeps the colour; the minor mode is appended as text, on BOTH
    # surfaces, from the one `current_mode()` answer.
    assert window._mode_label.text() == "Project · Caption"
    assert window.toolbar_mode_indicator.text() == "Project · Caption"
    assert window.current_mode() == ("project", "Caption")

    window.center_stage.caption_management_panel.close_panel()
    assert window._mode_label.text() == "Project"
    assert window.toolbar_mode_indicator.text() == "Project"


def test_caption_go_to_line_switches_to_raw_xml_and_navigates(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home"/>\n  <Page caption="Other"/>\n</Root>'
    )
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()

    calls = []
    window.center_stage.xml_editor.navigate_to_line = lambda line: calls.append(line)
    # Row 1 is on source line 3; go_to_line via the panel callback.
    window.center_stage.caption_management_panel.on_go_to_line(3)

    stage = window.center_stage
    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert calls == [3]


def test_readonly_edit_attempt_flashes_status_hint(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.read_only_edit_attempted.emit()
    assert "read-only" in window.statusBar().currentMessage()


# -- FQ-017: caption find/filter/replace lives ONLY in the permanent bar ----


def _enter_caption_mode_with(window, snapshot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window.center_stage.xml_editor.setPlainText(snapshot)
    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()


def test_the_caption_filter_modal_is_gone_from_the_host(qtbot):
    """FQ-017 deleted `ui/caption_find_replace_dialog.py` and every host-side
    seam that reached it: the Tools entry, the two mode-gated window
    QShortcuts, the factory and the four routing slots."""
    window = MainWindow()
    qtbot.addWidget(window)
    for gone in (
        "_caption_find_replace_dialog",
        "_make_caption_find_replace_dialog",
        "_open_caption_filter_dialog",
        "_open_caption_replace_dialog",
        "_caption_shortcut_open_filter",
        "_caption_shortcut_open_replace",
        "_caption_filter_shortcut",
        "_caption_replace_shortcut",
        "_caption_apply_filter",
        "_caption_replace_all",
    ):
        assert not hasattr(window, gone), gone
    with pytest.raises(ImportError):
        __import__("pgtp_editor.ui.caption_find_replace_dialog")


def test_caption_filter_action_is_gone_from_the_tools_menu(qtbot):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow()
    qtbot.addWidget(window)
    assert find_action(find_top_menu(window, "Tools"), "Caption Filter…") is None
    # The tab that replaced it is still reachable.
    assert find_action(find_top_menu(window, "Tools"), "Manage Captions...") is not None


def test_caption_mode_needs_no_find_replace_gating_any_more(qtbot):
    """FQ-016 deleted the gate rather than re-pointing it. `set_find_actions` /
    `set_find_actions_enabled` existed ONLY so Caption Mode could disable the
    Edit-menu Find…/Replace… QActions and let its own shortcuts win. With the
    Edit menu dissolved, both sides' Ctrl+F/Ctrl+R are focus shortcuts scoped to
    the surface that owns them, so exactly one is ever live -- structurally, not
    by gating."""
    from PySide6.QtGui import QShortcut

    window = MainWindow()
    qtbot.addWidget(window)
    assert not hasattr(window._find_ui, "find_action")
    assert not hasattr(window._find_ui, "set_find_actions")
    assert not hasattr(window._find_ui, "set_find_actions_enabled")
    # No window-parented Ctrl+F / Ctrl+R exists to be ambiguous with the caption
    # panel's own panel-scoped pair.
    window_combos = {
        s.key().toString()
        for s in window.findChildren(QShortcut)
        if s.parent() is window
    }
    assert not {"Ctrl+F", "Ctrl+R"} & window_combos

    _enter_caption_mode_with(window, '<Root>\n  <Page caption="Home"/>\n</Root>')
    panel = window.center_stage.caption_management_panel
    assert panel._focus_find_shortcut.key().toString() == "Ctrl+F"
    assert panel._focus_replace_shortcut.key().toString() == "Ctrl+R"
    window._close_caption_mode()


def test_the_caption_bar_is_visible_as_soon_as_caption_mode_opens(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    _enter_caption_mode_with(
        window,
        '<Root>\n  <Page caption="Home Page"/>\n  <Page caption="Orders Page"/>\n</Root>',
    )
    panel = window.center_stage.caption_management_panel
    bar = panel.find_replace_bar
    assert bar.isHidden() is False
    # And it is the one surface for filtering the grid. (set_find_text, so the
    # live replace does not fire with an empty Replace-with and rewrite rows.)
    bar.set_find_text("Home")
    bar.apply_filter()
    proxy = panel._proxy
    visible = [
        proxy.index(r, 6).data(Qt.ItemDataRole.DisplayRole)
        for r in range(proxy.rowCount())
    ]
    assert visible == ["Home Page"]


def test_the_caption_bar_replace_all_reaches_the_whole_project(qtbot):
    """The one capability the deleted modal was the sole route to, now on the
    bar behind the scope dropdown plus an explicit press."""
    window = MainWindow()
    qtbot.addWidget(window)
    _enter_caption_mode_with(
        window,
        '<Root>\n  <Page caption="Home Page"/>\n  <Page caption="Orders Page"/>\n</Root>',
    )
    panel = window.center_stage.caption_management_panel
    bar = panel.find_replace_bar
    bar.find_field.setText("Home")
    bar.apply_filter()
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    bar.set_scope("project")
    bar.replace_all_button.click()
    assert panel._model.new_value_at(0) == "Home Screen"
    assert panel._model.new_value_at(1) == "Orders Screen"


# ---------------------------------------------------------------------------
# Tier-2 Validate Project wiring
# ---------------------------------------------------------------------------

_DUP_FILENAME_XML = (
    '<Project>\n'
    '  <Presentation>\n'
    '    <Pages>\n'
    '      <Page fileName="dup.php" tableName="t1"/>\n'
    '      <Page fileName="dup.php" tableName="t2"/>\n'
    '    </Pages>\n'
    '  </Presentation>\n'
    '</Project>\n'
)


def _load_into_window(window, xml_text):
    """Attach a text-built project to the window without touching disk/modals."""
    from pgtp_editor.model.parser import load_project_from_text

    project = load_project_from_text(xml_text)
    window._current_project = project
    window.center_stage.xml_editor.setPlainText(xml_text)
    return project


def _validation_items(window):
    from pgtp_editor.ui.find_controller import _VALIDATION_PREFIX

    return [
        window.audit_panel.item(row).text()
        for row in range(window.audit_panel.count())
        if window.audit_panel.item(row).text().startswith(_VALIDATION_PREFIX)
    ]


def test_validate_with_no_project_shows_info_and_empty_audit(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._current_project is None
    window._find_ui.validate_project()
    assert window.statusBar().currentMessage() == "Open a project to validate."
    assert window.audit_panel.count() == 0


def test_validate_duplicate_filename_populates_audit_and_status(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    _load_into_window(window, _DUP_FILENAME_XML)

    window._find_ui.validate_project()

    items = _validation_items(window)
    errors = [t for t in items if "ERROR" in t]
    assert len(errors) == 2
    assert all("dup.php" in t for t in errors)
    # Status summary names the error count.
    assert window.statusBar().currentMessage() == "Validation: 2 error(s), 0 warning(s)"


def test_a_second_validation_run_ACCUMULATES_under_its_own_run_separator(qtbot):
    """FQ-028 reversed this one deliberately.

    `clear_validation_results` used to delete the previous run's rows. Results
    now ACCUMULATE -- saved validation history is exactly what the owner asked
    for -- so the sweep is read as a RUN BOUNDARY: the old rows stay and the new
    run opens under its own dated separator.
    """
    from PySide6.QtWidgets import QListWidgetItem

    window = MainWindow()
    qtbot.addWidget(window)
    window.audit_panel.addItem(QListWidgetItem("[Check] x"))
    _load_into_window(window, _DUP_FILENAME_XML)
    window._find_ui.validate_project()
    first = len(_validation_items(window))
    assert first

    window._find_ui.validate_project()

    assert len(_validation_items(window)) == first * 2
    remaining = [
        window.audit_panel.item(row).text() for row in range(window.audit_panel.count())
    ]
    assert "[Check] x" in remaining
    # ...and the two runs are separated on screen by the dated rule.
    rows = window.results_panel.row_texts()
    assert rows.count("-" * 40) == 3  # the seed's run, then the two validations


def test_clicking_validation_item_navigates_to_line(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    _load_into_window(window, _DUP_FILENAME_XML)
    window._find_ui.validate_project()

    # Find the first validation row and click it.
    from pgtp_editor.ui.find_controller import _VALIDATION_PREFIX

    row = next(
        r
        for r in range(window.audit_panel.count())
        if window.audit_panel.item(r).text().startswith(_VALIDATION_PREFIX)
    )
    item = window.audit_panel.item(row)
    line = item.data(Qt.ItemDataRole.UserRole)
    assert line is not None

    window._on_audit_item_clicked(item)

    # Switched to the Raw XML tab and moved the cursor to the issue line.
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index
    cursor = window.center_stage.xml_editor.textCursor()
    assert cursor.blockNumber() + 1 == line


def test_validate_passes_on_clean_project(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    clean = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="a.php" tableName="t_a"/>\n'
        '      <Page fileName="b.php" tableName="t_b"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    _load_into_window(window, clean)
    window._find_ui.validate_project()
    assert _validation_items(window) == []
    assert window.statusBar().currentMessage() == "Validation passed — no issues."


def test_find_selected_text_reveals_raw_xml_tab_and_prefills_and_searches(qtbot):
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("<Page>\n  widget\n</Page>\n")

    # Simulate the editor's right-click "Find" emitting the selected text.
    window.center_stage.xml_editor.find_selected_text.emit("widget")

    cs = window.center_stage
    assert cs.currentIndex() == cs.raw_xml_tab_index
    assert cs.find_replace_bar._find_field.text() == "widget"
    # find_next ran: the editor now has the term selected (unambiguous term so
    # the case-insensitive search doesn't match "Page" first).
    assert cs.xml_editor.textCursor().selectedText() == "widget"


# -- Phase C.2: enter caption mode with a preset filter ---------------------

_CAPTION_CONTEXT_XML = (
    "<Root>\n"
    '  <Page caption="Equipment" fileName="equip" tableName="pr.equip">\n'
    "    <Columns>\n"
    '      <ColumnPresentation caption="WBS" fieldName="wbs_id"/>\n'
    "    </Columns>\n"
    '    <Detail caption="Attachments" tableName="pr.att">\n'
    '      <Page fileName="attpage">\n'
    "        <Columns>\n"
    '          <ColumnPresentation caption="Name" fieldName="att_name"/>\n'
    "        </Columns>\n"
    "      </Page>\n"
    "    </Detail>\n"
    "  </Page>\n"
    '  <Page caption="Other" fileName="other" tableName="pr.other"/>\n'
    "</Root>"
)


def _visible_values(panel):
    proxy = panel._proxy
    from pgtp_editor.ui.caption_management_panel import _VALUE_COLUMN

    return [
        proxy.index(r, _VALUE_COLUMN).data(Qt.ItemDataRole.DisplayRole)
        for r in range(proxy.rowCount())
    ]


def test_enter_caption_mode_for_table_filters_grid(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_CAPTION_CONTEXT_XML)

    window.enter_caption_mode_for_table("pr.equip")

    stage = window.center_stage
    assert stage.currentIndex() == stage.caption_management_tab_index
    panel = stage.caption_management_panel
    # Only rows whose owning table is pr.equip: the Equipment page + its WBS
    # column (the Detail is pr.att, the second page is pr.other).
    assert sorted(_visible_values(panel)) == ["Equipment", "WBS"]


def test_enter_caption_mode_for_table_details_filters_to_detail_rows(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_CAPTION_CONTEXT_XML)

    window.enter_caption_mode_for_table_details("pr.att")

    panel = window.center_stage.caption_management_panel
    # Only the in-detail column on pr.att (Name).
    assert _visible_values(panel) == ["Name"]


def test_enter_caption_mode_for_field_selects_row(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_CAPTION_CONTEXT_XML)

    window.enter_caption_mode_for_field("wbs_id")

    panel = window.center_stage.caption_management_panel
    assert _visible_values(panel) == ["WBS"]
    selected = panel._table.selectionModel().selectedRows()
    assert len(selected) == 1
    source_row = panel._proxy.mapToSource(selected[0]).row()
    assert panel._model.entry_at(source_row).field_name == "wbs_id"


# -- Phase D: tree double-click jump + redesigned context menus -------------

_TREE_D_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="equipment" tableName="pr.equipment" caption="Equipment">
        <ColumnPresentations>
          <ColumnPresentation fieldName="tag" caption="Tag"/>
        </ColumnPresentations>
        <Columns>
          <List>
            <Column fieldName="tag" visible="true"/>
          </List>
        </Columns>
        <Details>
          <Detail caption="Sub-item" tableName="pr.attachment">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item">
              <ColumnPresentations>
                <ColumnPresentation fieldName="cvalue" caption="Value"/>
              </ColumnPresentations>
            </Page>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def _load_tree_d_window(qtbot):
    import textwrap

    from pgtp_editor.model.parser import load_project_from_text

    window = MainWindow()
    qtbot.addWidget(window)
    text = textwrap.dedent(_TREE_D_PGTP)
    window.center_stage.xml_editor.setPlainText(text)
    project = load_project_from_text(text)
    window._current_project = project
    window.project_tree.populate_from_project(project)
    return window, project


def test_double_click_jumps_editor_to_node_line(qtbot):
    window, project = _load_tree_d_window(qtbot)
    detail = project.pages[0].details[0]

    page_item = window.project_tree.topLevelItem(0)
    detail_item = page_item.child(0)
    window.project_tree.itemDoubleClicked.emit(detail_item, 0)

    cs = window.center_stage
    assert cs.currentIndex() == cs.raw_xml_tab_index
    # The editor caret is on the outer <Detail> open line.
    line = window.center_stage.xml_editor.textCursor().blockNumber() + 1
    assert line == detail.sourceline


def test_select_page_xml_selects_whole_page_block(qtbot):
    window, project = _load_tree_d_window(qtbot)
    page = project.pages[0]

    window._on_tree_select_xml_block(page)

    editor = window.center_stage.xml_editor
    # Qt uses U+2029 (paragraph separator) for line breaks in selectedText();
    # normalise to real newlines before asserting.
    selected = editor.textCursor().selectedText().replace(chr(0x2029), "\n")
    assert selected.startswith("<Page fileName=\"equipment\"")
    assert selected.rstrip().endswith("</Page>")
    # Whole element captured: the nested Detail is inside the selection.
    assert "<Detail caption=\"Sub-item\"" in selected


def test_select_detail_xml_selects_whole_detail_block(qtbot):
    window, project = _load_tree_d_window(qtbot)
    detail = project.pages[0].details[0]

    window._on_tree_select_xml_block(detail)

    editor = window.center_stage.xml_editor
    selected = editor.textCursor().selectedText().replace(chr(0x2029), "\n")
    assert selected.startswith("<Detail caption=\"Sub-item\"")
    assert selected.rstrip().endswith("</Detail>")


def test_jump_to_column_visibility_lands_on_columns_line(qtbot):
    window, project = _load_tree_d_window(qtbot)
    column = project.pages[0].columns[0]

    window._on_tree_jump_to_column_visibility(column)

    editor = window.center_stage.xml_editor
    landed_line = editor.textCursor().blockNumber() + 1
    assert editor.line_text(landed_line).strip() == "<Columns>"


def test_jump_to_column_presentation_lands_on_column_presentation_line(qtbot):
    window, project = _load_tree_d_window(qtbot)
    column = project.pages[0].columns[0]

    window._on_tree_jump_to_xml(column)

    editor = window.center_stage.xml_editor
    landed_line = editor.textCursor().blockNumber() + 1
    assert landed_line == column.sourceline
    assert "ColumnPresentation" in editor.line_text(landed_line)


def test_see_table_in_caption_enters_filtered_caption_mode(qtbot):
    window, project = _load_tree_d_window(qtbot)
    page = project.pages[0]

    window._on_tree_see_table_in_caption(page)

    stage = window.center_stage
    assert stage.currentIndex() == stage.caption_management_tab_index
    panel = stage.caption_management_panel
    # pr.equipment rows only: the Equipment page caption + its Tag column.
    assert sorted(_visible_values(panel)) == ["Equipment", "Tag"]


def test_see_column_in_caption_filters_and_selects_row(qtbot):
    window, project = _load_tree_d_window(qtbot)
    column = project.pages[0].columns[0]

    window._on_tree_see_column_in_caption(column)

    panel = window.center_stage.caption_management_panel
    assert _visible_values(panel) == ["Tag"]
    selected = panel._table.selectionModel().selectedRows()
    assert len(selected) == 1
    # BUG-020: the preset filter applied from the Browser Pane must be
    # visibly represented via the panel's active-filter banner, not silent.
    assert panel._filter_banner.isVisibleTo(panel)
    assert f"Field = {column.field_name}" in panel._filter_banner_label.text()
