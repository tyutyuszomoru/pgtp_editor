"""FQ-010 + FQ-027 — the startup launcher: three mode columns, the session-only
Maintenance menu filter, `File ▸ New Session`, and the two hard constraints that
keep the launcher out of the suite's way.

The lane lives in `ui/launcher_dialog.py` plus `MainWindow`'s
`set_workflow_mode` / `_refresh_workflow_mode_affordances` / `new_session`.
Tests drive `LauncherDialog`'s seam (`entry_ids`, `choose`, `cancel`) and pass
`exec_dialog=` to `show_launcher` — **no test calls `.exec()`**, and no test lets
a launcher-picked action actually open a real modal (every action is a stand-in
unless the test is specifically checking identity with the menu's own QAction).

FQ-027 DELETED the "Don't show this again" suppression entirely (the
`launcherSuppressed` key, the checkbox, the `force=` bypass), so the tests that
pinned that behaviour are gone rather than inverted — there is nothing left to
assert about a flag that no longer exists.

`main()`-side coverage (the seam, the `--mcp` unreachability, `args.file`) is in
`tests/test_main.py`.
"""
import pytest
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from pgtp_editor.ui import toolbar_registry
from pgtp_editor.ui.launcher_dialog import (
    GROUP_MODES,
    LAUNCHER_GROUPS,
    MODE_MAINTENANCE,
    MODE_PROJECT,
    MODE_STANDALONE,
    LauncherDialog,
    resolve_menu_entries,
    show_launcher,
)
from pgtp_editor.ui.main_window import (
    _MAINTENANCE_FILE_ITEMS,
    _MAINTENANCE_MENU_TITLES,
    _MAINTENANCE_ONLY_MENU_TITLES,
    MainWindow,
)
from tests.ui._menu_helpers import (
    action_labels,
    editor_menu_titles,
    find_action,
    find_top_menu,
    window_menu_titles,
)


