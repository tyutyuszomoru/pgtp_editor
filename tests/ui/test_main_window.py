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
    assert window.audit_dock.windowTitle() == "Audit / Problems"


def test_properties_dock_on_right(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.dockWidgetArea(window.properties_dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert window.properties_dock.windowTitle() == "Properties"


def test_center_stage_is_central_widget(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.centralWidget() is window.center_stage


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
    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
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
    window._reparse_raw_xml()

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
    window._reparse_raw_xml()

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
    import pgtp_editor.ui.main_window as mw
    from pgtp_editor.model.parser import PgtpParseError

    def _raise_no_line(text, source_description="<editor>"):
        raise PgtpParseError("structural surprise", line=None)

    monkeypatch.setattr(mw, "load_project_from_text", _raise_no_line)
    window._reparse_raw_xml()

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
    window._reparse_raw_xml()

    new_page = window._current_project.pages[0]
    # Clicking the page's (now-shifted) line resolves to the rebuilt node.
    window._on_editor_line_clicked(new_page.sourceline)
    assert window.project_tree.currentItem().data(0, MODEL_NODE_ROLE) is new_page
