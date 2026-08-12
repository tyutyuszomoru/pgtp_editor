# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""FQ-260812002827 — `Settings ▸ Software settings…`, the app's one settings home.

Three groups of tests, and the middle one is the load-bearing group:

* **The panes are the REAL widgets.** Every pane assertion checks the concrete
  class of the embedded dialog and drives its own seams, because the whole design
  is *re-host, do not reimplement*. A pane that merely looked right would be the
  failure mode this feature was written to avoid.
* **The apply contract.** Each pane keeps the OK/Cancel semantics it already had,
  the host adds none, and a finished pane is REBUILT from the now-current state.
  The snippets pane is checked click-path-first (its three mutating buttons go
  through argument-dropping lambdas, BUG-260812001455 — re-hosting is exactly
  when such a connection gets rewritten by accident).
* **Relocation means MOVE.** The four absorbed entries must be gone from `View`
  and `Settings`, not duplicated. Asserted by absence, in the menu AND in the
  command walk that feeds the toolbar and the shortcut list.

No test reaches a modal: the settings dialog is `show()`n or driven headlessly,
and nothing here calls `.exec()`.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from pgtp_editor.sql.snippet_store import SNIPPETS_FILENAME
from pgtp_editor.ui.autoformat_settings_dialog import AutoformatSettingsDialog
from pgtp_editor.ui.customize_shortcuts_dialog import CustomizeShortcutsDialog
from pgtp_editor.ui.customize_toolbar_dialog import CustomizeToolbarDialog
from pgtp_editor.ui.edit_snippets_dialog import EditSnippetsDialog
from pgtp_editor.ui.launcher_dialog import LAUNCHER_GROUPS, MODE_MAINTENANCE
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.software_settings_dialog import (
    COMMAND_ID,
    MENU_LABEL,
    SETTINGS_PANES,
    SoftwareSettingsDialog,
)
from pgtp_editor.ui.toolbar_registry import command_id_for
from tests.ui._menu_helpers import find_action, find_top_menu


@pytest.fixture
def window(qtbot, tmp_path):
    def build():
        win = MainWindow(
            generator_config_dir=tmp_path,
            settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
        )
        qtbot.addWidget(win)
        return win

    return build


def _open(win) -> SoftwareSettingsDialog:
    dialog = win.open_software_settings_dialog()
    return dialog


def _button_box(pane) -> QDialogButtonBox:
    """The pane's own OK/Cancel box. Two of the four surfaces call it
    `button_box` and one calls it `_buttons`; the point of pressing the real
    button rather than calling `accept()` is that it exercises the pane's own
    connection, so the name difference is worth accommodating."""
    return getattr(pane, "button_box", None) or pane._buttons


def _ok(pane) -> None:
    _button_box(pane).button(QDialogButtonBox.StandardButton.Ok).click()


def _cancel(pane) -> None:
    _button_box(pane).button(QDialogButtonBox.StandardButton.Cancel).click()


# -- the command ---------------------------------------------------------------


def test_the_command_id_is_derived_from_the_label_it_ships_with():
    """The id is a FUNCTION of the menu label (`toolbar_registry.command_id_for`),
    so the literal in `COMMAND_ID` — which `launcher_dialog` imports — must be
    what the menu row actually produces."""
    assert COMMAND_ID == command_id_for(["Settings", MENU_LABEL])
    assert COMMAND_ID == "settings.software-settings"


def test_settings_holds_exactly_one_entry_and_it_is_this_one(window):
    win = window()
    labels = [a.text() for a in win._settings_menu.actions() if not a.isSeparator()]
    assert labels == [MENU_LABEL]
    assert win._software_settings_action is find_action(
        win._settings_menu, MENU_LABEL
    )


def test_the_command_carries_NO_shortcut(window):
    """It has a command form (this entry plus a launcher button), so under
    DEC-012 it gets exactly one keyboard host — the `QAction` — and per the
    Maintenance-only `Settings` convention (DEC-006) that host carries nothing.
    **This change adds no chord.**"""
    win = window()
    assert win._software_settings_action.shortcut().isEmpty()
    assert list(win._software_settings_action.shortcuts()) == []