def _ini_settings(tmp_path, name="s.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


def _fake_entries(command_ids, fired=None):
    """`command_id -> (label, QAction)` with recording actions, so a test never
    triggers a real File/Schema/Generation slot."""
    entries = {}
    for command_id in command_ids:
        action = QAction(command_id)
        if fired is not None:
            action.triggered.connect(
                lambda _checked=False, cid=command_id: fired.append(cid)
            )
        entries[command_id] = (command_id.replace(".", " › "), action)
    return entries


def _all_group_ids():
    return [cid for _title, ids in LAUNCHER_GROUPS for cid in ids]


def _visible_labels(menu_or_bar):
    return [
        action.text()
        for action in menu_or_bar.actions()
        if action.isVisible() and not action.isSeparator()
    ]


def _unfiltered_window_labels(window):
    """What the WINDOW bar shows outside any mode.

    Not simply `window_menu_titles`: since FQ-030 the bar carries `Settings`,
    the app's first MAINTENANCE-ONLY menu, which is built like every other one
    (so it is enumerated) but hidden until the mode is entered. The unfiltered
    bar is therefore every built menu MINUS the maintenance-only ones.
    """
    return [
        title
        for title in window_menu_titles(window)
        if title not in _MAINTENANCE_ONLY_MENU_TITLES
    ]


# -- the three mode columns (FQ-027) -----------------------------------------


def test_there_are_exactly_three_columns():
    """One row, three boxes: the app's three major modes."""
    assert len(LAUNCHER_GROUPS) == 3
    assert [title for title, _ids in LAUNCHER_GROUPS] == [
        "Standalone",
        "Project",
        "Maintenance",
    ]


def test_column_membership_is_the_owners_taxonomy():
    groups = dict(LAUNCHER_GROUPS)
    # Standalone MERGES FQ-010's "Open a pgtp for editing" and "Open other
    # files" -- both are "open something, with no project behind it".
    assert groups["Standalone"] == ("file.open", "file.open-php-file")
    assert groups["Project"] == ("file.new-project", "file.open-project")
    # Edit XSD + Import XSD only: the owner's verbatim "Open XSD" names the
    # read-only viewer that was deleted in favour of the editable tab, and the
    # §20 re_phpgen/panGen entries left the launcher with FQ-027.
    assert groups["Maintenance"] == ("schema.edit-xsd", "schema.import-xsd")


def test_every_column_names_a_workflow_mode():
    assert GROUP_MODES == {
        "Standalone": MODE_STANDALONE,
        "Project": MODE_PROJECT,
        "Maintenance": MODE_MAINTENANCE,
    }
    assert set(GROUP_MODES) == {title for title, _ids in LAUNCHER_GROUPS}


@pytest.mark.parametrize(
    "excluded",
    [
        # §19's vendor PHP generation was never in the launcher...
        "generation.locate-php-generator-executable",
        "generation.generate-php",
        "generation.open-output-folder",
        # ...and FQ-027 removed §20's re_phpgen/panGen loop from it too.
        "generation.locate-pangen-runtime",
        "generation.pangen-generate-own-php",
        "generation.rephpgen-analyze-gap",
        "generation.save-rejson",
        # Maintenance is Edit XSD + Import XSD, not the whole Schema menu.
        "schema.edit-autoxsd",
        "schema.verify-xsd",
        "schema.export-xsd",
    ],
)
def test_ids_that_are_deliberately_in_no_column(excluded):
    assert excluded not in _all_group_ids()


def test_every_group_id_resolves_to_a_real_menu_action(qtbot, tmp_path):
    """The launcher never reimplements a gesture: every id must name a live menu
    command, and the entry must BE the menu's own QAction."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    entries = resolve_menu_entries(window)
    missing = [cid for cid in _all_group_ids() if cid not in entries]
    assert missing == []
    _label, open_action = entries["file.open"]
    assert open_action is find_action(find_top_menu(window, "File"), "Open...")


def test_dialog_offers_every_group_id_in_order():
    entries = _fake_entries(_all_group_ids())
    dialog = LauncherDialog(entries)
    assert dialog.entry_ids() == _all_group_ids()


def test_dialog_labels_are_the_menu_path_labels():
    entries = _fake_entries(["file.open"])
    dialog = LauncherDialog(entries)
    assert dialog.button_for("file.open").text() == "file › open"


def test_a_disabled_menu_action_gives_a_disabled_button():
    """Shares the menu item's enabled state: `Generation ▸ Save reJSON…` starts
    disabled, and a button that looks clickable but does nothing is worse."""
    entries = _fake_entries(["file.open", "generation.save-rejson"])
    entries["generation.save-rejson"][1].setEnabled(False)
    dialog = LauncherDialog(
        entries,
        groups=(("G", ("file.open", "generation.save-rejson")),),
    )
    assert dialog.button_for("file.open").isEnabled() is True
    assert dialog.button_for("generation.save-rejson").isEnabled() is False


def test_a_group_whose_ids_are_all_missing_is_dropped_not_crashed():
    """Defensive: a renamed menu must never stop the app from starting."""
    dialog = LauncherDialog(
        _fake_entries(["file.open"]),
        groups=(("Real", ("file.open",)), ("Gone", ("nope.nothing",))),
    )
    assert dialog.entry_ids() == ["file.open"]


def test_there_is_no_suppression_surface_left():
    """FQ-027 deleted "Don't show this again" outright: no checkbox, no
    accessors, no `force=` bypass."""
    import inspect

    import pgtp_editor.ui.launcher_dialog as launcher_mod

    dialog = LauncherDialog(_fake_entries(["file.open"]))
    for gone in ("suppress_checkbox", "suppress_requested", "set_suppressed"):
        assert not hasattr(dialog, gone)
    for gone in (
        "LAUNCHER_SUPPRESSED_SETTINGS_KEY",
        "launcher_suppressed",
        "set_launcher_suppressed",
    ):
        assert not hasattr(launcher_mod, gone)
    assert "force" not in inspect.signature(show_launcher).parameters


def test_the_launcher_writes_nothing_to_settings_and_is_never_skipped(tmp_path):
    """The launcher owned exactly one QSettings key and it is gone, so showing
    it twice over the same store must show it twice — there is no flag left that
    could make the second call a no-op."""
    settings = _ini_settings(tmp_path)
    execs = []
    for _ in range(2):
        show_launcher(
            None,
            settings,
            resolve_entries=lambda _w: _fake_entries(["file.open"]),
            exec_dialog=lambda dialog: execs.append(True) or dialog.cancel(),
        )
    assert execs == [True, True]
    assert settings.allKeys() == []


# -- picking an entry --------------------------------------------------------


def test_choosing_an_entry_accepts_and_records_it():
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    dialog.choose("file.open")
    assert dialog.chosen_command_id == "file.open"
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_choose_does_not_trigger_the_action_itself():
    """The action fires only once the modal is down (`show_launcher`), so an
    action that opens its own QFileDialog is never stacked on the launcher."""
    fired = []
    dialog = LauncherDialog(_fake_entries(["file.open"], fired))
    dialog.choose("file.open")
    assert fired == []


def test_choosing_an_unknown_id_is_ignored():
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    dialog.choose("file.nonsense")
    assert dialog.chosen_command_id is None
    assert dialog.chosen_workflow_mode is None


@pytest.mark.parametrize(
    "command_id,mode",
    [
        ("file.open", MODE_STANDALONE),
        ("file.open-php-file", MODE_STANDALONE),
        ("file.new-project", MODE_PROJECT),
        ("schema.edit-xsd", MODE_MAINTENANCE),
        ("schema.import-xsd", MODE_MAINTENANCE),
    ],
)
def test_a_pick_reports_the_mode_of_its_column(command_id, mode):
    dialog = LauncherDialog(_fake_entries(_all_group_ids()))
    dialog.choose(command_id)
    assert dialog.chosen_workflow_mode == mode


def test_an_ad_hoc_column_names_no_mode():
    """`groups=` is a test/caller seam; a column outside the taxonomy must not
    invent a mode. `dismissable=True` because BUG-059's undismissable regime
    REFUSES a mode-less pick — see
    `test_an_undismissable_launcher_refuses_a_pick_that_names_no_mode`."""
    dialog = LauncherDialog(
        _fake_entries(["file.open"]),
        groups=(("Whatever", ("file.open",)),),
        dismissable=True,
    )
    dialog.choose("file.open")
    assert dialog.chosen_workflow_mode is None


def test_show_launcher_triggers_the_chosen_action_and_returns_its_id(tmp_path):
    fired = []
    entries = _fake_entries(_all_group_ids(), fired)
    settings = _ini_settings(tmp_path)
    chosen = show_launcher(
        None,
        settings,
        resolve_entries=lambda _window: entries,
        exec_dialog=lambda dialog: dialog.choose("file.new-project"),
    )
    assert chosen == "file.new-project"
    assert fired == ["file.new-project"]


def test_show_launcher_runs_the_menus_own_action(qtbot, tmp_path):
    """End-to-end against a real window: picking Standalone's first entry
    triggers `File ▸ Open...`, whose slot is replaced so no QFileDialog is
    reached."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    opened = []
    window._doc_ui.open_dialog = lambda: opened.append(True)
    show_launcher(
        window,
        window._settings,
        exec_dialog=lambda dialog: dialog.choose("file.open"),
    )
    assert opened == [True]


# -- BUG-059: two regimes -- obligatory choice, then dismissable -------------
#
# Owner ruling: "do not permit to close the launcher without having chosen a
# mode. If launcher is opened with a mode already chosen (new session), let it be
# closed, otherwise make choice obligatory. this means that also window close
# button must be disabled". `MainWindow._workflow_mode` starts as None and is
# never read from settings (FQ-027), so a dismissable startup launcher was the
# one path into the invalid "No Mode" state.


def test_undismissable_is_the_default_regime():
    """The safe regime is the DEFAULT: a caller must ask for dismissability
    rather than remember to forbid it."""
    assert LauncherDialog(_fake_entries(["file.open"])).dismissable is False


def test_an_undismissable_launcher_offers_no_close_button():
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    assert dialog.button_box.buttons() == []
    assert (
        dialog.button_box.button(QDialogButtonBox.StandardButton.Close) is None
    )


def test_an_undismissable_launcher_drops_the_native_close_button_hints():
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    flags = dialog.windowFlags()
    assert not flags & Qt.WindowType.WindowCloseButtonHint
    assert not flags & Qt.WindowType.WindowContextHelpButtonHint


def test_an_undismissable_launcher_refuses_a_close_event():
    """The AUTHORITATIVE barrier: the window-flag hint is advisory and covers
    neither Alt+F4 nor a window-manager close, both of which arrive here."""
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    # `result()` starts at 0, which IS `Rejected`, so the observable that
    # distinguishes "never dismissed" from "dismissed" is `finished`.
    finished = []
    dialog.finished.connect(finished.append)
    event = QCloseEvent()
    event.accept()
    dialog.closeEvent(event)
    assert event.isAccepted() is False
    assert dialog.close() is False
    assert finished == []


def test_an_undismissable_launcher_swallows_escape_reject_and_cancel():
    """Every dismissal funnel is inert, so there is no exit without a pick —
    "No Mode" is unreachable rather than merely unlikely."""
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    finished = []
    dialog.finished.connect(finished.append)

    dialog.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    )
    dialog.cancel()
    dialog.reject()
    dialog.button_box.rejected.emit()

    assert dialog.chosen_command_id is None
    assert finished == []


