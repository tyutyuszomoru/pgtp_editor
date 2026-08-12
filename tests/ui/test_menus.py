# tests/ui/test_menus.py
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import (
    action_labels,
    all_top_level_menu_titles,
    editor_menu_titles,
    find_action,
    find_top_menu,
    window_menu_titles,
)


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
        # FQ-010 removed "Open Recent" (and the recentFiles store behind it)
        # and added "Show Launcher…", which FQ-027 then RENAMED to
        # "New Session": one action, not two, now re-initiating the app into the
        # launcher (save/close/relaunch) and doubling as the escape hatch from
        # Maintenance mode's menu filter. The rename is an id change, so
        # `toolbar_registry.RENAMED_ID_ALIASES` carries a row.
        # FQ-020: `Save`/`Save As...` are DELETED (saving is per-tab on the
        # Editor bar's `Deployment` menu), `Revert` became `Discard Changes`, and
        # `Deploy .pgtp` MOVED to `Deployment` -- so §18.2's project group is
        # four entries, not five.
        # BUG-058: `Project Status…` MOVED here from the Database menu, directly
        # below `Project Settings…` (owner ruling). §18.2's own four project
        # actions plus §18.8's status screen, so the group reads five.
        "Open...", "Open PHP File…", "―",
        "New Project…", "Open Project…", "Close Project", "Project Settings…",
        "Project Status…", "―",
        "Discard Changes", "Close", "―", "New Session", "Exit",
    ]


def test_file_menu_shortcuts(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    expected = {
        "Open...": "",  # Ctrl+O deliberately unbound, 2026-08-09
        "Close": "",  # Ctrl+W deliberately unbound, 2026-08-09
    }
    for label, combo in expected.items():
        action = find_action(file_menu, label)
        assert action is not None
        assert action.shortcut().toString() == combo


def test_ctrl_s_and_ctrl_shift_s_are_bound_nowhere_in_the_app(qtbot):
    """§7/FQ-020's standing invariant: `Ctrl+S` is dead app-wide and `Ctrl+Shift+S`
    is deleted. Asserted over EVERY action of both menu bars plus every
    window-level QAction, so re-adding the key anywhere reachable from a menu (or
    as a menu-less window action, the `F3` shape) fails here.

    `CodeEditorDialog`'s carved-out Ctrl+S/Ctrl+W is deliberately out of scope:
    it lives on a modal dialog, is that modal's OK button, and writes nothing to
    disk (see `tests/ui/test_code_editor.py`).
    """
    window = MainWindow()
    qtbot.addWidget(window)
    dead = {"Ctrl+S", "Ctrl+Shift+S"}
    seen = []
    for bar in (window.menuBar(), window.editor_menu_bar):
        for menu_action in bar.actions():
            menu = menu_action.menu()
            for action in (menu.actions() if menu is not None else []):
                seen.extend(
                    s.toString() for s in action.shortcuts()
                )
    seen.extend(s.toString() for action in window.actions() for s in action.shortcuts())
    assert dead & set(seen) == set()
    # ...and the router those keys drove is gone, not merely unbound.
    assert not hasattr(window, "_save_active_tab")


def test_no_QShortcut_under_the_window_claims_ctrl_s_either(qtbot):
    """The other half of the same invariant, and the sneaky way the key could
    come back: a `QShortcut` is not a `QAction`, so the sweep above would not
    see one (this app really does bind Ctrl+F/Ctrl+R/Ctrl+G that way). Every
    shortcut object in the window's widget tree is checked, at any scope.

    `CodeEditorDialog`'s two carved-out `QShortcut`s live on a modal that is not
    constructed until `Edit code…` is used, and are covered by
    `tests/ui/test_code_editor.py`.
    """
    from PySide6.QtGui import QShortcut

    window = MainWindow()
    qtbot.addWidget(window)
    bound = {
        shortcut.key().toString() for shortcut in window.findChildren(QShortcut)
    }
    assert "Ctrl+S" not in bound
    assert "Ctrl+Shift+S" not in bound


def test_file_menu_has_no_open_recent_submenu(qtbot):
    """FQ-010: `Open Recent` and the `recentFiles` store are gone. The File menu
    must carry NO submenu at all — every entry is a leaf command."""
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    assert find_action(file_menu, "Open Recent") is None
    assert [a.text() for a in file_menu.actions() if a.menu() is not None] == []


def test_exit_action_closes_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    file_menu = find_top_menu(window, "File")
    find_action(file_menu, "Exit").trigger()
    assert window.isVisible() is False


def test_the_edit_menu_no_longer_exists(qtbot):
    """FQ-016 DISSOLVED it, rather than emptying it: History…/Undo/Redo moved to
    the Editor bar's History, the five Find/Replace entries became the
    permanently visible bar, `Auto Parse XML` moved to Parsing, the two selection
    commands are FQ-015's `Select`, and Cut/Copy/Paste/Delete + Preferences…
    were deleted stubs (five of the seven absent-not-disabled violators)."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert "Edit" not in window_menu_titles(window)
    assert "Edit" not in editor_menu_titles(window)
    assert find_top_menu(window, "Edit") is None
    for gone in (
        "Cut", "Copy", "Paste", "Delete", "Preferences...",
        "Find...", "Find All", "Replace...", "Replace All",
    ):
        assert not [
            command_id
            for command_id, label in window._toolbar_ui.all_menu_commands()
            if label.endswith(gone)
        ], gone


def test_editor_menu_bar_is_a_second_bar_above_the_central_pane(qtbot):
    """The container: a child `QMenuBar` + `CenterStage` inside a widget that IS
    the central widget. A QMainWindow's own menu/toolbar areas span the docks
    too, so a bar strictly above the central pane cannot use them."""
    window = MainWindow()
    qtbot.addWidget(window)
    container = window.centralWidget()
    assert container is not window.center_stage
    assert window.center_stage.parent() is container
    assert window.editor_menu_bar.parent() is container
    # `window.center_stage` still points at the CenterStage -- the attribute
    # every other test addresses.
    assert window.center_stage is container.layout().itemAt(1).widget()
    assert window.editor_menu_bar is container.layout().itemAt(0).widget()
    # Never absorbed into the macOS system menu bar (see main_window).
    assert window.editor_menu_bar.isNativeMenuBar() is False


def test_editor_menu_bar_contents(qtbot):
    """History, Select (FQ-015), Parsing, Bookmarks, Deployment (FQ-020)."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert editor_menu_titles(window) == [
        "History",
        "Select",
        "Parsing",
        "Navigation",
        "Deployment",
    ]