def test_the_command_is_maintenance_only_like_the_menu_it_sits_on(window):
    win = window()
    assert win._settings_menu.menuAction().isVisible() is False
    win.set_workflow_mode(MODE_MAINTENANCE)
    assert win._settings_menu.menuAction().isVisible() is True
    win.set_workflow_mode(None)
    assert win._settings_menu.menuAction().isVisible() is False


def test_the_launcher_offers_it_in_the_MAINTENANCE_column(window):
    """A launcher button is one menu command resolved through the menu walk, so
    the label is DERIVED (`Settings › Software settings`) rather than typed into
    the launcher — which is only possible because the command exists as a real
    menu action."""
    from pgtp_editor.ui.launcher_dialog import LauncherDialog, resolve_menu_entries

    win = window()
    assert dict(LAUNCHER_GROUPS)["Maintenance"][-1] == COMMAND_ID

    entries = resolve_menu_entries(win)
    assert entries[COMMAND_ID][0] == "Settings › Software settings"
    dialog = LauncherDialog(entries, parent=win)
    assert COMMAND_ID in dialog.entry_ids()
    assert dialog.button_for(COMMAND_ID).text() == "Settings › Software settings"


# -- relocation means MOVE -----------------------------------------------------


def test_the_four_absorbed_entries_are_GONE_from_their_old_menus(window):
    win = window()
    view = find_top_menu(win, "View")
    for label in ("Customize Toolbar…", "Customize Shortcuts…"):
        assert find_action(view, label) is None, label
    for label in ("Edit Snippets…", "Autoformatter settings…"):
        assert find_action(win._settings_menu, label) is None, label


def test_the_four_absorbed_command_ids_no_longer_ENUMERATE(window):
    """The stronger statement: they are gone from the menu walk, so they are not
    pinnable to the toolbar and not rebindable in the shortcuts pane either. A
    stored `toolbarIds` entry naming one is dropped by `resolve_ids` — correct,
    because there is no successor id that means "customize the toolbar"."""
    win = window()
    commands = dict(win._toolbar_ui.all_menu_commands())
    for gone in (
        "view.customize-toolbar",
        "view.customize-shortcuts",
        "settings.edit-snippets",
        "settings.autoformatter-settings",
    ):
        assert gone not in commands, gone
    assert COMMAND_ID in commands


# -- the panes -----------------------------------------------------------------


def test_five_panes_ship_and_the_two_SUPERSEDED_ones_are_ABSENT(window):
    """DEC-260812004400 is answered by a REAL fifth pane, not by a stub.

    FQ-260812002828 (syntax highlight colors) and FQ-260812002829 (color scheme)
    were SUPERSEDED by FQ-260812021716: syntax highlighting is part of the theme
    by owner ruling, so the two reserved panes are ONE `Themes` pane. Neither
    placeholder key exists — two panes editing one `Theme` is precisely the
    mismatch the merge removes."""
    win = window()
    dialog = _open(win)
    assert dialog.pane_keys() == [
        "snippets", "toolbar", "autoformatter", "shortcuts", "themes",
    ]
    assert dialog.pane_titles() == [
        "Snippets",
        "Toolbar",
        "Autoformatter",
        "Keyboard shortcuts",
        "Themes",
    ]
    for absent in ("syntax-highlight-colors", "color-scheme", "theme"):
        assert dialog.pane_for(absent) is None


def test_adding_a_pane_is_a_DATA_change(window):
    """The category list is built from `SETTINGS_PANES`, so a new pane is one
    more row rather than a rewrite. Proved by injecting an extra one — and
    demonstrated for real by the `Themes` pane, which cost exactly one row."""
    from pgtp_editor.ui.software_settings_dialog import SettingsPane

    win = window()
    extra = SettingsPane(
        key="extra",
        title="Extra",
        blurb="a pane that does not exist in the product",
        build=lambda _window, parent: QDialog(parent),
    )
    dialog = SoftwareSettingsDialog(win, win, panes=SETTINGS_PANES + (extra,))
    assert dialog.pane_keys()[-1] == "extra"
    assert dialog.category_list.count() == len(SETTINGS_PANES) + 1
    assert dialog.select_pane("extra") is True
    assert dialog.current_pane_key() == "extra"


