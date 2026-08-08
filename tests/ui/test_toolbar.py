"""Sub-project E -- the customizable toolbar, owned by `ToolbarController`.

The lane lives in `ui/toolbar_controller.py` and is reached as
`window._toolbar_ui`; `MainWindow` keeps only `addToolBar`/`menuBar()` (the
`QMainWindow` gestures) and hands both to `ToolbarController.build`. These tests
still drive a real `MainWindow` because the command universe *is* its live menu
bar — the assertions are unchanged from before the extraction, only retargeted.

QSettings is isolated via an injected temp ini file.

BUG-027 widened the available command set from a hardcoded seven to every menu
command, and changed ids from bare names (`save`) to menu paths (`file.save`).
Toolbar buttons are now the menus' OWN QActions, so the labels these tests
assert are the real menu labels ("Open...", "Validate Project", ...) rather
than the old registry's tidied-up ones.
"""
from PySide6.QtCore import QSettings

from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.toolbar_registry import DEFAULT_TOOLBAR_IDS
from tests.ui._menu_helpers import find_action, find_top_menu


# FIVE, down from the original seven: `Find...` retired with FQ-016 (the Edit menu
# dissolved and Find became a permanently visible bar, knowingly unpinnable) and
# `Save` with FQ-020 (`File ▸ Save` is deleted and its four per-tab successors on
# the `Deployment` menu are tab-gated, so none of them may be a DEFAULT button --
# the app ships with no save button at all). Undo/Redo/Validate Project live on the
# Editor menu bar, which is why the walk must cover both bars.
DEFAULT_LABELS = [
    "Open...",
    "Undo",
    "Redo",
    "Validate Project",
    "Generate PHP...",
]