def test_history_menu_contents_and_order(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "History")
    # History… FIRST: the owner's ordering, on the reasoning that "everyone uses
    # Ctrl+Z/Ctrl+Y anyway", so the entry with no shortcut leads.
    # The two step commands are named for their PROJECT scope (BUG-064): they
    # mean "undo the project, wherever you are", which is a different command
    # from the one Ctrl+Z drives in the focused surface.
    assert action_labels(menu) == [
        "History…",
        "Undo Project Edit",
        "Redo Project Edit",
    ]
    assert find_action(menu, "Undo Project Edit") is window._undo_action
    assert find_action(menu, "Redo Project Edit") is window._redo_action
    assert find_action(menu, "History…") is window._history_action


def test_parsing_menu_contents(qtbot):
    """BUG-039: FOUR members, all built once here and only `setVisible`-toggled.

    `Validate Project` MOVED here off Tools (the owner's "validate xml"); the two
    §18.5 D3a check gestures MOVED here off the Database menu, which no longer
    carries them at all."""
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Parsing")
    assert action_labels(menu) == [
        "Auto Parse XML",
        "―",
        "Validate Project",
        "―",
        "Check Object in Sandbox",
        "Check and rollback",
    ]
    assert find_action(menu, "Auto Parse XML") is window._auto_parse_action
    assert find_action(menu, "Validate Project") is window._validate_project_action
    assert find_action(menu, "Check Object in Sandbox") is window._sandbox_check_action
    assert (
        find_action(menu, "Check and rollback")
        is window._sandbox_probe_check_action
    )