@pytest.mark.parametrize(
    "key,kind",
    [
        ("snippets", EditSnippetsDialog),
        ("toolbar", CustomizeToolbarDialog),
        ("autoformatter", AutoformatSettingsDialog),
        ("shortcuts", CustomizeShortcutsDialog),
    ],
)
def test_each_pane_shows_the_REAL_widget(window, key, kind):
    """Re-hosted, not reimplemented: the pane IS the shipped dialog."""
    win = window()
    dialog = _open(win)
    assert dialog.select_pane(key) is True
    pane = dialog.pane_widget(key)
    assert isinstance(pane, kind)
    # Embedded as a plain widget, never as a window of its own.
    assert pane.isVisible() is True
    assert pane.isWindow() is False
    assert pane.window() is dialog


def test_the_panes_are_wired_to_the_real_collaborators(window):
    win = window()
    dialog = _open(win)
    assert dialog.pane_widget("snippets") is win._snippet_ui.dialog()
    assert dialog.pane_widget("toolbar") is win._toolbar_ui.customize_dialog
    assert dialog.pane_widget("shortcuts") is win._customize_shortcuts_dialog


def test_the_shortcuts_pane_lists_the_whole_command_universe(window):
    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("shortcuts")
    assert pane.command_ids() == [
        command_id for command_id, _label in win._toolbar_ui.all_menu_commands()
    ]
    # ...including the command that opens the dialog it is sitting in.
    assert COMMAND_ID in pane.command_ids()


def test_the_toolbar_pane_offers_every_menu_command(window):
    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("toolbar")
    assert pane._available_ids() == [
        command_id for command_id, _label in win._toolbar_ui.all_menu_commands()
    ]


# -- single instance / modality ------------------------------------------------


def test_it_is_NON_MODAL(window):
    """DEC-260812004359's shipped default: the four absorbed surfaces were all
    non-modal, and the shortcuts pane in particular wants to stay up."""
    win = window()
    assert _open(win).isModal() is False


def test_opening_twice_FOCUSES_the_one_dialog(window):
    """A non-modal settings window that can be opened twice is two windows
    editing the same stores."""
    win = window()
    first = _open(win)
    assert win.open_software_settings_dialog() is first
    win._software_settings_action.trigger()
    assert win._software_settings_dialog is first


def test_the_menu_ACTION_opens_the_dialog_on_a_FRESH_window(window):
    """The dialog's user path, asserted from nothing.

    `test_opening_twice_FOCUSES_the_one_dialog` below triggers the action too,
    but only AFTER `_open()` already built the dialog — so it passes unchanged
    against an action whose `triggered` connection does not exist, because the
    handle it asserts on was put there by the direct call. This is the
    BUG-260812001455 shape (`add_snippet` was green through its seam while the
    button was dead), and re-hosting four surfaces is exactly when a connection
    gets rewritten by accident. Trigger first, assert the dialog appeared.
    """
    win = window()
    assert win._software_settings_dialog is None

    win._software_settings_action.trigger()

    dialog = win._software_settings_dialog
    assert isinstance(dialog, SoftwareSettingsDialog)
    assert dialog.pane_keys() == [
        "snippets", "toolbar", "autoformatter", "shortcuts", "themes",
    ]


def test_the_LAUNCHER_BUTTON_CLICK_chooses_this_command(window):
    """`test_the_launcher_offers_it_in_the_MAINTENANCE_column` proves the button
    EXISTS and is labelled from the menu walk; it never presses it. The launcher
    binds every button through `lambda _checked=False, cid=...` precisely because
    `clicked(bool)` would otherwise land `False` in `choose`'s `command_id` — the
    same argument-binding defect BUG-260812001455 shipped. Press it for real."""
    from pgtp_editor.ui.launcher_dialog import LauncherDialog, resolve_menu_entries

    win = window()
    dialog = LauncherDialog(resolve_menu_entries(win), parent=win)

    dialog.button_for(COMMAND_ID).click()

    assert dialog.chosen_command_id == COMMAND_ID
    assert dialog.chosen_group_title == "Maintenance"
    assert dialog.chosen_workflow_mode == MODE_MAINTENANCE