def test_an_undismissable_launcher_still_accepts_a_pick():
    dialog = LauncherDialog(_fake_entries(_all_group_ids()))
    dialog.choose("file.new-project")
    assert dialog.chosen_command_id == "file.new-project"
    assert dialog.chosen_workflow_mode == MODE_PROJECT
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_an_undismissable_launcher_refuses_a_pick_that_names_no_mode():
    """The other half of unreachability: the only way OUT is an accept, and an
    accept must carry a mode. Only an ad-hoc `groups=` column can fail this."""
    dialog = LauncherDialog(
        _fake_entries(["file.open"]), groups=(("Whatever", ("file.open",)),)
    )
    dialog.choose("file.open")
    assert dialog.chosen_command_id is None
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_a_dismissable_launcher_keeps_its_close_button_and_cancels():
    dialog = LauncherDialog(_fake_entries(["file.open"]), dismissable=True)
    assert dialog.button_box.button(QDialogButtonBox.StandardButton.Close) is not None
    assert dialog.windowFlags() & Qt.WindowType.WindowCloseButtonHint
    dialog.cancel()
    assert dialog.chosen_command_id is None
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_a_dismissable_launchers_close_button_is_wired_to_reject():
    dialog = LauncherDialog(_fake_entries(["file.open"]), dismissable=True)
    dialog.button_box.rejected.emit()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.chosen_command_id is None