def _visible_parsing_labels(window):
    menu = find_top_menu(window, "Parsing")
    return [
        action.text()
        for action in menu.actions()
        if not action.isSeparator() and action.isVisible()
    ]


def test_the_parsing_menu_shows_its_xml_face_on_a_non_ddl_tab(qtbot):
    """BUG-039's default face: on the Raw XML tab (and every other non-DDL tab)
    the XML pair is what "parsing" means, and the check pair is hidden."""
    window = MainWindow()
    qtbot.addWidget(window)

    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    assert _visible_parsing_labels(window) == ["Auto Parse XML", "Validate Project"]


def test_a_ddl_object_tab_hides_the_xml_pair_even_with_no_sandbox(qtbot):
    """The XML pair is hidden by the TAB KIND ALONE — a PL/pgSQL buffer has no
    XML to parse whether or not a sandbox exists. With no sandbox configured the
    check pair has nothing to run against either, so the menu is legitimately
    EMPTY; that is the intended posture, not a defect.

    This is also the accepted cost recorded in §7: `Validate Project` is one of
    the five DEFAULT toolbar buttons, so hiding its action empties that button
    while a DDL tab is in front."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = MainWindow()
    qtbot.addWidget(window)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")
    window.center_stage.setCurrentWidget(window.center_stage.ddl_object_tab(ref.key))

    assert _visible_parsing_labels(window) == []

    # ...and switching back restores the XML face, so the flip is not one-way.
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    assert _visible_parsing_labels(window) == ["Auto Parse XML", "Validate Project"]


def test_editor_menu_bar_is_hidden_on_the_caption_and_manual_tabs(qtbot):
    """§29's recorded recommendation: all four menus are meaningless on the two
    non-editor center-stage tabs, so the whole BAR goes (not the actions -- a
    pinned toolbar button must not blink out with it)."""
    window = MainWindow()
    qtbot.addWidget(window)
    stage = window.center_stage
    assert window.editor_menu_bar.isHidden() is False

    stage.setTabVisible(stage.caption_management_tab_index, True)
    stage.setCurrentIndex(stage.caption_management_tab_index)
    assert window.editor_menu_bar.isHidden() is True
    # The actions themselves stay alive and pinnable.
    assert window._auto_parse_action.isVisible() is True

    stage.setTabVisible(stage.manual_tab_index, True)
    stage.setCurrentIndex(stage.manual_tab_index)
    assert window.editor_menu_bar.isHidden() is True

    stage.setCurrentIndex(stage.raw_xml_tab_index)
    assert window.editor_menu_bar.isHidden() is False


def test_f3_is_a_window_level_action_with_no_menu_entry(qtbot):
    """§27: F3 survives the Edit menu's dissolution rebound onto Ctrl+L Go To
    XSD's shape -- a window action, no menu home, therefore un-pinnable."""
    window = MainWindow()
    qtbot.addWidget(window)
    action = window._find_next_action
    assert action.shortcut().toString() == "F3"
    assert action in window.actions()
    assert action.menu() is None
    ids = [cid for cid, _label in window._toolbar_ui.all_menu_commands()]
    assert not [cid for cid in ids if cid.endswith("find-next")]