def _ini_settings(tmp_path, name="s.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


def _toolbar_labels(window):
    return [a.text() for a in window._toolbar_ui.toolbar.actions()]


def test_default_toolbar_has_every_default_action_in_order(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == DEFAULT_LABELS
    assert window._toolbar_ui.toolbar.objectName() == "main_toolbar"


def test_no_default_toolbar_button_ships_empty_or_iconless(qtbot, tmp_path):
    """The FQ-016 alias hazard, pinned: `DEFAULT_TOOLBAR_IDS` derives from
    `LEGACY_ID_ALIASES` and `ICON_ID_BY_COMMAND` is its inverse, so an alias left
    pointing at a moved command's OLD menu path would silently ship a default
    button with no action behind it and no icon on it."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    actions = window._toolbar_ui.toolbar.actions()
    assert len(actions) == len(DEFAULT_TOOLBAR_IDS)
    for command_id, action in zip(DEFAULT_TOOLBAR_IDS, actions):
        assert command_id in window._toolbar_ui.menu_commands, command_id
        assert action is window._toolbar_ui.menu_commands[command_id]
        assert action.text()
        assert not action.icon().isNull(), command_id


def test_apply_toolbar_ids_reorders_and_subsets(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_ids(["deployment.save-pgtp", "file.open"])
    assert _toolbar_labels(window) == ["Save pgtp", "Open..."]
    assert window._toolbar_ui.command_ids == ["deployment.save-pgtp", "file.open"]


def test_apply_toolbar_ids_drops_unknowns(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    # "edit.find" is a now-dead id (FQ-016) and is dropped exactly like "bogus".
    window._toolbar_ui.apply_ids(["parsing.validate-project", "bogus", "edit.find"])
    assert _toolbar_labels(window) == ["Validate Project"]


def test_toolbar_action_is_the_menu_action_itself(qtbot, tmp_path):
    """BUG-027: the toolbar hosts the real menu QAction rather than a parallel
    copy wired through a slot table -- that's what makes the button share the
    menu item's slot, enabled state and shortcut."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_ids(["parsing.validate-project"])
    menu_action = find_action(find_top_menu(window, "Parsing"), "Validate Project")
    assert window._toolbar_ui.toolbar.actions() == [menu_action]


def test_toolbar_action_triggers_slot(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    called = []
    window._toolbar_ui.apply_ids(["parsing.validate-project"])
    # The shared action carries the menu's connection; add our own spy to it
    # rather than patching the bound slot, which would not rewire it.
    window._toolbar_ui.toolbar.actions()[0].triggered.connect(lambda: called.append(True))
    window._toolbar_ui.toolbar.actions()[0].trigger()
    assert called == [True]


def test_apply_and_save_persists_and_round_trips(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._toolbar_ui.apply_and_save(["history.undo", "deployment.save-pgtp"])
    assert _toolbar_labels(window) == ["Undo", "Save pgtp"]

    # A new window reading the same store restores that toolbar.
    settings2 = _ini_settings(tmp_path)
    window2 = MainWindow(settings=settings2)
    qtbot.addWidget(window2)
    assert _toolbar_labels(window2) == ["Undo", "Save pgtp"]


def test_stored_comma_string_is_restored(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", "history.undo,history.redo")
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == ["Undo", "Redo"]


def test_unknown_stored_ids_are_dropped(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", ["deployment.save-pgtp", "bogus", "file.open"])
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == ["Save pgtp", "Open..."]


def test_empty_stored_ids_fall_back_to_default(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", ["bogus", "nope"])
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert window._toolbar_ui.command_ids == DEFAULT_TOOLBAR_IDS


def test_no_stored_ids_uses_default(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    assert window._toolbar_ui.command_ids == DEFAULT_TOOLBAR_IDS


# -- BUG-027: the available set is every menu command ----------------------
def test_available_commands_come_from_the_menus_not_a_fixed_seven(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    pairs = window._toolbar_ui.all_menu_commands()
    ids = [command_id for command_id, _label in pairs]

    assert len(pairs) > 7                       # the reported bug: only 7 commands
    # Commands that were previously impossible to put on the toolbar:
    for command_id in ("deployment.save-as-new-pgtp", "history.history", "navigation.next-bookmark"):
        assert command_id in ids
    # ...alongside the legacy seven, which must all still be offered.
    for command_id in DEFAULT_TOOLBAR_IDS:
        assert command_id in ids


def test_the_walk_covers_BOTH_menu_bars(qtbot, tmp_path):
    """FQ-016: `build` takes a SEQUENCE of menu-bar roots (one walk, widened).
    Without the second root every Editor-bar command would be unpinnable and
    invisible to Customize Toolbar and to FQ-004's icon assignments."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    pairs = window._toolbar_ui.all_menu_commands()
    ids = [command_id for command_id, _label in pairs]
    labels = dict(pairs)

    # Window bar...
    assert "file.open" in ids
    # ...and the Editor bar's four-menu inventory (Select is FQ-015's lane).
    # The bookmark members read `navigation.*` since FQ-021 retitled their menu.
    for command_id in (
        "history.history", "history.undo", "history.redo",
        "parsing.auto-parse-xml", "parsing.validate-project",
        "navigation.toggle-bookmark", "navigation.next-bookmark",
        "navigation.previous-bookmark", "navigation.clear-all-bookmarks",
    ):
        assert command_id in ids, command_id
    assert labels["history.undo"] == "History › Undo"
    assert labels["parsing.validate-project"] == "Parsing › Validate Project"
    # Window-bar roots come first, so a walk that dropped one is visible in order.
    assert ids.index("file.open") < ids.index("history.history")


def test_the_walk_accepts_a_single_menu_bar_too(qtbot, tmp_path):
    """`build` keeps the one-bar form so a caller with a single bar needs no
    ceremony -- the widening is a sequence of roots, not a new mechanism."""
    from pgtp_editor.ui.toolbar_controller import ToolbarController

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    lane = ToolbarController(window._shell, parent=window)
    lane.build(window.editor_menu_bar, window.addToolBar)
    ids = [command_id for command_id, _label in lane.all_menu_commands()]
    assert "history.undo" in ids
    assert "file.open" not in ids


def test_menu_command_labels_show_their_menu_path(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    labels = dict(window._toolbar_ui.all_menu_commands())
    assert labels["deployment.save-as-new-pgtp"] == "Deployment › Save as new pgtp"


def test_menu_command_ids_are_unique(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    ids = [command_id for command_id, _label in window._toolbar_ui.all_menu_commands()]
    assert len(ids) == len(set(ids))


def test_no_recent_files_command_exists_at_all(qtbot, tmp_path):
    """FQ-010 deleted `File ▸ Open Recent` and the store behind it, and with it
    §7's rule that its transient children must never be pinnable. Nothing
    recent-shaped is offered because nothing recent-shaped exists."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    ids = [command_id for command_id, _label in window._toolbar_ui.all_menu_commands()]
    assert not [command_id for command_id in ids if "recent" in command_id.lower()]


def test_separators_are_not_offered(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    for command_id, label in window._toolbar_ui.all_menu_commands():
        assert command_id and label


def test_a_previously_unavailable_command_can_go_on_the_toolbar(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_and_save(["deployment.save-as-new-pgtp"])
    assert _toolbar_labels(window) == ["Save as new pgtp"]
    assert window._toolbar_ui.toolbar.actions()[0] is find_action(
        find_top_menu(window, "Deployment"), "Save as new pgtp"
    )


def test_checkable_menu_toggle_stays_checkable_on_the_toolbar(qtbot, tmp_path):
    """Reusing the real action means a View-menu dock toggle keeps its
    checked state in sync between menu and toolbar for free."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_ids(["view.light-theme"])
    action = window._toolbar_ui.toolbar.actions()[0]
    assert action.isCheckable()
    assert action is find_action(find_top_menu(window, "View"), "Light Theme")


# -- BUG-027: saved toolbars from before the widening ----------------------
def test_legacy_stored_ids_still_restore(qtbot, tmp_path):
    """Pre-BUG-027 installs stored bare ids. Without alias mapping every one of
    those users would launch to a toolbar silently reset to the default."""
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", ["save", "find", "undo", "generate"])
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    # The RETIRED aliases resolve to nothing and are pruned, which is the
    # deliberate outcome in both cases: `find` has no menu home to alias onto
    # (FQ-016), and `save` no longer has one command to point at (FQ-020 -- the
    # four successors are per-tab). The ids AROUND them survive, so this user
    # loses two buttons rather than having the toolbar reset to the default.
    assert window._toolbar_ui.command_ids == [
        "history.undo",
        "generation.generate-php",
    ]
    assert _toolbar_labels(window) == ["Undo", "Generate PHP..."]


def test_legacy_comma_string_still_restores(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", "validate,generate")
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == ["Validate Project", "Generate PHP..."]


def test_customize_toolbar_action_in_view_menu(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    action = find_action(view_menu, "Customize Toolbar…")
    assert action is not None


def test_opening_customize_toolbar_does_not_block(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.open_customize_dialog()  # non-modal show(), must not raise/block
    assert window._toolbar_ui.customize_dialog is not None
    assert window._toolbar_ui.customize_dialog.selected_ids() == window._toolbar_ui.command_ids


def test_customize_dialog_is_offered_every_menu_command(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.open_customize_dialog()
    dialog = window._toolbar_ui.customize_dialog
    offered = dialog._available_ids()
    assert offered == [command_id for command_id, _label in window._toolbar_ui.all_menu_commands()]
    assert len(offered) > 7
    # Everything already on the toolbar is listed but greyed, never removed.
    assert set(window._toolbar_ui.command_ids).isdisjoint(dialog._available_enabled_ids())


def test_toolbar_shows_text_beside_icon(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    # Icon + label: the actions now carry Breeze icons alongside their text.
    assert (
        window._toolbar_ui.toolbar.toolButtonStyle()
        == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    )
    labels = [a.text() for a in window._toolbar_ui.toolbar.actions()]
    assert all(labels)  # no empty labels


def test_every_default_toolbar_action_has_a_non_null_icon(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    actions = window._toolbar_ui.toolbar.actions()
    assert actions
    assert all(not a.icon().isNull() for a in actions)


def test_icons_are_hidden_in_menus(qtbot, tmp_path):
    """BUG-027: the toolbar decorates a SHARED action, so the icon must be
    suppressed in the menu or adding a button would restyle the menu too."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    assert all(not a.isIconVisibleInMenu() for a in window._toolbar_ui.toolbar.actions())


def test_an_icon_less_command_is_still_addable(qtbot, tmp_path):
    """An icon must never be a precondition for toolbar membership -- only the
    legacy seven have vendored SVGs."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_ids(["deployment.save-as-new-pgtp"])
    action = window._toolbar_ui.toolbar.actions()[0]
    assert action.icon().isNull()
    assert action.text() == "Save as new pgtp"


def test_toggling_light_theme_keeps_icons_non_null(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._on_light_theme_toggled(True)
    actions = window._toolbar_ui.toolbar.actions()
    assert actions
    assert all(not a.icon().isNull() for a in actions)


# -- BUG-027: sharing the menus' QActions must not destroy them -------------
def test_repopulating_the_toolbar_does_not_destroy_the_menu_action(qtbot, tmp_path):
    """The load-bearing corollary of hosting the menus' OWN QActions:
    `QToolBar.clear()` DELETES them in PySide, taking the live menu item with
    it. Re-applying twice and then using the menu proves `removeAction` is
    used instead."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    validate = find_action(find_top_menu(window, "Parsing"), "Validate Project")

    window._toolbar_ui.apply_ids(["parsing.validate-project"])
    window._toolbar_ui.apply_ids(["deployment.save-pgtp"])          # drops validate again
    window._toolbar_ui.apply_ids(["parsing.validate-project"])

    # Still the same, still-alive object, still in the Parsing menu.
    assert window._toolbar_ui.toolbar.actions() == [validate]
    assert validate.text() == "Validate Project"
    assert find_action(find_top_menu(window, "Parsing"), "Validate Project") is validate
    called = []
    validate.triggered.connect(lambda: called.append(True))
    validate.trigger()
    assert called == [True]


def test_removed_toolbar_action_survives_and_stays_in_its_menu(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    save_as = find_action(find_top_menu(window, "Deployment"), "Save as new pgtp")
    window._toolbar_ui.apply_ids(["deployment.save-as-new-pgtp"])
    window._toolbar_ui.apply_ids(["deployment.save-pgtp"])
    assert save_as not in window._toolbar_ui.toolbar.actions()
    assert save_as.text() == "Save as new pgtp"          # C++ object still alive
    assert find_action(find_top_menu(window, "Deployment"), "Save as new pgtp") is save_as


def test_menu_walk_keepalive_survives_garbage_collection(qtbot, tmp_path):
    """`QAction.menu()` transfers the QMenu's ownership to Python, so a
    collected wrapper destroys the real menu and every action in it (this
    crashed startup on the first `_restore_theme` touch of the View menu).
    `_menu_keepalive` pins them; force a GC and then USE a submenu action."""
    import gc

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.collect_menu_commands()
    gc.collect()

    light = find_action(find_top_menu(window, "View"), "Light Theme")
    assert light is not None
    light.setChecked(light.isChecked())            # would raise if deleted
    # Every walked command is still a usable QAction after the collection.
    for command_id, _label in window._toolbar_ui.all_menu_commands():
        assert window._toolbar_ui.menu_commands[command_id].text()


def test_keepalive_is_never_cleared_when_recollecting(qtbot, tmp_path):
    """Re-enumeration (every Customize Toolbar open) must ADD to the pin list,
    never reset it — releasing the last reference is exactly what destroys the
    menus."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    first = list(window._toolbar_ui.menu_keepalive)
    assert first
    window._toolbar_ui.collect_menu_commands()
    window._toolbar_ui.collect_menu_commands()
    assert window._toolbar_ui.menu_keepalive[: len(first)] == first
    # Idempotent: re-walking pins no duplicates.
    assert len(window._toolbar_ui.menu_keepalive) == len(first)


# -- BUG-027: id derivation edge cases on the live menu bar -----------------
def test_duplicate_menu_labels_get_a_numeric_suffix(qtbot, tmp_path):
    """Two identically-labelled actions in one menu would collide on one id;
    the suffix rule keeps every id resolving to exactly one action."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    parsing = find_top_menu(window, "Parsing")
    original = find_action(parsing, "Validate Project")
    twin = parsing.addAction("Validate Project")

    pairs = window._toolbar_ui.collect_menu_commands()
    ids = [command_id for command_id, _label in pairs]
    assert "parsing.validate-project" in ids
    assert "parsing.validate-project-2" in ids
    assert len(ids) == len(set(ids))
    assert window._toolbar_ui.menu_commands["parsing.validate-project"] is original
    assert window._toolbar_ui.menu_commands["parsing.validate-project-2"] is twin

    parsing.removeAction(twin)


def test_customize_dialog_reenumerates_commands_added_after_startup(qtbot, tmp_path):
    """`open_customize_dialog` re-walks the menus, so a command the app grew
    since startup is offered without a restart."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    before = [command_id for command_id, _label in window._toolbar_ui.all_menu_commands()]
    assert "tools.brand-new-command" not in before

    tools = find_top_menu(window, "Tools")
    fresh = tools.addAction("Brand New Command")
    window._toolbar_ui.open_customize_dialog()
    offered = window._toolbar_ui.customize_dialog._available_ids()
    assert "tools.brand-new-command" in offered
    assert window._toolbar_ui.menu_commands["tools.brand-new-command"] is fresh

    tools.removeAction(fresh)


def test_submenu_commands_are_offered_with_their_full_path(qtbot, tmp_path):
    """The walk is depth-first over real submenus (since FQ-010 removed Open
    Recent the live menu bar has none, so this builds one), so a nested command
    gets a dotted id and a `›`-joined label — and the submenu placeholder itself
    is never a command."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    tools = find_top_menu(window, "Tools")
    submenu = tools.addMenu("Extra Stuff")
    nested_action = submenu.addAction("Deep Command")

    labels = dict(window._toolbar_ui.collect_menu_commands())
    assert labels["tools.extra-stuff.deep-command"] == "Tools › Extra Stuff › Deep Command"
    assert window._toolbar_ui.menu_commands["tools.extra-stuff.deep-command"] is nested_action
    # The placeholder action that merely opens the submenu is not a command.
    assert "tools.extra-stuff" not in labels

    window._toolbar_ui.apply_ids(["tools.extra-stuff.deep-command"])
    assert window._toolbar_ui.toolbar.actions() == [nested_action]


def test_no_offered_id_contains_uppercase_or_whitespace(qtbot, tmp_path):
    """Ids are slugs of the menu path — stable enough to persist in QSettings
    (they round-trip through a comma-joined string)."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    for command_id, _label in window._toolbar_ui.all_menu_commands():
        assert command_id == command_id.lower()
        assert " " not in command_id and "," not in command_id


# -- BUG-027: icons on a widened, mostly icon-less command set --------------
def test_refresh_toolbar_icons_tolerates_icon_less_commands(qtbot, tmp_path):
    """A theme flip re-tints the toolbar; with icon-less commands on it that
    must be a no-op for those, not a crash or a blanked icon."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    # Both `Deployment` entries are icon-less (FQ-020 retired the only save icon
    # DEFAULT), so `file.open` supplies the one command that does have an icon.
    window._toolbar_ui.apply_ids(
        ["deployment.save-as-new-pgtp", "deployment.save-pgtp", "file.open"]
    )
    window._toolbar_ui.refresh_icons()
    save_as, save, open_ = window._toolbar_ui.toolbar.actions()
    assert save_as.icon().isNull()
    assert save.icon().isNull()
    assert not open_.icon().isNull()


def test_icon_less_command_keeps_its_menu_icon_visibility(qtbot, tmp_path):
    """`setIconVisibleInMenu(False)` is only applied to actions we decorate;
    an icon-less command is left completely untouched."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    save_as = find_action(find_top_menu(window, "Deployment"), "Save as new pgtp")
    window._toolbar_ui.apply_ids(["deployment.save-as-new-pgtp"])
    assert save_as.isIconVisibleInMenu() is True


def test_saved_ids_are_menu_path_ids_in_settings(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._toolbar_ui.apply_and_save(["deployment.save-as-new-pgtp", "navigation.next-bookmark"])
    stored = settings.value("toolbarIds")
    stored = stored.split(",") if isinstance(stored, str) else list(stored)
    assert stored == ["deployment.save-as-new-pgtp", "navigation.next-bookmark"]


# --- FQ-004: per-command icon assignments ----------------------------------
def test_assigned_icon_overrides_the_legacy_default(qtbot, tmp_path):
    """Any button may be re-decorated, including the legacy seven."""
    from pgtp_editor.ui.toolbar_registry import icon_id_for

    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)

    # FQ-020 retired `save` from the alias table, so this command has NO default
    # icon -- an assigned one is the only icon it can have.
    assert icon_id_for("deployment.save-pgtp", {}) is None
    assert icon_id_for("deployment.save-pgtp", {"deployment.save-pgtp": "document-print"}) == "document-print"


def test_icon_assignments_round_trip_through_settings(qtbot, tmp_path):
    """Saved under a sibling key of toolbarIds, restored on the next window."""
    from pgtp_editor.ui.toolbar_registry import ICON_ASSIGNMENTS_SETTINGS_KEY

    path = str(tmp_path / "s.ini")
    window = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_and_save(
        window._toolbar_ui.command_ids, {"deployment.save-pgtp": "document-print"}
    )
    window._settings.sync()

    reopened = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(reopened)

    assert reopened._settings.value(ICON_ASSIGNMENTS_SETTINGS_KEY) is not None
    assert reopened._toolbar_ui.icon_ids.get("deployment.save-pgtp") == "document-print"


def test_an_unknown_assignment_is_dropped_on_load(qtbot, tmp_path):
    """Self-healing, the way resolve_ids already drops unknown ids: an
    assignment naming a command that no longer exists must not survive."""
    from pgtp_editor.ui.toolbar_registry import (
        ICON_ASSIGNMENTS_SETTINGS_KEY,
        serialize_icon_assignments,
    )

    path = str(tmp_path / "s.ini")
    seed = QSettings(path, QSettings.Format.IniFormat)
    seed.setValue(
        ICON_ASSIGNMENTS_SETTINGS_KEY,
        serialize_icon_assignments({"no.such.command": "document-print"}),
    )
    seed.sync()

    window = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(window)

    assert "no.such.command" not in window._toolbar_ui.icon_ids


# -- FQ-021: the Bookmarks -> Navigation rename, end to end -----------------
def test_a_bookmark_button_pinned_before_the_rename_survives_the_upgrade(
    qtbot, tmp_path
):
    """The whole point of FQ-021's `RENAMED_ID_ALIASES` rows, exercised the way a
    real upgrade hits them: a settings store written by a pre-rename build,
    opened by this one.

    Both keys are seeded, because they are resolved by different functions
    (`resolve_ids` for `toolbarIds`, `resolve_icon_assignments` for
    `toolbarIconIds`). A table consulted by only one of them would restore the
    button and silently drop the icon the user picked for it -- a half-fix that
    looks fine in a toolbar-only test.
    """
    from pgtp_editor.ui.toolbar_registry import (
        ICON_ASSIGNMENTS_SETTINGS_KEY,
        serialize_icon_assignments,
    )

    path = str(tmp_path / "s.ini")
    seed = QSettings(path, QSettings.Format.IniFormat)
    # What a pre-FQ-021 build stored: the menu was titled `Bookmarks`. The
    # neighbour is `file.open` rather than `file.save` because FQ-020 DELETED
    # the save command -- a deleted id is dropped by design, so using one here
    # would test that degradation instead of this rename's survival.
    seed.setValue("toolbarIds", ["file.open", "bookmarks.next-bookmark"])
    seed.setValue(
        ICON_ASSIGNMENTS_SETTINGS_KEY,
        serialize_icon_assignments({"bookmarks.next-bookmark": "zoom-in"}),
    )
    seed.sync()

    window = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(window)

    # The button is still there, under the id the menu now yields...
    assert window._toolbar_ui.command_ids == ["file.open", "navigation.next-bookmark"]
    assert _toolbar_labels(window) == ["Open...", "Next Bookmark"]
    # ...it is the real menu action, not an orphan...
    menu = find_top_menu(window, "Navigation")
    assert window._toolbar_ui.toolbar.actions()[1] is find_action(
        menu, "Next Bookmark"
    )
    # ...and it kept the icon, re-keyed onto the new id rather than left behind
    # under the old one.
    assert window._toolbar_ui.icon_ids.get("navigation.next-bookmark") == "zoom-in"
    assert "bookmarks.next-bookmark" not in window._toolbar_ui.icon_ids
    assert not window._toolbar_ui.toolbar.actions()[1].icon().isNull()


def test_the_navigation_menus_members_kept_their_own_labels(qtbot, tmp_path):
    """FQ-021 renamed the MENU only. If a member label had drifted too, its id
    would need a second rename row -- so this pins the boundary of the change."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    ids = dict(
        (label, command_id)
        for command_id, label in window._toolbar_ui.all_menu_commands()
    )
    assert ids["Navigation › Next Bookmark"] == "navigation.next-bookmark"
    assert ids["Navigation › List All Bookmarks"] == "navigation.list-all-bookmarks"


def test_no_menu_command_still_answers_to_a_bookmarks_prefixed_id(qtbot, tmp_path):
    """The rename is complete in the live menu: every `bookmarks.*` id exists
    only as a `RENAMED_ID_ALIASES` key now. A leftover would mean the menu title
    was changed in one place and not another."""
    from pgtp_editor.ui.toolbar_registry import RENAMED_ID_ALIASES

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    live = {command_id for command_id, _label in window._toolbar_ui.all_menu_commands()}

    assert not {cid for cid in live if cid.startswith("bookmarks.")}
    # ...and every rename row points at a command that really exists, so a typo
    # in the table is a failure here rather than a button that silently vanishes.
    for old_id, new_id in RENAMED_ID_ALIASES.items():
        assert new_id in live, (old_id, new_id)


# -- FQ-020: a toolbar saved before the Deployment menu ---------------------


def test_a_toolbar_saved_before_fq020_follows_the_moved_commands(qtbot, tmp_path):
    """FQ-020's three `RENAMED_ID_ALIASES` rows, exercised as a real upgrade:
    `Compare / Merge Two Files...` moved off Tools onto `Deployment`,
    `Deploy .pgtp` moved off File onto `Deployment`, and `File ▸ Revert` was
    re-specified as `Discard Changes`. All three still EXIST, so a pinned button
    must follow them — while `file.save`, which was DELETED, is dropped instead.
    Both degradations in one saved store, because they are easy to confuse.
    """
    path = str(tmp_path / "s.ini")
    seed = QSettings(path, QSettings.Format.IniFormat)
    seed.setValue(
        "toolbarIds",
        [
            "tools.compare-merge-two-files",
            "file.deploy-pgtp",
            "file.revert",
            "file.save",
        ],
    )
    seed.sync()

    window = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(window)

    assert window._toolbar_ui.command_ids == [
        "deployment.compare-merge-pgtp",
        "deployment.deploy-pgtp",
        "file.discard-changes",
    ]
    # ...and each button IS the live menu action, not an orphan with the right id.
    deployment = find_top_menu(window, "Deployment")
    assert window._toolbar_ui.toolbar.actions()[:2] == [
        find_action(deployment, "Compare/Merge pgtp"),
        find_action(deployment, "Deploy .pgtp"),
    ]
    assert window._toolbar_ui.toolbar.actions()[2] is find_action(
        find_top_menu(window, "File"), "Discard Changes"
    )


def test_no_live_menu_command_answers_to_a_deleted_save_id(qtbot, tmp_path):
    """The deletion is complete in the live menus, which is what makes the
    silent drop above the CORRECT degradation rather than a lost alias: nothing
    named `file.save`/`file.save-as` is enumerable any more, and neither old
    Tools id survives."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    live = {command_id for command_id, _label in window._toolbar_ui.all_menu_commands()}

    for gone in (
        "file.save",
        "file.save-as",
        "tools.compare-merge-two-files",
        "file.deploy-pgtp",
        "file.revert",
    ):
        assert gone not in live
    # The successors are all there -- including the tab-gated ones, which are
    # hidden on the Raw XML tab this window is showing.
    for command_id in (
        "deployment.save-pgtp",
        "deployment.save-as-new-pgtp",
        "deployment.compare-merge-pgtp",
        "deployment.deploy-pgtp",
        "file.discard-changes",
    ):
        assert command_id in live


# -- BUG-039/BUG-040: the check gestures MOVED, the session ones were DELETED --


def test_a_toolbar_saved_before_bug039_follows_the_check_gestures_to_parsing(
    qtbot, tmp_path
):
    """BUG-039's two `RENAMED_ID_ALIASES` rows as a real upgrade. The labels did
    not change at all — the id is the whole menu path, so moving the two check
    gestures off `Database` onto `Parsing` renamed both.

    The buttons resolve even though the actions are HIDDEN in this window (no
    DDL object tab is active), which is exactly why the four Parsing members are
    built once and only `setVisible`-toggled: `_walk_menu_actions` never tests
    `isVisible()`, so a hidden action stays enumerable and pinnable."""
    path = str(tmp_path / "s.ini")
    seed = QSettings(path, QSettings.Format.IniFormat)
    seed.setValue(
        "toolbarIds",
        [
            "database.check-object-in-sandbox",
            "database.check-object-without-applying",
        ],
    )
    seed.sync()

    window = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(window)

    assert window._toolbar_ui.command_ids == [
        "parsing.check-object-in-sandbox",
        "parsing.check-object-without-applying",
    ]
    parsing = find_top_menu(window, "Parsing")
    assert window._toolbar_ui.toolbar.actions()[:2] == [
        find_action(parsing, "Check Object in Sandbox"),
        find_action(parsing, "Check Object Without Applying"),
    ]


def test_a_pinned_session_lifecycle_button_is_dropped_not_left_dead(qtbot, tmp_path):
    """BUG-040 DELETED `Open`/`Close Sandbox Session`, and a deletion is not a
    move: there is deliberately no alias row, so a pinned button degrades the
    FQ-020 `file.save` way — `resolve_ids` drops an id that no longer resolves.

    This is also why the actions were deleted rather than hidden: a toolbar
    button bypasses menu visibility entirely, so a hidden action would have left
    a live, clickable button for a gesture the app no longer offers."""
    path = str(tmp_path / "s.ini")
    seed = QSettings(path, QSettings.Format.IniFormat)
    seed.setValue(
        "toolbarIds",
        [
            "database.open-sandbox-session",
            "file.open",
            "database.close-sandbox-session",
        ],
    )
    seed.sync()

    window = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(window)

    assert window._toolbar_ui.command_ids == ["file.open"]
    live = {command_id for command_id, _label in window._toolbar_ui.all_menu_commands()}
    for gone in (
        "database.open-sandbox-session",
        "database.close-sandbox-session",
        "database.check-object-in-sandbox",
        "database.check-object-without-applying",
    ):
        assert gone not in live
    assert "parsing.check-object-in-sandbox" in live
    assert "parsing.check-object-without-applying" in live


def test_no_assignments_leaves_toolbar_behavior_unchanged(qtbot, tmp_path):
    """Back-compat: an existing saved toolbar keeps each button's default."""
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)

    assert window._toolbar_ui.icon_ids == {}