def test_a_dismissable_launcher_accepts_a_close_event():
    dialog = LauncherDialog(_fake_entries(["file.open"]), dismissable=True)
    event = QCloseEvent()
    event.accept()
    dialog.closeEvent(event)
    assert event.isAccepted() is True


def test_show_launcher_derives_the_regime_from_the_windows_mode(qtbot, tmp_path):
    """ONE rule, in ONE place: no mode -> obligatory choice; a mode already
    chosen -> dismissable. No caller can open a dismissable launcher over a
    mode-less window."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    seen = []

    def _run(dialog):
        seen.append(dialog.dismissable)
        dialog.choose("file.open")

    show_launcher(
        window,
        window._settings,
        resolve_entries=lambda _w: _fake_entries(_all_group_ids()),
        exec_dialog=_run,
    )
    assert seen == [False]  # started with no mode

    show_launcher(
        window,
        window._settings,
        resolve_entries=lambda _w: _fake_entries(_all_group_ids()),
        exec_dialog=_run,
    )
    assert seen == [False, True]  # the first pick left a mode behind


def test_escape_lands_in_the_app_rather_than_quitting(qtbot, tmp_path):
    """FQ-010: cancelling must leave the window up and running. Nothing here
    closes, hides or quits anything — the app is simply still there. Reachable
    only once a mode is set (BUG-059), and the cancel RETAINS that mode."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()
    window.set_workflow_mode(MODE_STANDALONE)
    fired = []
    result = show_launcher(
        window,
        window._settings,
        resolve_entries=lambda _w: _fake_entries(_all_group_ids(), fired),
        exec_dialog=lambda dialog: dialog.cancel(),
    )
    assert result is None
    assert fired == []
    assert window.isVisible() is True
    assert window.workflow_mode == MODE_STANDALONE


def test_a_startup_launcher_cannot_be_left_without_a_mode(qtbot, tmp_path):
    """The end-to-end statement of the fix: over a mode-less window, every
    dismissal gesture fails and the mode is only ever set by a pick."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    assert window.workflow_mode is None

    def _try_to_escape(dialog):
        dialog.cancel()
        dialog.reject()
        dialog.close()
        dialog.keyPressEvent(
            QKeyEvent(
                QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
            )
        )
        assert dialog.chosen_command_id is None
        # The only way out:
        dialog.choose("file.open")

    result = show_launcher(
        window,
        window._settings,
        resolve_entries=lambda _w: _fake_entries(_all_group_ids()),
        exec_dialog=_try_to_escape,
    )
    assert result == "file.open"
    assert window.workflow_mode == MODE_STANDALONE


# -- the session workflow mode (FQ-027) --------------------------------------


def test_picking_a_column_records_its_mode_on_the_window(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    show_launcher(
        window,
        window._settings,
        resolve_entries=lambda _w: _fake_entries(_all_group_ids()),
        exec_dialog=lambda dialog: dialog.choose("schema.edit-xsd"),
    )
    assert window.workflow_mode == MODE_MAINTENANCE
    assert window.in_maintenance_mode() is True


@pytest.mark.parametrize("command_id", ["file.open", "file.new-project"])
def test_standalone_and_project_leave_the_full_menu_bar_in_place(
    qtbot, tmp_path, command_id
):
    """"Project and standalone are OK for now" — only Maintenance filters."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    before = _unfiltered_window_labels(window)
    show_launcher(
        window,
        window._settings,
        resolve_entries=lambda _w: _fake_entries(_all_group_ids()),
        exec_dialog=lambda dialog: dialog.choose(command_id),
    )
    assert window.in_maintenance_mode() is False
    assert _visible_labels(window.menuBar()) == before