def test_f3_finds_next_with_the_caret_in_the_editor(qtbot):
    """The reason F3 is window-level and not a `keyPressEvent` on the bar: it is
    pressed while the caret is in the EDITOR. Driven as a real key press."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtWidgets import QApplication

    window = MainWindow()
    qtbot.addWidget(window)
    editor = window.center_stage.xml_editor
    editor.setPlainText("one page two page")
    window.center_stage.find_replace_bar._find_field.setText("page")
    window.show()
    QApplication.processEvents()
    window.activateWindow()
    QApplication.processEvents()
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    editor.setFocus()
    QApplication.processEvents()
    assert window.isActiveWindow() is True

    qtbot.keyClick(editor, _Qt.Key.Key_F3)
    QApplication.processEvents()
    assert editor.textCursor().selectedText() == "page"
    assert editor.textCursor().selectionStart() == 4

    qtbot.keyClick(editor, _Qt.Key.Key_F3)
    QApplication.processEvents()
    assert editor.textCursor().selectionStart() == 13


def test_find_all_and_replace_all_chords_are_gone(qtbot):
    """Ctrl+Shift+F and Ctrl+Alt+Return are DELETED (§27): both commands survive
    as buttons on the permanently visible bar."""
    window = MainWindow()
    qtbot.addWidget(window)
    bound = {
        a.shortcut().toString()
        for a in window.findChildren(type(window._find_next_action))
        if not a.shortcut().isEmpty()
    }
    assert "Ctrl+Shift+F" not in bound
    assert "Ctrl+Alt+Return" not in bound


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

    # FQ-015: reached through the `Select` menu's action, which resolves the
    # active editor at trigger time. See tests/ui/test_select_menu.py for the
    # per-tab dispatch and the wrong-document regression tests.
    find_action(find_top_menu(window, "Select"), "Select Enclosing Block").trigger()

    expected = text[text.index("<Detail>"):text.index("</Detail>") + len("</Detail>")]
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected


def test_expand_selection_action_selects_parent(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    editor = window.center_stage.xml_editor
    text = "<Page>\n  <Detail>\n    <Column>x</Column>\n  </Detail>\n</Page>"
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("x"))
    editor.setTextCursor(cursor)

    find_action(find_top_menu(window, "Select"), "Expand Selection").trigger()

    expected = text[text.index("<Detail>"):text.index("</Detail>") + len("</Detail>")]
    selected = editor.textCursor().selectedText().replace(" ", "\n")
    assert selected == expected


def test_every_editor_bar_is_permanently_visible_and_expanded(qtbot):
    """FQ-016: all six construction sites ship a bar that is visible from
    construction with BOTH rows shown. (The window itself is never shown in
    these tests, so isVisibleTo reflects the widget's own show state.)"""
    window = MainWindow()
    qtbot.addWidget(window)
    stage = window.center_stage
    for bar, host in (
        (stage.find_replace_bar, stage.raw_xml_tab),
        (stage.xsd_find_replace_bar, stage.xsd_tab),
        (stage.ddl_editor_panel.find_replace_bar, stage.ddl_editor_panel),
    ):
        assert bar.isVisibleTo(host) is True
        assert bar._replace_row_widget.isVisibleTo(bar) is True


def test_ctrl_f_and_ctrl_r_focus_the_active_tabs_bar(qtbot):
    """The keys are per-editor-tab focus shortcuts, not window-level ones --
    a window-level Ctrl+F would be AMBIGUOUS against the caption panel's own
    pair (FQ-017) and neither would fire."""
    from PySide6.QtGui import QShortcut

    window = MainWindow()
    qtbot.addWidget(window)
    stage = window.center_stage
    combos = {
        s.key().toString()
        for s in stage.raw_xml_tab.findChildren(QShortcut)
        if s.parent() is stage.raw_xml_tab
    }
    assert combos == {"Ctrl+F", "Ctrl+R"}
    # ...and no Ctrl+F/Ctrl+R QShortcut is parented to the window itself.
    window_combos = {
        s.key().toString()
        for s in window.findChildren(QShortcut)
        if s.parent() is window
    }
    assert "Ctrl+F" not in window_combos
    assert "Ctrl+R" not in window_combos

    bar = stage.find_replace_bar
    bar._find_field.setText("")
    bar.focus_find()
    assert bar.focusWidget() is bar._find_field
    bar.focus_replace()
    assert bar.focusWidget() is bar._replace_field


def test_view_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert action_labels(view_menu) == [
        # "Find table reference" retired by FQ-003: table references are now
        # the References sub-section / Pages branch of the Database ▸
        # Database/XML Coherence view, with no standalone entry point.
        "Project Tree", "Properties Panel",
        # FQ-028: ONE bottom dock with two tabs. Its toggle is named for what
        # it now holds, and the two tabs get FOCUS entries (not checkable dock
        # toggles -- a tab is either in view or not, there is no third posture).
        "Activity Log / Messages Panel", "Activity Log", "Messages",
        # BUG-061: the LEFT dock's Findings tab, in the same run of FOCUS entries
        # (not checkable). It had no user gesture at all before -- only the audit
        # router could reveal it -- so with no navigable op behind it the tab
        # appeared not to exist.
        "Findings",
        "Raw XML Panel",
        "―",
        "Expand All", "Collapse All",
        "―",
        "Light Theme",
        # FQ-260812002827 ENDS the menu here. `Customize Toolbar…` and
        # `Customize Shortcuts…` were the last two entries; both were MOVED into
        # `Settings ▸ Software settings…` and removed from `View`, so the
        # trailing separator went with them.
    ]


def test_the_two_customize_entries_are_GONE_from_the_view_menu(qtbot):
    """Relocating means moving (owner-settled, FQ-260812002827): both surfaces
    live in the Software settings dialog now, and leaving a second door here
    would defeat the consolidation."""
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert find_action(view_menu, "Customize Toolbar…") is None
    assert find_action(view_menu, "Customize Shortcuts…") is None


def test_the_shortcuts_pane_is_offered_the_whole_command_universe(qtbot):
    """FQ-012's contract, unchanged by the re-hosting: the pane is fed the SAME
    menu walk Customize Toolbar uses, never a second one."""
    window = MainWindow()
    qtbot.addWidget(window)
    dialog = window.build_customize_shortcuts_pane()
    qtbot.addWidget(dialog)
    assert dialog.isModal() is False
    assert dialog.command_ids() == [
        command_id for command_id, _label in window._toolbar_ui.all_menu_commands()
    ]


def test_view_menu_default_checked_states(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert find_action(view_menu, "Project Tree").isChecked() is True
    assert find_action(view_menu, "Properties Panel").isChecked() is True
    assert find_action(view_menu, "Activity Log / Messages Panel").isChecked() is True
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
    find_action(view_menu, "Activity Log / Messages Panel").trigger()
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
        (window.audit_dock, "Activity Log / Messages Panel"),
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
        (window.audit_dock, "Activity Log / Messages Panel"),
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
        (window.audit_dock, "Activity Log / Messages Panel"),
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
        # BUG-260812002307 part C: the one sanctioned overwrite of the
        # hand-owned curated.xsd. Deliberately carries NO shortcut (DEC-012 —
        # a menu command form has exactly one keyboard host, and a chord would
        # have to clear `docs/KEYBINDINGS.md` first).
        "Restore Bundled Curated Schema…",
    ]


def test_schema_menu_sits_between_view_and_tools(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window_menu_titles(window) == [
        # `Settings` (FQ-030) is a MAINTENANCE-ONLY menu: it is built like every
        # other one and only `setVisible`-toggled, so it is enumerated here even
        # though it is hidden outside the mode. See test_edit_snippets_menu.py.
        "File", "View", "Schema", "Database", "Tools", "Generation",
        "Settings", "Help",
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
        # FQ-017 deleted "Caption Filter…": the modal it opened duplicated the
        # Caption Management tab's own permanent Find/Replace bar.
        "Manage Captions...", "―",
        # "Validate Project" MOVED to the Editor bar's Parsing menu (FQ-016) --
        # it is the owner's "validate xml". §22's three lint entries stay here
        # (§29 open item: whether all three follow it).
        "Lint Current File", "Lint on Save", "Locate PHP Linter…", "―",
        "Reparse Raw XML into Tree", "―",
        # NO Compare/Merge command survives here. FQ-020 took
        # `Compare / Merge Two Files...` (-> `Deployment ▸ Compare/Merge pgtp`)
        # and `Apply Changes to Target`; FQ-021's third leg took the two
        # Difference steppers and rehomed Apply, all three onto `Navigation` as
        # mode-only members -- deliberately NOT `Deployment`, which would put two
        # very differently shaped irreversible actions under one menu.
        # §23's embedded MCP server: one checkable entry, off at startup.
        "Start MCP Server",
    ]
    assert find_action(menu, "Compare / Merge Two Files...") is None
    assert find_action(menu, "Apply Changes to Target") is None
    assert find_action(menu, "Next Difference") is None
    assert find_action(menu, "Prev Difference") is None
    assert find_action(menu, "Previous Difference") is None


def test_validate_project_action_populates_audit(qtbot):
    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.find_controller import _VALIDATION_PREFIX

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

    menu = find_top_menu(window, "Parsing")
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
    # Two bars since FQ-016: `Edit` is gone from the window bar and the bookmark
    # menu moved off it onto the Editor bar (retitled `Navigation` by FQ-021).
    assert window_menu_titles(window) == [
        # `Settings` (FQ-030) is a MAINTENANCE-ONLY menu: it is built like every
        # other one and only `setVisible`-toggled, so it is enumerated here even
        # though it is hidden outside the mode. See test_edit_snippets_menu.py.
        "File", "View", "Schema", "Database", "Tools", "Generation",
        "Settings", "Help",
    ]
    assert editor_menu_titles(window) == [
        "History",
        "Select",
        "Parsing",
        "Navigation",
        "Deployment",
    ]
    # `all_top_level_menu_titles` spans both, window bar first.
    assert all_top_level_menu_titles(window) == (
        window_menu_titles(window) + editor_menu_titles(window)
    )


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


def test_navigation_menu_moved_onto_the_editor_menu_bar(qtbot):
    """FQ-016: it was a top-level WINDOW menu between Tools and Generation; it is
    a per-editor menu, so it belongs on the per-editor bar. Under its FQ-016
    title (`Bookmarks`) it must be gone from BOTH bars, not merely renamed on
    the window bar."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert "Navigation" not in window_menu_titles(window)
    assert "Bookmarks" not in window_menu_titles(window)
    titles = editor_menu_titles(window)
    assert "Bookmarks" not in titles
    assert titles.index("Navigation") == titles.index("Parsing") + 1


def test_navigation_menu_contents(qtbot):
    """All eight members, in order. `action_labels` reads `menu.actions()`, so
    the three Compare/Merge members appear here even though they are HIDDEN
    outside the mode -- which is the point: they are built once and only shown /
    hidden (FQ-021), so their command ids stay stable for the toolbar.
    Their per-mode visibility is asserted in test_diff_merge_mode.py."""
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Navigation")
    assert action_labels(menu) == [
        "Toggle Bookmark", "Next Bookmark", "Previous Bookmark", "―",
        "Clear All Bookmarks", "List All Bookmarks", "―",
        # FQ-021: `Next`/`Previous Difference` MOVED off Tools (`Prev` became
        # `Previous`, matching `Previous Bookmark`), and `Apply Changes to
        # Target` finally has a menu home again.
        "Next Difference", "Previous Difference", "Apply Changes to Target",
    ]


def test_navigation_menu_shortcuts(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Navigation")
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
    menu = find_top_menu(window, "Navigation")
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
    menu = find_top_menu(window, "Navigation")
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
    menu = find_top_menu(window, "Navigation")
    find_action(menu, "Clear All Bookmarks").trigger()
    assert editor.bookmarked_lines() == []


# -- Navigation menu follows the active editor tab (§8) ----------------------


def _activate_ddl_tab(window):
    stage = window.center_stage
    stage.show_ddl_explorer()
    stage.setCurrentIndex(stage.ddl_tab_index)
    return stage.ddl_editor_panel.editor


def test_bookmark_actions_target_the_active_ddl_editor(qtbot):
    """The four bookmark actions resolve their editor at trigger time, so on
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

    menu = find_top_menu(window, "Navigation")
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
    menu = find_top_menu(window, "Navigation")

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

    find_action(find_top_menu(window, "Navigation"), "Toggle Bookmark").trigger()

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

    find_action(find_top_menu(window, "Navigation"), "Toggle Bookmark").trigger()

    assert window.center_stage.currentIndex() == before
