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
        # "Open PHP File…" (§21) sits beside "Open..." because it IS an open
        # gesture, and above the project separator: a .php file has no
        # structural tie to a .pgtp and opens with or without a project.
        "Open...", "Open Recent", "Open PHP File…", "―",
        "New Project…", "Open Project…", "Close Project", "Project Settings…", "Deploy .pgtp", "―",
        "Save", "Save As...",
        "Revert", "Close", "―", "Exit",
    ]


def test_file_menu_shortcuts(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    expected = {
        "Open...": "Ctrl+O",
        "Save": "Ctrl+S",
        "Save As...": "Ctrl+Shift+S",
        "Close": "Ctrl+W",
    }
    for label, combo in expected.items():
        action = find_action(file_menu, label)
        assert action is not None
        assert action.shortcut().toString() == combo


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


def test_edit_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    assert action_labels(edit_menu) == [
        "Undo", "Redo", "History…", "―",
        "Cut", "Copy", "Paste", "Delete", "―",
        "Find...", "Find Next", "Find All", "Replace...", "Replace All", "―",
        "Select Enclosing Block", "Select Parent Block", "―",
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


def test_edit_menu_structural_selection_shortcuts(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    assert find_action(edit_menu, "Select Enclosing Block").shortcut().toString() == "Ctrl+Shift+B"
    assert find_action(edit_menu, "Select Parent Block").shortcut().toString() == "Ctrl+Shift+A"


def test_select_enclosing_block_action_selects_block(qtbot):
    from PySide6.QtGui import QTextCursor

    window = MainWindow()
    qtbot.addWidget(window)
    editor = window.center_stage.xml_editor
    text = "<Page>\n  <Detail>\n    x\n  </Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("x"))
    editor.setTextCursor(cursor)

    edit_menu = find_top_menu(window, "Edit")
    find_action(edit_menu, "Select Enclosing Block").trigger()

    expected = text[text.index("<Detail>"):text.index("</Detail>") + len("</Detail>")]
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected


def test_select_parent_block_action_selects_parent(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    editor = window.center_stage.xml_editor
    text = "<Page>\n  <Detail>\n    <Column>x</Column>\n  </Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("x"))
    editor.setTextCursor(cursor)

    edit_menu = find_top_menu(window, "Edit")
    find_action(edit_menu, "Select Parent Block").trigger()

    expected = text[text.index("<Detail>"):text.index("</Detail>") + len("</Detail>")]
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected


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
        # "Find table reference" retired by FQ-003: table references are now
        # the References sub-section / Pages branch of the Database ▸
        # Database/XML Coherence view, with no standalone entry point.
        "Project Tree", "Properties Panel",
        "Audit/Problems Panel", "Raw XML Panel",
        "―",
        "Expand All", "Collapse All",
        "―",
        "Light Theme",
        "―",
        "Customize Toolbar…",
    ]


def test_view_menu_default_checked_states(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert find_action(view_menu, "Project Tree").isChecked() is True
    assert find_action(view_menu, "Properties Panel").isChecked() is True
    assert find_action(view_menu, "Audit/Problems Panel").isChecked() is True
    assert find_action(view_menu, "Raw XML Panel").isChecked() is True


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


def test_closing_dock_directly_unchecks_view_action(qtbot):
    # BUG-007: closing a dock via its own title-bar ✕ (== close()/hide())
    # must uncheck the matching View-menu action — the wiring is
    # bidirectional, not just action → dock.
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    view_menu = find_top_menu(window, "View")
    for dock, label in (
        (window.tree_dock, "Project Tree"),
        (window.properties_dock, "Properties Panel"),
        (window.audit_dock, "Audit/Problems Panel"),
    ):
        assert find_action(view_menu, label).isChecked() is True
        dock.close()
        assert find_action(view_menu, label).isChecked() is False


def test_reshowing_dock_rechecks_view_action(qtbot):
    # visibilityChanged fires both ways (BUG-007): re-showing the dock
    # programmatically re-checks the action too.
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    view_menu = find_top_menu(window, "View")
    for dock, label in (
        (window.tree_dock, "Project Tree"),
        (window.properties_dock, "Properties Panel"),
        (window.audit_dock, "Audit/Problems Panel"),
    ):
        dock.close()
        assert find_action(view_menu, label).isChecked() is False
        dock.show()
        assert find_action(view_menu, label).isChecked() is True
        assert dock.isVisible() is True


def test_view_action_reopens_dock_after_direct_close(qtbot):
    # BUG-007 recovery path: after the user closes a dock via its title-bar ✕
    # (action now unchecked), triggering the View-menu action must re-show
    # the dock and re-check itself.
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    view_menu = find_top_menu(window, "View")
    for dock, label in (
        (window.tree_dock, "Project Tree"),
        (window.properties_dock, "Properties Panel"),
        (window.audit_dock, "Audit/Problems Panel"),
    ):
        dock.close()
        action = find_action(view_menu, label)
        assert action.isChecked() is False
        action.trigger()
        assert dock.isVisible() is True
        assert action.isChecked() is True


def test_dock_action_round_trip_does_not_oscillate(qtbot):
    # The bidirectional wiring must settle (Qt only emits toggled /
    # visibilityChanged on real state changes): toggling the action off and
    # on again leaves dock and checkbox in agreement.
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    view_menu = find_top_menu(window, "View")
    action = find_action(view_menu, "Project Tree")
    action.trigger()  # off
    assert window.tree_dock.isVisible() is False
    assert action.isChecked() is False
    action.trigger()  # on again
    assert window.tree_dock.isVisible() is True
    assert action.isChecked() is True


def test_toggling_raw_xml_panel_hides_and_shows_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    center = window.center_stage
    # Starts visible (and the action checked); toggling once hides it.
    assert center.isTabVisible(center.raw_xml_tab_index) is True
    view_menu = find_top_menu(window, "View")
    raw_action = find_action(view_menu, "Raw XML Panel")
    raw_action.trigger()
    assert center.isTabVisible(center.raw_xml_tab_index) is False
    raw_action.trigger()
    assert center.isTabVisible(center.raw_xml_tab_index) is True


def test_expand_all_and_collapse_all_drive_tree(qtbot):
    from tests.ui._sample_project import build_sample_project

    window = MainWindow()
    qtbot.addWidget(window)
    window.project_tree.populate_from_project(build_sample_project())
    top = window.project_tree.topLevelItem(0)
    assert top is not None and top.childCount() > 0

    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Collapse All").trigger()
    assert top.isExpanded() is False
    find_action(view_menu, "Expand All").trigger()
    assert top.isExpanded() is True


def test_no_top_level_diff_merge_menu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert find_top_menu(window, "Diff / Merge") is None


def test_schema_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Schema")
    assert menu is not None
    assert action_labels(menu) == [
        "Edit XSD",
        "Edit AutoXSD",
        "Verify XSD",
        "Export XSD",
        "Import XSD",
    ]


def test_schema_menu_sits_between_view_and_tools(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    titles = all_top_level_menu_titles(window)
    assert titles == [
        "File", "Edit", "View", "Schema", "Database", "Tools", "Bookmarks",
        "Generation", "Help",
    ]


def test_schema_menu_actions_are_always_enabled(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Schema")
    for label in ("Edit XSD", "Edit AutoXSD", "Verify XSD", "Export XSD", "Import XSD"):
        assert find_action(menu, label).isEnabled() is True


def test_tools_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Tools")
    assert action_labels(menu) == [
        "Manage Captions...", "Caption Filter…", "―",
        "Validate Project", "―",
        # §22 PHP lint, directly under Validate Project: the same kind of
        # gesture one tier down (this file, not the project).
        "Lint Current File", "Lint on Save", "Locate PHP Linter…", "―",
        "Reparse Raw XML into Tree", "―",
        "Compare / Merge Two Files...", "Next Difference", "Prev Difference",
        "Apply Changes to Target",
    ]


def test_validate_project_action_populates_audit(qtbot):
    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import _VALIDATION_PREFIX

    window = MainWindow()
    qtbot.addWidget(window)
    xml = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="dup.php" tableName="t1"/>\n'
        '      <Page fileName="dup.php" tableName="t2"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    window._current_project = load_project_from_text(xml)
    window.center_stage.xml_editor.setPlainText(xml)

    menu = find_top_menu(window, "Tools")
    find_action(menu, "Validate Project").trigger()

    validation_items = [
        window.audit_panel.item(row).text()
        for row in range(window.audit_panel.count())
        if window.audit_panel.item(row).text().startswith(_VALIDATION_PREFIX)
    ]
    assert any("ERROR" in t for t in validation_items)


def test_generation_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Generation")
    assert action_labels(menu) == [
        "Locate PHP Generator Executable...", "―",
        "Generate PHP...", "―",
        "Open Output Folder", "―",
        "Locate panGen Runtime...",
        "panGen (Generate Own PHP)",
        "rePHPgen (Analyze Gap)",
        "Save reJSON...",
    ]


def test_help_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Help")
    assert action_labels(menu) == ["Manual", "Open Log Folder", "About"]


def test_all_top_level_menus_present_in_order(qtbot):
    # The menu bar's phantom empty-titled overflow-chevron QMenu (which under
    # Fusion exists even without show()) is filtered out inside
    # all_top_level_menu_titles — see _menu_helpers._top_level_menus.
    window = MainWindow()
    qtbot.addWidget(window)
    titles = all_top_level_menu_titles(window)
    assert titles == [
        "File", "Edit", "View", "Schema", "Database", "Tools", "Bookmarks",
        "Generation", "Help",
    ]


def test_raw_xml_panel_action_is_accessible_as_attribute(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert window._raw_xml_panel_action is find_action(view_menu, "Raw XML Panel")


def test_view_menu_has_no_wrap_raw_xml_lines_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert "Wrap Raw XML Lines" not in action_labels(view_menu)
    assert "Wrap Lines" not in action_labels(view_menu)


def test_bookmarks_menu_sits_between_tools_and_generation(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    titles = all_top_level_menu_titles(window)
    assert titles.index("Bookmarks") == titles.index("Tools") + 1
    assert titles.index("Bookmarks") == titles.index("Generation") - 1


def test_bookmarks_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Bookmarks")
    assert action_labels(menu) == [
        "Toggle Bookmark", "Next Bookmark", "Previous Bookmark", "―",
        "Clear All Bookmarks",
    ]


def test_bookmarks_menu_shortcuts(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Bookmarks")
    assert find_action(menu, "Toggle Bookmark").shortcut().toString() == "Ctrl+F2"
    assert find_action(menu, "Next Bookmark").shortcut().toString() == "F2"
    assert find_action(menu, "Previous Bookmark").shortcut().toString() == "Shift+F2"


def test_toggle_bookmark_action_marks_cursor_line(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb\nc\nd")
    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(2).position())
    editor.setTextCursor(cursor)
    menu = find_top_menu(window, "Bookmarks")
    find_action(menu, "Toggle Bookmark").trigger()
    assert editor.bookmarked_lines() == [2]


def test_next_bookmark_action_moves_cursor_with_wrap(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb\nc\nd\ne")
    for n in (1, 3):
        editor.toggle_bookmark(n)
    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(0).position())
    editor.setTextCursor(cursor)
    menu = find_top_menu(window, "Bookmarks")
    next_action = find_action(menu, "Next Bookmark")
    next_action.trigger()
    assert editor.textCursor().blockNumber() == 1
    next_action.trigger()
    assert editor.textCursor().blockNumber() == 3
    next_action.trigger()  # wrap
    assert editor.textCursor().blockNumber() == 1


def test_clear_all_bookmarks_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb\nc")
    editor.toggle_bookmark(0)
    editor.toggle_bookmark(2)
    menu = find_top_menu(window, "Bookmarks")
    find_action(menu, "Clear All Bookmarks").trigger()
    assert editor.bookmarked_lines() == []


# -- Bookmarks menu follows the active editor tab (§8) -----------------------


def _activate_ddl_tab(window):
    stage = window.center_stage
    stage.show_ddl_explorer()
    stage.setCurrentIndex(stage.ddl_tab_index)
    return stage.ddl_editor_panel.editor


def test_bookmark_actions_target_the_active_ddl_editor(qtbot):
    """The four Bookmarks actions resolve their editor at trigger time, so on
    the DDL Explorer tab they act on the DDL buffer -- not on Raw XML, which
    they used to be bound to permanently."""
    window = MainWindow()
    qtbot.addWidget(window)
    raw = window.center_stage.xml_editor
    raw.setPlainText("x\ny\nz")
    ddl = _activate_ddl_tab(window)
    ddl.setPlainText("a\nb\nc\nd")
    cursor = ddl.textCursor()
    cursor.setPosition(ddl.document().findBlockByNumber(2).position())
    ddl.setTextCursor(cursor)

    menu = find_top_menu(window, "Bookmarks")
    find_action(menu, "Toggle Bookmark").trigger()

    assert ddl.bookmarked_lines() == [2]
    assert raw.bookmarked_lines() == []  # Raw XML untouched


def test_bookmark_navigation_and_clear_follow_the_active_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    ddl = _activate_ddl_tab(window)
    ddl.setPlainText("a\nb\nc\nd\ne")
    for n in (1, 3):
        ddl.toggle_bookmark(n)
    cursor = ddl.textCursor()
    cursor.setPosition(ddl.document().findBlockByNumber(0).position())
    ddl.setTextCursor(cursor)
    menu = find_top_menu(window, "Bookmarks")

    find_action(menu, "Next Bookmark").trigger()
    assert ddl.textCursor().blockNumber() == 1

    find_action(menu, "Clear All Bookmarks").trigger()
    assert ddl.bookmarked_lines() == []


def test_bookmark_actions_target_the_active_xsd_editor(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    stage = window.center_stage
    stage.show_edit_xsd()
    stage.setCurrentIndex(stage.xsd_tab_index)
    xsd = stage.xsd_editor
    xsd.setPlainText("a\nb\nc")
    cursor = xsd.textCursor()
    cursor.setPosition(xsd.document().findBlockByNumber(1).position())
    xsd.setTextCursor(cursor)

    find_action(find_top_menu(window, "Bookmarks"), "Toggle Bookmark").trigger()

    assert xsd.bookmarked_lines() == [1]
    assert window.center_stage.xml_editor.bookmarked_lines() == []
    # setPlainText marked the XSD tab dirty; silence the teardown close prompt
    # so it never reaches a real modal (CLAUDE.md testing policy).
    window._xsd_ui.confirm_close = lambda: "discard"


def test_bookmark_actions_do_not_switch_tabs(qtbot):
    """Toggling a bookmark must never yank the user to another tab -- unlike
    the Find bar's routing, which deliberately reveals Raw XML."""
    window = MainWindow()
    qtbot.addWidget(window)
    ddl = _activate_ddl_tab(window)
    ddl.setPlainText("a\nb")
    before = window.center_stage.currentIndex()

    find_action(find_top_menu(window, "Bookmarks"), "Toggle Bookmark").trigger()

    assert window.center_stage.currentIndex() == before