def test_maintenance_hides_view_database_tools_and_generation(qtbot, tmp_path):
    """The corrected hidden set. FQ-027's own list (`File · Edit · View · Schema
    · Database · Tools · Bookmarks · Generation · Help`) is stale: FQ-016
    dissolved `Edit`, and FQ-021 renamed `Bookmarks` to `Navigation` and moved it
    to the Editor bar."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.set_workflow_mode(MODE_MAINTENANCE)
    assert _visible_labels(window.menuBar()) == ["File", "Schema", "Settings", "Help"]
    assert list(_MAINTENANCE_MENU_TITLES) == ["File", "Schema", "Help"]
    hidden = [
        title
        for title in window_menu_titles(window)
        if find_top_menu(window, title).menuAction().isVisible() is False
    ]
    assert hidden == ["View", "Database", "Tools", "Generation"]


def test_schema_and_help_survive_whole_and_ungated(qtbot, tmp_path):
    """File is the only menu that survives PARTIALLY."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    before = {
        title: action_labels(find_top_menu(window, title))
        for title in ("Schema", "Help")
    }
    window.set_workflow_mode(MODE_MAINTENANCE)
    for title, labels in before.items():
        menu = find_top_menu(window, title)
        assert [a.text() for a in menu.actions() if not a.isSeparator()] == [
            label for label in labels if label != "―"
        ]
        assert all(a.isVisible() for a in menu.actions())


def test_the_editor_menu_bar_is_out_of_the_filters_scope(qtbot, tmp_path):
    """Scope is the WINDOW menu bar. The Editor bar keeps every menu — which is
    what leaves `Deployment ▸ Save XSD` reachable, so an XSD edit can be saved
    without leaving the mode. `Navigation` in particular must not be touched:
    FQ-027 named it (as "Bookmarks") but it lives on this bar."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    before = editor_menu_titles(window)
    window.center_stage.setCurrentIndex(window.center_stage.xsd_tab_index)
    window.set_workflow_mode(MODE_MAINTENANCE)

    assert _visible_labels(window.editor_menu_bar) == before
    assert "Navigation" in before
    # `isHidden`, not `isVisible`: an unshown window's children are all
    # "invisible" regardless, so only an explicit hide would be evidence.
    assert window.editor_menu_bar.isHidden() is False
    save_xsd = find_action(find_top_menu(window, "Deployment"), "Save XSD")
    assert save_xsd is not None and save_xsd.isVisible() is True


def test_maintenance_trims_the_file_menu_to_new_session_and_exit(qtbot, tmp_path):
    """FQ-027 said New Session + Save + Save All, but FQ-020 deleted
    `File ▸ Save`/`Save As…` and `Save All` has never existed anywhere in the
    app — neither is invented here.

    `Exit` survives, per §7's membership table: a mode that hides the way out of
    the APPLICATION is the same trap `New Session` exists to prevent, one level
    up. The window's close button always worked, but a File menu with no Exit
    reads as a broken app rather than a focused one."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.set_workflow_mode(MODE_MAINTENANCE)
    assert _visible_labels(window._file_menu) == ["New Session", "Exit"]
    assert _MAINTENANCE_FILE_ITEMS == ("New Session", "Exit")
    # Separators go with the entries they used to divide.
    assert [
        a for a in window._file_menu.actions() if a.isSeparator() and a.isVisible()
    ] == []


