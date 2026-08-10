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
"""The `Settings` menu and `Settings ▸ Edit Snippets…` on the real window
(FQ-030): where they live, when they are visible, and that the store the entry
edits is the injected one.

Two invariants here are not behaviour checks but rules with recorded reasons:

* **`Settings` is the app's first MAINTENANCE-ONLY menu.** Every other rule in
  `_refresh_workflow_mode_affordances` subtracts from the bar inside the mode;
  this one adds. It is asserted in both directions and across a mode round-trip,
  because a one-way test would pass on a menu that never comes back.
* **Nothing in it may carry a keyboard shortcut** (DEC-006: hiding means "not in
  your way", never "prevented"). Hiding a QMenu leaves its children's shortcuts
  live, so a shortcut here would still fire outside Maintenance mode.

`generator_config_dir=tmp_path` in every test — the SAME per-user config
override §19/§22 use, and what keeps the suite off the developer's real store.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from pgtp_editor.sql.snippet_store import SNIPPETS_FILENAME, save_snippets
from pgtp_editor.sql.templates import DEFAULT_SNIPPETS, Snippet
from pgtp_editor.ui.launcher_dialog import MODE_MAINTENANCE
from pgtp_editor.ui.main_window import MainWindow

MINE = Snippet("upd", "an update", "UPDATE {{1:t}} SET {{0}};")


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


def _settings_menu(win):
    for action in win.menuBar().actions():
        if action.text() == "Settings":
            return action.menu()
    return None


def _entry(win, label="Edit Snippets…"):
    menu = _settings_menu(win)
    for action in menu.actions():
        if action.text() == label:
            return action
    return None


# -- the menu ------------------------------------------------------------------


def test_settings_is_a_top_level_menu_holding_edit_snippets(window):
    win = window()
    assert _settings_menu(win) is not None
    assert _entry(win) is not None


def test_settings_sits_between_generation_and_help(window):
    win = window()
    titles = [a.text() for a in win.menuBar().actions() if a.menu() is not None]
    assert titles == [
        "File", "View", "Schema", "Database", "Tools", "Generation",
        "Settings", "Help",
    ]


def test_settings_is_absent_outside_maintenance_mode(window):
    win = window()
    assert _settings_menu(win).menuAction().isVisible() is False


def test_maintenance_mode_reveals_it_and_leaving_hides_it_again(window):
    win = window()
    win.set_workflow_mode(MODE_MAINTENANCE)
    assert _settings_menu(win).menuAction().isVisible() is True
    win.set_workflow_mode(None)
    assert _settings_menu(win).menuAction().isVisible() is False


def test_the_menu_and_its_actions_exist_in_both_modes(window):
    """Built once, only `setVisible`-toggled — the enumeration rule
    `_refresh_workflow_mode_affordances` documents at length: an action that
    does not EXIST at enumeration time drops out of Customize Toolbar."""
    win = window()
    before = _entry(win)
    win.set_workflow_mode(MODE_MAINTENANCE)
    assert _entry(win) is before


def test_no_settings_command_carries_a_keyboard_shortcut(window):
    """DEC-006: a hidden menu's children keep their shortcuts, so a shortcut
    here would reach a maintenance-only command from outside the mode."""
    win = window()
    for action in _settings_menu(win).actions():
        assert action.shortcut().isEmpty(), action.text()


def test_no_settings_command_at_any_depth_carries_a_shortcut(window):
    """The same DEC-006 rule as above, swept RECURSIVELY and over `shortcuts()`
    as well as `shortcut()` — a submenu added later, or a second binding set
    with `setShortcuts`, would otherwise slip past the shallow check and fire
    outside Maintenance mode."""
    win = window()

    def sweep(menu, seen):
        for action in menu.actions():
            assert action.shortcut().isEmpty(), action.text()
            assert list(action.shortcuts()) == [], action.text()
            sub = action.menu()
            if sub is not None and id(sub) not in seen:
                seen.add(id(sub))
                sweep(sub, seen)

    sweep(_settings_menu(win), set())


def test_the_maintenance_filter_still_hides_the_ordinary_menus(window):
    """The inverse rule must not have broken the subtractive one."""
    win = window()
    win.set_workflow_mode(MODE_MAINTENANCE)
    visible = [
        a.text() for a in win.menuBar().actions() if a.menu() is not None and a.isVisible()
    ]
    assert visible == ["File", "Schema", "Settings", "Help"]


def test_the_command_is_enumerated_and_therefore_pinnable(window):
    """KNOWN AND ACCEPTED, pinned here so it cannot change unnoticed.

    `ToolbarController._walk_menu_actions` does not test `isVisible()`, so
    `settings.edit-snippets` is offered by Customize Toolbar and a pinned
    button reaches the dialog outside Maintenance mode. That is FQ-027 Q2's
    recorded trade and DEC-006's ruling (hiding is "not in your way", never
    "prevented"), and it is what keeps the command's id stable across modes.
    """
    win = window()
    commands = dict(win._toolbar_ui.all_menu_commands())
    assert commands.get("settings.edit-snippets") == "Settings › Edit Snippets"


def test_nothing_else_reaches_the_editor(window):
    """The menu entry is the only route in: no toolbar default, no context
    menu, no window-level action."""
    win = window()
    assert [
        a.text() for a in win.actions() if "nippet" in a.text()
    ] == []
    toolbar_actions = [
        a.text()
        for bar in win.findChildren(type(win._toolbar_ui.toolbar))
        for a in bar.actions()
    ]
    assert [t for t in toolbar_actions if "nippet" in t] == []


# -- the store the entry edits --------------------------------------------------


def test_the_window_loads_the_store_from_the_injected_config_dir(qtbot, tmp_path):
    save_snippets(tmp_path / SNIPPETS_FILENAME, (MINE,))
    win = MainWindow(
        generator_config_dir=tmp_path,
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
    )
    qtbot.addWidget(win)
    assert win._snippet_ui.path == tmp_path / SNIPPETS_FILENAME
    assert win._snippet_ui.snippets() == (MINE,)
    # ...and it is already in force in the SQL editors that exist at startup.
    assert win.center_stage.ddl_explorer_panel().editor.snippets() == (MINE,)


def test_without_a_store_the_shipped_defaults_stay_in_force(window):
    win = window()
    assert win._snippet_ui.snippets() == DEFAULT_SNIPPETS
    assert win.center_stage.ddl_explorer_panel().editor.snippets() == (
        DEFAULT_SNIPPETS
    )


def test_triggering_the_entry_opens_the_editor(window):
    win = window()
    win.set_workflow_mode(MODE_MAINTENANCE)
    _entry(win).trigger()
    dialog = win._snippet_ui.dialog()
    assert dialog is not None
    assert dialog.result_snippets() == DEFAULT_SNIPPETS
    dialog.reject()