def test_picking_a_CATEGORY_ROW_switches_the_shown_pane(window):
    """`select_pane` returns True from the pane table alone, so it reports
    success whether or not `currentRowChanged → stack.setCurrentIndex` survived.
    Drive the list widget the way a click does and assert the STACK moved."""
    win = window()
    dialog = _open(win)
    keys = dialog.pane_keys()

    for row, key in enumerate(keys):
        dialog.category_list.setCurrentRow(row)
        assert dialog.stack.currentIndex() == row, key
        assert dialog.current_pane_key() == key
        # ...and the real widget for that key is the one now on screen.
        assert dialog.pane_widget(key).isVisible() is True


def test_closing_it_lets_the_next_open_build_a_FRESH_one(window):
    """Every pane reads its store at construction, so a settings window kept
    alive across a session would be the one place showing yesterday's values."""
    win = window()
    first = _open(win)
    first.reject()
    assert win._software_settings_dialog is None
    assert _open(win) is not first


def test_the_host_offers_CLOSE_and_no_OK(window):
    """There is no host-level apply because there is no host-level state: each
    pane owns its own OK. A host OK would have to invent a fifth apply semantics
    over four that already disagree."""
    win = window()
    box = _open(win).button_box
    assert box.button(QDialogButtonBox.StandardButton.Close) is not None
    assert box.button(QDialogButtonBox.StandardButton.Ok) is None
    assert box.button(QDialogButtonBox.StandardButton.Apply) is None


# -- the apply contract --------------------------------------------------------


def test_the_snippets_CLICK_PATH_still_works_through_the_dialog(window):
    """BUG-260812001455: `clicked(bool)` binds to a handler's first positional
    parameter, so `Add` used to call `add_snippet(False)` and die inside a
    traceback Qt swallows. The lambdas that fixed it must survive re-hosting —
    this presses the real buttons rather than calling the seams."""
    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("snippets")
    before = pane.table.rowCount()

    pane.add_button.click()
    assert pane.table.rowCount() == before + 1

    pane.delete_button.click()
    assert pane.table.rowCount() == before

    pane.restore_button.click()  # nothing missing; must not raise
    assert pane.message()


def test_a_panes_OK_persists_and_the_pane_is_REBUILT_from_what_was_saved(
    window, tmp_path
):
    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("snippets")
    pane.add_button.click()
    expected = len(pane.result_snippets())

    _ok(pane)

    assert (tmp_path / SNIPPETS_FILENAME).exists()
    assert len(win._snippet_ui.snippets()) == expected
    fresh = dialog.pane_widget("snippets")
    assert fresh is not pane, "a finished pane must be replaced, not left hidden"
    assert fresh.isVisible() is True
    assert len(fresh.result_snippets()) == expected


def test_a_panes_CANCEL_undoes_everything_it_ever_did(window, tmp_path):
    """The snippets dialog edits a SCRATCH copy and Cancel discards it — a
    contract pinned since FQ-030 and unchanged by the re-hosting, which is the
    whole reason the host adds no OK of its own."""
    win = window()
    before = win._snippet_ui.snippets()
    dialog = _open(win)
    pane = dialog.pane_widget("snippets")
    pane.add_button.click()

    _cancel(pane)

    assert win._snippet_ui.snippets() == before
    assert not (tmp_path / SNIPPETS_FILENAME).exists()
    fresh = dialog.pane_widget("snippets")
    assert fresh is not pane
    assert fresh.result_snippets() == before


def test_the_toolbar_panes_OK_applies_and_saves(window):
    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("toolbar")
    chosen = pane.selected_ids()[:2]
    pane.set_ids(chosen)

    _ok(pane)

    assert win._toolbar_ui.command_ids == chosen
    assert dialog.pane_widget("toolbar") is not pane
    assert dialog.pane_widget("toolbar").selected_ids() == chosen


def test_the_shortcuts_panes_OK_applies_and_saves(window):
    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("shortcuts")
    pane.set_binding("file.close", "Ctrl+Alt+W")

    _ok(pane)

    assert win._shortcut_overrides.get("file.close") == "Ctrl+Alt+W"
    rebuilt = dialog.pane_widget("shortcuts")
    assert rebuilt is not pane
    assert rebuilt.binding_of("file.close") == "Ctrl+Alt+W"