def test_maintenance_mode_suppresses_a_hidden_FILE_entrys_shortcut(qtbot, tmp_path):
    """A user-assigned key on a File entry the mode trims away stops firing.

    `manual-maintainer` refused to answer this from inference, correctly — Qt's
    behaviour for a hidden QAction's shortcut is stated nowhere in the spec and
    nothing covered it. It follows from a fact FQ-027 already had to work
    around: `QAction.isEnabled()` returns False for a hidden action in PySide6,
    and Qt dispatches a shortcut only to an ENABLED action.

    The specimen is a USER-ASSIGNED key (FQ-012), which is now the only kind
    there is: the File menu shed `Ctrl+O` and `Ctrl+W` on 2026-08-09, so nothing
    the mode hides ships with a default. That makes this the more honest test —
    it exercises the real interaction between the two features.
    """
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.apply_and_save_shortcut_overrides({"file.close": "Ctrl+Alt+K"})
    action = window._toolbar_ui.menu_commands["file.close"]
    assert action.isEnabled() is True

    window.set_workflow_mode(MODE_MAINTENANCE)

    assert action.isVisible() is False
    assert action.isEnabled() is False  # ...so Qt will not fire Ctrl+Alt+K
    # The binding itself is untouched -- the command is hidden, not rebound, so
    # leaving the mode restores the key without re-assigning anything.
    assert action.shortcut().toString() == "Ctrl+Alt+K"

    window.set_workflow_mode(None)
    assert action.isEnabled() is True


def test_a_hidden_WHOLE_MENUS_shortcuts_still_fire_KNOWN_GAP(qtbot, tmp_path):
    """The mode hides `View`/`Database`/`Tools`/`Generation` by hiding the
    top-level QMenu, not its members — so their child actions stay visible and
    ENABLED, and Qt still dispatches their shortcuts.

    **This pins a known gap, not a desired behaviour.** The two halves of the
    filter disagree: `File` is trimmed member-by-member, so a hidden File
    command genuinely loses its key (the test above), while a command inside a
    hidden menu keeps one. A user who assigns a key to `View ▸ Customize
    Toolbar…` can still fire it in Maintenance mode, which is the "filters what
    you can SEE but not what you can DO" case the mode is supposed to avoid.

    It is NOT fixed here because the obvious fix collides with an owner ruling:
    hiding the child actions would also strip any pinned TOOLBAR button for
    them, and FQ-027's Q2 answer was explicitly "menu bar only, leave the
    toolbar alone". Recorded for the owner rather than guessed at.
    """
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.apply_and_save_shortcut_overrides({"view.customize-toolbar": "Ctrl+Alt+T"})
    action = window._toolbar_ui.menu_commands["view.customize-toolbar"]

    window.set_workflow_mode(MODE_MAINTENANCE)

    view_menu = find_top_menu(window, "View")
    assert view_menu.menuAction().isVisible() is False  # the MENU is gone...
    assert action.isVisible() is True  # ...but its members are not
    assert action.isEnabled() is True  # ...so Ctrl+Alt+T still fires


