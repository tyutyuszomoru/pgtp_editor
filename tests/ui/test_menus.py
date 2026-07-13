# tests/ui/test_menus.py
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import action_labels, all_top_level_menu_titles, find_action, find_top_menu


def test_file_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    assert file_menu is not None
    labels = action_labels(file_menu)
    assert labels == [
        "New Project", "Open...", "Open Recent", "Save", "Save As...", "Close", "―", "Exit",
    ]


def test_open_recent_is_an_empty_submenu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    open_recent_action = find_action(file_menu, "Open Recent")
    open_recent_menu = open_recent_action.menu()
    assert open_recent_menu is not None
    assert open_recent_menu.actions() == []


def test_exit_action_closes_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    file_menu = find_top_menu(window, "File")
    find_action(file_menu, "Exit").trigger()
    assert window.isVisible() is False


def test_other_file_actions_show_stub_message(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    find_action(file_menu, "New Project").trigger()
    assert window.statusBar().currentMessage() == "Not yet implemented: New Project"


def test_edit_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    assert action_labels(edit_menu) == [
        "Undo", "Redo", "―",
        "Cut", "Copy", "Paste", "Delete", "―",
        "Find...", "Find Next", "Find All", "Replace...", "Replace All", "―",
        "Preferences...",
    ]


def test_edit_menu_search_shortcuts(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    expected = {
        "Find...": "Ctrl+F",
        "Find Next": "F3",
        "Find All": "Ctrl+Shift+F",
        "Replace...": "Ctrl+R",
        "Replace All": "Ctrl+Alt+Return",
    }
    for label, combo in expected.items():
        action = find_action(edit_menu, label)
        assert action is not None
        assert action.shortcut().toString() == combo


def test_find_menu_action_shows_bar_and_raw_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    find_action(edit_menu, "Find...").trigger()
    # The window itself is never shown in this test, so isVisible() (which
    # requires all ancestors on screen) is False; isVisibleTo(tab) reflects
    # the bar's own show state, which show_find() sets.
    bar = window.center_stage.find_replace_bar
    assert bar.isVisibleTo(window.center_stage.raw_xml_tab) is True
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index


def test_replace_menu_action_shows_replace_row(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    find_action(edit_menu, "Replace...").trigger()
    bar = window.center_stage.find_replace_bar
    assert bar.isVisibleTo(window.center_stage.raw_xml_tab) is True
    assert bar._replace_row_widget.isVisibleTo(bar) is True


def test_view_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert action_labels(view_menu) == [
        "Project Tree", "Properties Panel", "Audit/Problems Panel", "Raw XML Panel",
        "Wrap Raw XML Lines", "―",
        "Expand All", "Collapse All",
    ]


def test_view_menu_default_checked_states(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert find_action(view_menu, "Project Tree").isChecked() is True
    assert find_action(view_menu, "Properties Panel").isChecked() is True
    assert find_action(view_menu, "Audit/Problems Panel").isChecked() is True
    assert find_action(view_menu, "Raw XML Panel").isChecked() is False


def test_toggling_project_tree_hides_dock(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.tree_dock.isVisible() is True
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Project Tree").trigger()
    assert window.tree_dock.isVisible() is False


def test_toggling_audit_panel_hides_dock(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.audit_dock.isVisible() is True
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Audit/Problems Panel").trigger()
    assert window.audit_dock.isVisible() is False


def test_toggling_properties_panel_hides_dock(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.properties_dock.isVisible() is True
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Properties Panel").trigger()
    assert window.properties_dock.isVisible() is False


def test_toggling_raw_xml_panel_shows_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Raw XML Panel").trigger()
    assert window.center_stage.isTabVisible(window.center_stage.raw_xml_tab_index) is True


def test_expand_all_shows_stub_message(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Expand All").trigger()
    assert window.statusBar().currentMessage() == "Not yet implemented: Expand All"


def test_diff_merge_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Diff / Merge")
    assert action_labels(menu) == [
        "Compare / Merge Two Files...", "―",
        "Next Difference", "Prev Difference", "Apply Changes to Target",
    ]


def test_schema_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Schema")
    assert menu is not None
    assert action_labels(menu) == ["Annotate Schema Values..."]


def test_schema_menu_sits_between_diff_merge_and_tools(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    titles = all_top_level_menu_titles(window)
    assert titles == [
        "File", "Edit", "View", "Diff / Merge", "Schema", "Tools", "Generation", "Help",
    ]


def test_annotate_schema_values_action_is_always_enabled(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Schema")
    action = find_action(menu, "Annotate Schema Values...")
    assert action.isEnabled() is True


def test_tools_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Tools")
    assert action_labels(menu) == [
        "Manage Captions...", "―",
        "Find Reused Tables...", "―",
        "Validate Project", "―",
        "Reparse Raw XML into Tree",
    ]


def test_generation_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Generation")
    assert action_labels(menu) == [
        "Locate PHP Generator Executable...", "―",
        "Generate PHP...", "―",
        "Open Output Folder",
    ]


def test_help_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Help")
    assert action_labels(menu) == ["Documentation", "About"]


def test_all_top_level_menus_present_in_order(qtbot):
    # Do not call window.show() here — under the offscreen test platform's
    # small virtual screen, showing this window triggers Qt's menu-bar
    # overflow chevron, which injects a phantom empty-titled QMenu into
    # findChildren(QMenu) and breaks this order/count assertion.
    window = MainWindow()
    qtbot.addWidget(window)
    titles = all_top_level_menu_titles(window)
    assert titles == [
        "File", "Edit", "View", "Diff / Merge", "Schema", "Tools", "Generation", "Help",
    ]


def test_raw_xml_panel_action_is_accessible_as_attribute(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert window._raw_xml_panel_action is find_action(view_menu, "Raw XML Panel")


def test_view_menu_contains_wrap_raw_xml_lines_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert action_labels(view_menu) == [
        "Project Tree", "Properties Panel", "Audit/Problems Panel", "Raw XML Panel",
        "Wrap Raw XML Lines", "―",
        "Expand All", "Collapse All",
    ]


def test_wrap_raw_xml_lines_action_default_unchecked(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert find_action(view_menu, "Wrap Raw XML Lines").isChecked() is False


def test_toggling_wrap_raw_xml_lines_changes_editor_line_wrap_mode(qtbot):
    from PySide6.QtWidgets import QPlainTextEdit

    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Wrap Raw XML Lines").trigger()
    assert window.center_stage.xml_editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