def test_the_shortcuts_panes_CANCEL_persists_nothing(window):
    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("shortcuts")
    pane.set_binding("file.close", "Ctrl+Alt+W")

    _cancel(pane)

    assert win._shortcut_overrides == {}
    assert dialog.pane_widget("shortcuts").binding_of("file.close") != "Ctrl+Alt+W"


def test_the_autoformatter_panes_OK_persists_into_the_windows_store(window):
    from pgtp_editor.sql.format_config import KeywordCase
    from pgtp_editor.ui import format_settings

    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("autoformatter")
    pane.set_keyword_case(KeywordCase.UPPER)

    _ok(pane)

    saved = format_settings.load_sql_config(win._settings)
    assert saved.keyword_case == KeywordCase.UPPER
    # ...and the rebuilt pane shows what was saved rather than the defaults.
    assert dialog.pane_widget("autoformatter").sql_config().keyword_case == (
        KeywordCase.UPPER
    )


def test_closing_the_host_mid_edit_discards_only_that_panes_scratch(window, tmp_path):
    """Nothing is buffered at host level, so `Close` is never a save and never a
    loss beyond one pane's uncommitted edits — identical to closing any one of
    these four dialogs before this feature existed."""
    win = window()
    before = win._snippet_ui.snippets()
    dialog = _open(win)
    dialog.pane_widget("snippets").add_button.click()

    dialog.reject()

    assert win._snippet_ui.snippets() == before
    assert not (tmp_path / SNIPPETS_FILENAME).exists()


# -- FQ-260812021716: the Themes pane -----------------------------------------
# The fifth pane, and the one this module DEFINES rather than embeds. It is also
# the pane whose gestures are not all in the button box: "Use this theme" applies
# and persists IMMEDIATELY (owner ruling: a Maintenance setting is app-wide and
# durable from the moment it is marked), while colour edits go through the pane's
# own OK/Cancel like every other pane here.
#
# Every test below redirects `theme_model.user_themes_dir` at tmp_path. That ONE
# patch covers both halves of the file model — `theme_search_path` (so a written
# file is discovered) and `save_theme` (so nothing is written into the install) —
# which is precisely why the two go through the same function in the first place.


@pytest.fixture
def themes(monkeypatch, tmp_path):
    """A writable user themes directory, and the active theme reset afterwards.

    Resetting is not tidiness: `theme_model.theme_for` answers the app's
    `light: bool` seam with the ACTIVE theme, so a custom theme left applied
    would leak its colours into every later test's palette assertions.
    """
    from pgtp_editor.ui import theme_model

    directory = tmp_path / "user-themes"
    directory.mkdir()
    monkeypatch.setattr(theme_model, "user_themes_dir", lambda: directory)
    try:
        yield directory
    finally:
        theme_model.set_active_theme(None)


def _themes_pane(win):
    return _open(win).pane_widget("themes")


def test_the_pane_LISTS_every_bundled_theme_and_marks_the_one_in_use(window, themes):
    win = window()
    pane = _themes_pane(win)
    assert "dark" in pane.theme_names() and "light" in pane.theme_names()
    assert pane.active_theme_name() == "dark"
    assert any("in use" in pane.theme_list.item(row).text()
               for row in range(pane.theme_list.count()))