def test_the_two_never_hidden_surfaces_are_reachable_in_maintenance(qtbot, tmp_path):
    """The anti-trap rule, asserted directly rather than inferred from the menu
    lists: `Help ▸ Manual` (F1) is the only documentation explaining why commands
    are missing, and `File ▸ New Session` is the only way out of the mode. If
    either could be filtered out the app could hide its own exit."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.set_workflow_mode(MODE_MAINTENANCE)

    help_menu = find_top_menu(window, "Help")
    assert help_menu.menuAction().isVisible() is True
    manual = find_action(help_menu, "Manual")
    assert manual is not None and manual.isVisible() is True
    assert manual.shortcut().toString() == "F1"

    file_menu = find_top_menu(window, "File")
    assert file_menu.menuAction().isVisible() is True
    new_session = find_action(file_menu, "New Session")
    assert new_session is not None and new_session.isVisible() is True


def test_leaving_maintenance_restores_every_menu(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window_before = _unfiltered_window_labels(window)
    editor_before = editor_menu_titles(window)
    file_before = action_labels(window._file_menu)

    window.set_workflow_mode(MODE_MAINTENANCE)
    window.set_workflow_mode(None)

    assert _visible_labels(window.menuBar()) == window_before
    assert _visible_labels(window.editor_menu_bar) == editor_before
    assert action_labels(window._file_menu) == file_before
    assert all(a.isVisible() for a in window._file_menu.actions())


def test_the_mode_never_touches_enabled_state(qtbot, tmp_path):
    """Visibility only: the app has exactly two postures (present / absent) and
    Maintenance mode must not introduce a third — no greying out.

    Two assertions, because Qt makes the direct one impossible on its own:
    `QAction::isEnabled()` reports False for a hidden action, so an
    absent-because-hidden command is indistinguishable from a disabled one by
    reading the property. So (a) the filter's own code contains no `setEnabled`
    at all, and (b) every enabled state is exactly what it was once the mode is
    left — a real `setEnabled` would not undo itself.
    """
    import inspect

    source = inspect.getsource(MainWindow._refresh_workflow_mode_affordances)
    assert "setEnabled" not in source
    assert "setVisible" in source

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    everything = [
        *window.menuBar().actions(),
        *window.editor_menu_bar.actions(),
        *window._file_menu.actions(),
    ]
    before = {id(a): a.isEnabled() for a in everything}
    window.set_workflow_mode(MODE_MAINTENANCE)
    window.set_workflow_mode(None)
    assert {id(a): a.isEnabled() for a in everything} == before


def test_menu_actions_are_the_same_objects_across_a_mode_toggle(qtbot, tmp_path):
    """Build once, `setVisible`-toggle. An action rebuilt per mode would drop out
    of `collect_menu_commands()` while hidden and take saved `toolbarIds` with
    it (`_build_deployment_menu`'s rule, same reason)."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    before = [id(a) for a in window.menuBar().actions()]
    before += [id(a) for a in window.editor_menu_bar.actions()]
    before += [id(a) for a in window._file_menu.actions()]

    window.set_workflow_mode(MODE_MAINTENANCE)
    window.set_workflow_mode(None)

    after = [id(a) for a in window.menuBar().actions()]
    after += [id(a) for a in window.editor_menu_bar.actions()]
    after += [id(a) for a in window._file_menu.actions()]
    assert after == before


def test_a_hidden_command_still_enumerates_for_customize_toolbar(qtbot, tmp_path):
    """`ToolbarController._walk_menu_actions` never tests `isVisible()`, which is
    exactly why the filter may hide actions at all: a pinned button keeps
    working, and the Available list does not depend on the mode."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    before = dict(window._toolbar_ui.collect_menu_commands())
    window.set_workflow_mode(MODE_MAINTENANCE)
    after = dict(window._toolbar_ui.collect_menu_commands())
    assert after == before
    # A DEFAULT toolbar button whose menu is hidden in this mode:
    assert "generation.generate-php" in after


def test_the_mode_does_not_survive_a_restart(qtbot, tmp_path):
    """SESSION-ONLY (FQ-027 superseding FQ-011): no QSettings key, so a window
    built from the SAME settings store after a Maintenance session starts
    unfiltered. This is what makes the mode unable to strand a user."""
    settings = _ini_settings(tmp_path)
    first = MainWindow(settings=settings)
    qtbot.addWidget(first)
    first.set_workflow_mode(MODE_MAINTENANCE)
    assert _visible_labels(first.menuBar()) == ["File", "Schema", "Settings", "Help"]
    settings.sync()

    second = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(second)
    assert second.workflow_mode is None
    assert second.in_maintenance_mode() is False
    assert _visible_labels(second.menuBar()) == _unfiltered_window_labels(second)
    assert _visible_labels(second._file_menu) == [
        a.text() for a in second._file_menu.actions() if not a.isSeparator()
    ]
    # And nothing about the mode was ever written down.
    assert [k for k in settings.allKeys() if "mode" in k.lower()] == []


def test_switching_tabs_does_not_undo_the_filter(qtbot, tmp_path):
    """The other refreshers run on every `currentChanged`; none of them may put
    a filtered window menu back."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.set_workflow_mode(MODE_MAINTENANCE)
    for index in (
        window.center_stage.raw_xml_tab_index,
        window.center_stage.xsd_tab_index,
    ):
        window.center_stage.setCurrentIndex(index)
        assert _visible_labels(window.menuBar()) == ["File", "Schema", "Settings", "Help"]


# -- File ▸ New Session ------------------------------------------------------


def test_show_launcher_is_gone_and_new_session_took_its_place(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    assert find_action(file_menu, "Show Launcher…") is None
    assert find_action(file_menu, "New Session") is not None


def test_a_toolbar_saved_before_the_rename_still_resolves(qtbot, tmp_path):
    """The rename is an id change (a command id IS its whole menu path), so a
    pinned button survives it only via `RENAMED_ID_ALIASES` — and the row must be
    in THAT table, never `LEGACY_ID_ALIASES` (which is inverted into
    `ICON_ID_BY_COMMAND`)."""
    assert toolbar_registry.RENAMED_ID_ALIASES["file.show-launcher"] == (
        "file.new-session"
    )
    assert "file.show-launcher" not in toolbar_registry.LEGACY_ID_ALIASES

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    known = dict(window._toolbar_ui.collect_menu_commands())
    assert "file.new-session" in known
    assert "file.show-launcher" not in known
    assert toolbar_registry.resolve_ids(["file.show-launcher"], known) == [
        "file.new-session"
    ]


def test_new_session_retains_the_mode_and_reopens_the_launcher(qtbot, tmp_path):
    """BUG-059 REVERSED FQ-027's clear-then-show. The mode STANDS while the
    re-opened launcher is up — that is what makes this launcher dismissable at
    all, and it is what a dismissal lands in. Clearing it was the one production
    path into the invalid "No Mode" state."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.set_workflow_mode(MODE_MAINTENANCE)
    shown = []
    window.show_launcher = lambda: shown.append(window.workflow_mode)

    assert find_action(find_top_menu(window, "File"), "New Session").trigger() is None

    assert shown == [MODE_MAINTENANCE]
    assert window.workflow_mode == MODE_MAINTENANCE


def test_new_session_never_passes_none_to_set_workflow_mode(qtbot, tmp_path):
    """The invalid state is made unrepresentable by removing the WRITE, not by
    checking for it afterwards: no user gesture sets the mode back to None."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.set_workflow_mode(MODE_MAINTENANCE)
    window.show_launcher = lambda: None
    modes = []
    original = window.set_workflow_mode
    window.set_workflow_mode = lambda mode: (modes.append(mode), original(mode))[1]

    assert window.new_session() is True

    assert modes == []


def test_a_maintenance_launcher_still_offers_every_column(qtbot, tmp_path):
    """The consequence of retaining the mode: the launcher goes up over a
    TRIMMED menu bar. That is safe because `_walk_menu_actions` never tests
    `isVisible()`, so all six entries are still resolved and offered."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.set_workflow_mode(MODE_MAINTENANCE)

    entries = resolve_menu_entries(window)

    for command_id in _all_group_ids():
        assert command_id in entries


def test_new_session_closes_the_document_and_the_project(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.show_launcher = lambda: None
    calls = []
    window._doc_ui.close = lambda: calls.append("doc")
    window._ddl_project_ui.close_project = lambda: calls.append("project")
    assert window.new_session() is True
    assert calls == ["doc", "project"]


def test_a_cancelled_unsaved_prompt_aborts_new_session(qtbot, tmp_path):
    """Every cancel aborts the WHOLE gesture: nothing is closed, the mode is
    untouched and the launcher never goes up."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.set_workflow_mode(MODE_MAINTENANCE)
    shown = []
    window.show_launcher = lambda: shown.append(True)
    closed = []
    window._ddl_project_ui.close_project = lambda: closed.append(True)
    window._xsd_ui.confirm_close_for_exit = lambda: False

    assert window.new_session() is False
    assert shown == [] and closed == []
    assert window.workflow_mode == MODE_MAINTENANCE


def test_a_cancelled_document_close_aborts_new_session(qtbot, tmp_path):
    """The document lane reports a cancel by leaving the buffer dirty."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    shown = []
    window.show_launcher = lambda: shown.append(True)
    window._doc_ui.set_dirty(True)
    window._doc_ui.close = lambda: None  # a cancelled prompt changes nothing
    assert window.new_session() is False
    assert shown == []


# -- the hard constraint: MainWindow construction never reaches a modal ------


def test_constructing_a_main_window_never_shows_the_launcher(
    qtbot, tmp_path, monkeypatch
):
    """FQ-010's first hard constraint. 49 test files construct a MainWindow; if
    the launcher were shown from __init__ every one of them would hang."""
    import pgtp_editor.ui.launcher_dialog as launcher_mod

    def _boom(*args, **kwargs):
        raise AssertionError("MainWindow.__init__ must never show the launcher")

    monkeypatch.setattr(launcher_mod, "show_launcher", _boom)
    monkeypatch.setattr(launcher_mod.LauncherDialog, "exec", _boom, raising=False)

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()
    assert window.isVisible() is True


def test_new_session_reopens_the_launcher_with_no_force_argument(
    qtbot, tmp_path, monkeypatch
):
    """A USER-triggered modal. There is no `force=` any more — FQ-027 deleted the
    suppression it existed to bypass, so the launcher always shows."""
    import pgtp_editor.ui.launcher_dialog as launcher_mod

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)

    calls = []
    monkeypatch.setattr(
        launcher_mod,
        "show_launcher",
        lambda win, settings, **kwargs: calls.append((win, settings, kwargs)),
    )
    find_action(find_top_menu(window, "File"), "New Session").trigger()

    assert len(calls) == 1
    win, settings, kwargs = calls[0]
    assert win is window
    assert settings is window._settings
    assert kwargs == {}
