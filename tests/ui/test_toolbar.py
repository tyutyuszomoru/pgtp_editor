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


DEFAULT_LABELS = [
    "Open...",
    "Save",
    "Undo",
    "Redo",
    "Find...",
    "Validate Project",
    "Generate PHP...",
]


def _ini_settings(tmp_path, name="s.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


def _toolbar_labels(window):
    return [a.text() for a in window._toolbar_ui.toolbar.actions()]


def test_default_toolbar_has_seven_actions_in_order(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == DEFAULT_LABELS
    assert window._toolbar_ui.toolbar.objectName() == "main_toolbar"


def test_apply_toolbar_ids_reorders_and_subsets(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_ids(["file.save", "file.open"])
    assert _toolbar_labels(window) == ["Save", "Open..."]
    assert window._toolbar_ui.command_ids == ["file.save", "file.open"]


def test_apply_toolbar_ids_drops_unknowns(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_ids(["tools.validate-project", "bogus", "edit.find"])
    assert _toolbar_labels(window) == ["Validate Project", "Find..."]


def test_toolbar_action_is_the_menu_action_itself(qtbot, tmp_path):
    """BUG-027: the toolbar hosts the real menu QAction rather than a parallel
    copy wired through a slot table -- that's what makes the button share the
    menu item's slot, enabled state and shortcut."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_ids(["tools.validate-project"])
    menu_action = find_action(find_top_menu(window, "Tools"), "Validate Project")
    assert window._toolbar_ui.toolbar.actions() == [menu_action]


def test_toolbar_action_triggers_slot(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    called = []
    window._toolbar_ui.apply_ids(["tools.validate-project"])
    # The shared action carries the menu's connection; add our own spy to it
    # rather than patching the bound slot, which would not rewire it.
    window._toolbar_ui.toolbar.actions()[0].triggered.connect(lambda: called.append(True))
    window._toolbar_ui.toolbar.actions()[0].trigger()
    assert called == [True]


def test_apply_and_save_persists_and_round_trips(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._toolbar_ui.apply_and_save(["edit.find", "file.save"])
    assert _toolbar_labels(window) == ["Find...", "Save"]

    # A new window reading the same store restores that toolbar.
    settings2 = _ini_settings(tmp_path)
    window2 = MainWindow(settings=settings2)
    qtbot.addWidget(window2)
    assert _toolbar_labels(window2) == ["Find...", "Save"]


def test_stored_comma_string_is_restored(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", "edit.undo,edit.redo")
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == ["Undo", "Redo"]


def test_unknown_stored_ids_are_dropped(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", ["file.save", "bogus", "file.open"])
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == ["Save", "Open..."]


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

    assert len(pairs) > 7                       # the reported bug: only 7
    # Commands that were previously impossible to put on the toolbar:
    for command_id in ("file.save-as", "edit.replace", "edit.find-all"):
        assert command_id in ids
    # ...alongside the legacy seven, which must all still be offered.
    for command_id in DEFAULT_TOOLBAR_IDS:
        assert command_id in ids


def test_menu_command_labels_show_their_menu_path(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    labels = dict(window._toolbar_ui.all_menu_commands())
    assert labels["file.save-as"] == "File › Save As"


def test_menu_command_ids_are_unique(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    ids = [command_id for command_id, _label in window._toolbar_ui.all_menu_commands()]
    assert len(ids) == len(set(ids))


def test_recent_files_submenu_is_not_offered(qtbot, tmp_path):
    """Its children are transient per-session file entries -- pinning one to
    the toolbar would leave a dead button behind."""
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
    window._toolbar_ui.apply_and_save(["file.save-as"])
    assert _toolbar_labels(window) == ["Save As..."]
    assert window._toolbar_ui.toolbar.actions()[0] is find_action(
        find_top_menu(window, "File"), "Save As..."
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
    settings.setValue("toolbarIds", ["save", "find", "undo"])
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert window._toolbar_ui.command_ids == ["file.save", "edit.find", "edit.undo"]
    assert _toolbar_labels(window) == ["Save", "Find...", "Undo"]


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
    window._toolbar_ui.apply_ids(["file.save-as"])
    action = window._toolbar_ui.toolbar.actions()[0]
    assert action.icon().isNull()
    assert action.text() == "Save As..."


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
    validate = find_action(find_top_menu(window, "Tools"), "Validate Project")

    window._toolbar_ui.apply_ids(["tools.validate-project"])
    window._toolbar_ui.apply_ids(["file.save"])          # drops validate again
    window._toolbar_ui.apply_ids(["tools.validate-project"])

    # Still the same, still-alive object, still in the Tools menu.
    assert window._toolbar_ui.toolbar.actions() == [validate]
    assert validate.text() == "Validate Project"
    assert find_action(find_top_menu(window, "Tools"), "Validate Project") is validate
    called = []
    validate.triggered.connect(lambda: called.append(True))
    validate.trigger()
    assert called == [True]


def test_removed_toolbar_action_survives_and_stays_in_its_menu(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    save_as = find_action(find_top_menu(window, "File"), "Save As...")
    window._toolbar_ui.apply_ids(["file.save-as"])
    window._toolbar_ui.apply_ids(["file.save"])
    assert save_as not in window._toolbar_ui.toolbar.actions()
    assert save_as.text() == "Save As..."          # C++ object still alive
    assert find_action(find_top_menu(window, "File"), "Save As...") is save_as


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
    tools = find_top_menu(window, "Tools")
    original = find_action(tools, "Validate Project")
    twin = tools.addAction("Validate Project")

    pairs = window._toolbar_ui.collect_menu_commands()
    ids = [command_id for command_id, _label in pairs]
    assert "tools.validate-project" in ids
    assert "tools.validate-project-2" in ids
    assert len(ids) == len(set(ids))
    assert window._toolbar_ui.menu_commands["tools.validate-project"] is original
    assert window._toolbar_ui.menu_commands["tools.validate-project-2"] is twin

    tools.removeAction(twin)


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
    """The walk is depth-first over real submenus (today only the excluded
    Open Recent is one), so a nested command gets a dotted id and a `›`-joined
    label — and the submenu placeholder itself is never a command."""
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
    window._toolbar_ui.apply_ids(["file.save-as", "file.save"])
    window._toolbar_ui.refresh_icons()
    save_as, save = window._toolbar_ui.toolbar.actions()
    assert save_as.icon().isNull()
    assert not save.icon().isNull()


def test_icon_less_command_keeps_its_menu_icon_visibility(qtbot, tmp_path):
    """`setIconVisibleInMenu(False)` is only applied to actions we decorate;
    an icon-less command is left completely untouched."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    save_as = find_action(find_top_menu(window, "File"), "Save As...")
    window._toolbar_ui.apply_ids(["file.save-as"])
    assert save_as.isIconVisibleInMenu() is True


def test_saved_ids_are_menu_path_ids_in_settings(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._toolbar_ui.apply_and_save(["file.save-as", "edit.replace"])
    stored = settings.value("toolbarIds")
    stored = stored.split(",") if isinstance(stored, str) else list(stored)
    assert stored == ["file.save-as", "edit.replace"]


# --- FQ-004: per-command icon assignments ----------------------------------
def test_assigned_icon_overrides_the_legacy_default(qtbot, tmp_path):
    """Any button may be re-decorated, including the legacy seven."""
    from pgtp_editor.ui.toolbar_registry import icon_id_for

    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)

    assert icon_id_for("file.save", {}) == "save"
    assert icon_id_for("file.save", {"file.save": "document-print"}) == "document-print"


def test_icon_assignments_round_trip_through_settings(qtbot, tmp_path):
    """Saved under a sibling key of toolbarIds, restored on the next window."""
    from pgtp_editor.ui.toolbar_registry import ICON_ASSIGNMENTS_SETTINGS_KEY

    path = str(tmp_path / "s.ini")
    window = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    window._toolbar_ui.apply_and_save(
        window._toolbar_ui.command_ids, {"file.save": "document-print"}
    )
    window._settings.sync()

    reopened = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(reopened)

    assert reopened._settings.value(ICON_ASSIGNMENTS_SETTINGS_KEY) is not None
    assert reopened._toolbar_ui.icon_ids.get("file.save") == "document-print"


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


def test_no_assignments_leaves_toolbar_behavior_unchanged(qtbot, tmp_path):
    """Back-compat: an existing saved toolbar keeps each button's default."""
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)

    assert window._toolbar_ui.icon_ids == {}