def test_a_theme_FILE_dropped_in_appears_without_a_restart(window, themes):
    """The foundation feature's headline requirement, reaching the pane: the
    list is `available_themes()`, which rescans on every call, so a file written
    while the dialog is open shows up on the next refresh."""
    import json

    from pgtp_editor.ui.theme_model import bundled_themes_dir

    win = window()
    pane = _themes_pane(win)
    assert "midnight" not in pane.theme_names()

    (themes / "midnight.json").write_text(
        (bundled_themes_dir() / "dark.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    pane.refresh_themes()
    assert "midnight" in pane.theme_names()
    assert json.loads((themes / "midnight.json").read_text(encoding="utf-8"))["name"]


def test_USE_THIS_THEME_applies_and_PERSISTS_immediately(window, themes):
    """Not on OK. The owner's ruling is that a theme is app-wide and durable from
    the moment it is marked selected — which is exactly what makes the
    Maintenance-only round-trip an acceptable cost and the removed `View` toggle
    unnecessary."""
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication

    from pgtp_editor.ui import theme_model

    win = window()
    pane = _themes_pane(win)
    pane.select_theme("light")
    assert pane.use_selected() == "light"

    assert win.theme_name() == "light"
    assert win._settings.value(theme_model.SETTINGS_KEY, "", type=str) == "light"
    assert QApplication.instance().palette().color(
        QPalette.ColorRole.Window
    ).lightness() > 200
    # ...and the list now marks the new one, not the old.
    assert "in use" in pane.theme_list.item(pane.theme_names().index("light")).text()


def test_a_BUNDLED_theme_is_READ_ONLY_and_says_so(window, themes):
    win = window()
    pane = _themes_pane(win)
    pane.select_theme("dark")
    assert "read-only" in pane.status_label.text()
    assert not _button_box(pane).button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    with pytest.raises(Exception, match="bundled"):
        pane.save_edits()


def test_DUPLICATE_creates_an_editable_copy_in_the_USER_directory(window, themes):
    """"New = copy an existing one": the copy is a complete, valid `Theme` from
    the first keystroke, so there is no half-defined-theme state — and it lands
    in the user directory, which is what makes it editable at all."""
    win = window()
    pane = _themes_pane(win)
    pane.select_theme("dark")
    assert pane.duplicate_selected("My Theme") == "my-theme"

    assert (themes / "my-theme.json").exists()
    assert pane.selected_theme_name() == "my-theme"
    assert "read-only" not in pane.status_label.text()
    assert _button_box(pane).button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    # Same colours as its source: a duplicate is a copy, not a delta on it.
    assert pane.color_value("chrome", "COLOR_BACKGROUND_1") == \
        pane._theme.chrome["COLOR_BACKGROUND_1"]


def test_a_duplicate_may_not_COLLIDE_with_an_existing_theme(window, themes):
    win = window()
    pane = _themes_pane(win)
    pane.select_theme("dark")
    pane.duplicate_selected("My Theme")
    pane.select_theme("dark")
    with pytest.raises(Exception, match="already exists"):
        pane.duplicate_selected("my theme")  # same stem, different spelling


def test_EDITING_a_user_theme_writes_the_colour_and_it_LOADS_back(window, themes):
    """Round-tripped through the real loader, because the editor builds its
    result with `Theme.from_json` — an editor that could produce an unloadable
    theme would only reveal it on the next start."""
    from pgtp_editor.ui.theme_model import load_theme_file

    win = window()
    pane = _themes_pane(win)
    pane.select_theme("dark")
    pane.duplicate_selected("Midnight")

    pane.set_color_value("decorations", "current_line", "#123456")
    pane.set_color_value("chrome", "COLOR_BACKGROUND_1", "#010203")
    pane.set_color_value("modes", "maintenance.background", "#0a0b0c")
    pane.set_color_value("syntax", "code_comment", "#abcdef")
    pane.set_syntax_flag("code_comment", "italic", True)
    _ok(pane)

    saved = load_theme_file(themes / "midnight.json")
    assert saved.decoration("current_line") == "#123456"
    assert saved.chrome["COLOR_BACKGROUND_1"] == "#010203"
    assert saved.modes["maintenance"][0] == "#0a0b0c"
    assert saved.role("code_comment").color == "#abcdef"
    assert saved.role("code_comment").italic is True


def test_CANCEL_discards_the_edits_and_the_host_REBUILDS_the_pane(window, themes):
    """The dialog's settled contract: the pane owns Cancel, the host adds
    nothing, and a finished pane is replaced by a fresh one reading what is now
    stored — so no pane is ever a stale scratch copy."""
    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("themes")
    pane.select_theme("dark")
    pane.duplicate_selected("Midnight")
    before = pane.color_value("decorations", "current_line")

    pane.set_color_value("decorations", "current_line", "#123456")
    _cancel(pane)

    rebuilt = dialog.pane_widget("themes")
    assert rebuilt is not pane
    assert rebuilt.select_theme("midnight")
    assert rebuilt.color_value("decorations", "current_line") == before


def test_SAVING_the_theme_IN_USE_re_applies_it_so_the_edit_is_VISIBLE(window, themes):
    """The pane's live preview, honestly scoped: apply-on-save. The re-apply is
    what proves `load_theme_file`'s stat-keyed cache picks the write up — a
    path-keyed cache would hand back the parse from before the save."""
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication

    win = window()
    pane = _themes_pane(win)
    pane.select_theme("dark")
    pane.duplicate_selected("Midnight")
    pane.use_selected()
    assert win.theme_name() == "midnight"

    pane.set_color_value("palette", "Window", "#123456")
    _ok(pane)

    assert QApplication.instance().palette().color(
        QPalette.ColorRole.Window
    ).rgb() == QColor("#123456").rgb()


def test_an_edited_theme_gets_its_OWN_recoloured_stylesheet(window, themes):
    """The chrome QSS cache was keyed on the `light` bool before this feature;
    two dark themes would then have shared one stylesheet and an edit would have
    painted the OTHER theme's chrome. It is keyed on the chrome colours now."""
    from PySide6.QtWidgets import QApplication

    win = window()
    dialog = _open(win)
    pane = dialog.pane_widget("themes")
    pane.select_theme("dark")
    pane.duplicate_selected("Midnight")
    pane.set_color_value("chrome", "COLOR_BACKGROUND_1", "#010203")
    _ok(pane)
    # OK finishes the pane, so the host has already replaced it — drive the NEW
    # one, exactly as a user would.
    rebuilt = dialog.pane_widget("themes")
    rebuilt.select_theme("midnight")
    rebuilt.use_selected()

    assert "#010203" in QApplication.instance().styleSheet()


def test_a_user_theme_that_gives_CODE_SYNTAX_its_own_colours_REHIGHLIGHTS(
    window, themes, qtbot
):
    """`_apply_syntax_theme_colors` is wired but never fires today: both bundled
    themes carry the same five code roles, so `apply_syntax_theme` finds no
    change and returns False, and the caller skips the `rehighlight()`. The
    Themes pane is what can make them differ — so that path goes LIVE, and it is
    verified here rather than assumed.

    The editor is built BEFORE the new theme is applied, deliberately: built
    after, its constructor would load the new colours and the assertion would
    pass without the change path ever running.
    """
    from pgtp_editor.ui.code_editor import CodeEditor

    win = window()

    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    editor.setPlainText("select 1;")
    was = editor._highlighter._keyword_format.foreground().color().name()
    assert was != "#abcdef"

    dialog = _open(win)
    pane = dialog.pane_widget("themes")
    pane.select_theme("dark")
    pane.duplicate_selected("Midnight")
    pane.set_color_value("syntax", "code_keyword", "#abcdef")
    _ok(pane)
    rebuilt = dialog.pane_widget("themes")
    rebuilt.select_theme("midnight")
    rebuilt.use_selected()

    # The LIVE path did it by itself: applying the theme fires `PaletteChange`,
    # the editor's `changeEvent` calls `_apply_syntax_theme_colors`, and this
    # time the roles genuinely differ so the rehighlight actually happens.
    assert editor._highlighter._keyword_format.foreground().color().name() == "#abcdef"

    # ...and it settled: a repeat finds nothing to do, so the FOUR
    # `PaletteChange` events a flip fires cannot reformat the document four
    # times, and the first two (which report the OLD lightness) cannot leave the
    # editor on the previous theme.
    assert editor._highlighter.apply_syntax_theme(False) is False
    editor._apply_syntax_theme_colors(False)
    assert editor._highlighter._keyword_format.foreground().color().name() == "#abcdef"


def test_the_pane_has_NO_keyboard_shortcut_of_its_own(window, themes):
    """DEC-012: a command with a command form has exactly one keyboard host, and
    the Maintenance-only `Settings` convention gives that host no chord. The
    pane's controls are dialog widgets, not window chords — nothing here may
    claim a sequence."""
    win = window()
    pane = _themes_pane(win)
    assert pane.actions() == []
    assert [s.key().toString() for s in pane.findChildren(__import__(
        "PySide6.QtGui", fromlist=["QShortcut"]).QShortcut)] == []
