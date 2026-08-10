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
"""FQ-028 Part 2 (absorbing FQ-029) — the colour-coded mode indicator.

The load-bearing property is **one source of truth**: `MainWindow.current_mode()`
is the only place that answers "what mode am I in", and both the toolbar panel
and the status-bar label are written by the single `_refresh_mode_indicator`.
A second, drifting notion of the mode is precisely what these tests exist to
make impossible.

Mode terminology is §7's and gains no fifth meaning: **major** = FQ-027's
SESSION workflow mode (in-memory, never a QSettings key), **minor** = an active
editor sub-state, shown only when there is one.
"""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.launcher_dialog import (
    MODE_MAINTENANCE,
    MODE_PROJECT,
    MODE_STANDALONE,
)
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.mode_indicator import (
    MINOR_CAPTION,
    MINOR_DIFF,
    MINOR_XSD,
    NO_MODE_LABEL,
    ModeIndicator,
    mode_colors,
    mode_text,
)

from ._menu_helpers import find_action, find_top_menu


def _window(qtbot, tmp_path):
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    return window


def _both(window):
    return window._mode_label.text(), window.toolbar_mode_indicator.text()


# --- The pure half ----------------------------------------------------------


def test_mode_text_shows_the_minor_mode_only_when_there_is_one():
    assert mode_text(MODE_PROJECT) == "Project"
    assert mode_text(MODE_PROJECT, MINOR_CAPTION) == "Project · Caption"
    assert mode_text(None) == NO_MODE_LABEL


def test_mode_colors_are_theme_aware_and_pure():
    """Not the DEBUG chip's hardcoded red: every major mode has a light and a
    dark pair, and the builder mutates nothing."""
    light = mode_colors(True)
    dark = mode_colors(False)
    for mode in (None, MODE_STANDALONE, MODE_PROJECT, MODE_MAINTENANCE):
        assert light[mode] != dark[mode]
    light[MODE_PROJECT] = ("#000000", "#000000")
    assert mode_colors(True)[MODE_PROJECT] != ("#000000", "#000000")


def test_the_three_major_modes_are_told_apart_by_colour():
    palette = mode_colors(False)
    backgrounds = {
        palette[MODE_STANDALONE][0],
        palette[MODE_PROJECT][0],
        palette[MODE_MAINTENANCE][0],
    }
    assert len(backgrounds) == 3


def test_the_minor_mode_is_text_not_a_second_colour(qtbot):
    """A 3x4 colour grid would defeat "easy recognition"; the background stays
    the MAJOR mode's."""
    indicator = ModeIndicator(light=False)
    qtbot.addWidget(indicator)
    indicator.set_mode(MODE_PROJECT, None)
    plain = indicator.colors()
    indicator.set_mode(MODE_PROJECT, MINOR_CAPTION)

    assert indicator.colors() == plain
    assert indicator.text() == "Project · Caption"


# --- One source of truth, two surfaces --------------------------------------


def test_both_surfaces_exist_and_start_at_the_same_defined_fact(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    assert isinstance(window._mode_label, ModeIndicator)
    assert isinstance(window.toolbar_mode_indicator, ModeIndicator)
    assert _both(window) == (NO_MODE_LABEL, NO_MODE_LABEL)
    assert window.current_mode() == (None, None)


def test_the_indicator_tracks_workflow_mode_through_a_change(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window.set_workflow_mode(MODE_MAINTENANCE)

    assert window.current_mode() == (MODE_MAINTENANCE, None)
    assert _both(window) == ("Maintenance", "Maintenance")
    assert (
        window._mode_label.colors()
        == window.toolbar_mode_indicator.colors()
        == mode_colors(False)[MODE_MAINTENANCE]
    )


def test_new_session_keeps_the_indicator_on_the_standing_mode(
    qtbot, tmp_path, monkeypatch
):
    """BUG-059 reversed FQ-027's clear-on-New-Session: the mode STANDS while the
    re-opened launcher is up, so the indicator keeps showing it. It is not a
    stale label -- it is the mode a dismissed launcher lands back in, and "No
    Mode" is no longer reachable by any gesture."""
    window = _window(qtbot, tmp_path)
    window.set_workflow_mode(MODE_PROJECT)
    assert _both(window) == ("Project", "Project")
    monkeypatch.setattr(window, "show_launcher", lambda: None)

    assert window.new_session() is True

    assert window.workflow_mode == MODE_PROJECT
    assert _both(window) == ("Project", "Project")


def test_the_mode_is_session_only_and_never_persisted(qtbot, tmp_path):
    """FQ-027's ruling, which this indicator only DISPLAYS: a filtered mode can
    never be inherited across a restart."""
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    first = MainWindow(settings=settings)
    qtbot.addWidget(first)
    first.set_workflow_mode(MODE_MAINTENANCE)
    first.close()

    second = MainWindow(settings=settings)
    qtbot.addWidget(second)

    assert second.workflow_mode is None
    assert second._mode_label.text() == NO_MODE_LABEL
    assert not any("mode" in key.casefold() for key in settings.allKeys())


# --- The minor modes --------------------------------------------------------


def test_caption_mode_appears_as_a_minor_mode_and_leaves_again(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.set_workflow_mode(MODE_STANDALONE)
    window.center_stage.xml_editor.setPlainText(
        '<Root>\n  <Page caption="Home"/>\n</Root>'
    )

    find_action(find_top_menu(window, "Tools"), "Manage Captions...").trigger()
    assert window.current_mode() == (MODE_STANDALONE, MINOR_CAPTION)
    assert _both(window) == ("Standalone · Caption", "Standalone · Caption")

    window.center_stage.caption_management_panel.close_panel()
    assert window.current_mode() == (MODE_STANDALONE, None)
    assert _both(window) == ("Standalone", "Standalone")


def test_compare_merge_appears_as_a_minor_mode(qtbot, tmp_path):
    """FQ-021 made Compare/Merge a MODE that outlives its tab being current, so
    the indicator follows the mode signal, not the tab switch."""
    window = _window(qtbot, tmp_path)
    window.set_workflow_mode(MODE_PROJECT)

    window.center_stage.enter_diff_merge_mode()
    assert window.current_mode() == (MODE_PROJECT, MINOR_DIFF)
    assert window._mode_label.text() == "Project · Compare/Merge"

    window.center_stage.leave_diff_merge_mode()
    assert window.current_mode() == (MODE_PROJECT, None)


def test_edit_xsd_appears_as_a_minor_mode(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window.center_stage.show_edit_xsd()
    assert window.current_mode() == (None, MINOR_XSD)
    assert window.toolbar_mode_indicator.text() == f"{NO_MODE_LABEL} · {MINOR_XSD}"

    window.center_stage.hide_edit_xsd()
    assert window.current_mode() == (None, None)


# --- Placement and posture --------------------------------------------------


def test_the_toolbar_panel_is_right_anchored_behind_an_expanding_spacer(
    qtbot, tmp_path
):
    """A `QToolBar` is movable, so "to the right of the toolbar" only holds if
    the panel is IN it, last, behind an expanding spacer."""
    from PySide6.QtWidgets import QSizePolicy

    window = _window(qtbot, tmp_path)
    toolbar = window._toolbar_ui.toolbar
    actions = toolbar.actions()

    assert toolbar.widgetForAction(actions[-1]) is window.toolbar_mode_indicator
    spacer = toolbar.widgetForAction(actions[-2])
    assert spacer.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    # ...and it is NOT a command: Customize Toolbar never sees it.
    assert window.toolbar_mode_indicator not in [
        toolbar.widgetForAction(a) for a in window._toolbar_ui.command_actions
    ]


def test_the_panel_survives_a_customize_toolbar_rebuild(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    ids = list(window._toolbar_ui.command_ids)

    window._toolbar_ui.apply_ids(ids[:1])

    toolbar = window._toolbar_ui.toolbar
    assert toolbar.widgetForAction(toolbar.actions()[-1]) is window.toolbar_mode_indicator


def test_the_indicator_is_passive(qtbot, tmp_path):
    """Owner ruling: no click, no context menu, no mode switching from either
    surface. Mode changes stay with the launcher pick and New Session."""
    from PySide6.QtCore import Qt

    window = _window(qtbot, tmp_path)
    for indicator in (window._mode_label, window.toolbar_mode_indicator):
        assert indicator.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu
        assert not indicator.actions()
        assert not hasattr(indicator, "clicked")


def test_a_theme_flip_re_renders_both_surfaces(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.set_workflow_mode(MODE_PROJECT)
    dark = window._mode_label.colors()

    window._light_theme_action.setChecked(True)  # fires the real toggle slot

    assert window._mode_label.colors() == mode_colors(True)[MODE_PROJECT]
    assert window.toolbar_mode_indicator.colors() == mode_colors(True)[MODE_PROJECT]
    assert window._mode_label.colors() != dark
    # Leave the app palette as the suite found it.
    window._light_theme_action.setChecked(False)
    assert QApplication.instance() is not None


# --- FQ-032: the THIRD segment, the focused editor's editing mode ------------


def test_the_editing_mode_segment_is_present_on_a_focused_editable_editor(
    qtbot, tmp_path
):
    """`set_mode(major, minor)` gained a third argument, and both surfaces still
    render from the ONE `_refresh_mode_indicator` call."""
    from pgtp_editor.ui.mode_indicator import EDITING_COMMAND, EDITING_EDIT

    window = _window(qtbot, tmp_path)
    window.show()
    qtbot.waitExposed(window)
    editor = window.center_stage.xml_editor
    editor.setFocus()
    QApplication.processEvents()
    window._refresh_mode_indicator()
    assert _both(window) == (
        f"{NO_MODE_LABEL} · {EDITING_EDIT}",
        f"{NO_MODE_LABEL} · {EDITING_EDIT}",
    )

    QTest.keyClick(editor, Qt.Key.Key_Escape)
    assert _both(window) == (
        f"{NO_MODE_LABEL} · {EDITING_COMMAND}",
        f"{NO_MODE_LABEL} · {EDITING_COMMAND}",
    )


def test_an_editing_mode_transition_is_a_TRIGGER_for_the_one_refresh(qtbot, tmp_path):
    """The indicator follows a transition on ANY editor -- published through
    `vim_mode.add_editing_mode_observer`, the bookmark-observer idiom -- so no tab
    creation site needs a wiring line."""
    from pgtp_editor.ui.mode_indicator import EDITING_COMMAND

    window = _window(qtbot, tmp_path)
    window.show()
    qtbot.waitExposed(window)
    editor = window.center_stage.xml_editor
    editor.setFocus()
    QApplication.processEvents()
    editor.enter_command_mode()  # no keystroke: only the publish can move the chip
    assert EDITING_COMMAND in window._mode_label.text()


def test_the_segment_is_ABSENT_when_the_focused_editor_is_read_only(qtbot, tmp_path):
    """FQ-032 makes the layer inactive on a read-only buffer, and a read-only
    buffer already names itself in its tab title."""
    from pgtp_editor.ui.mode_indicator import EDITING_COMMAND, EDITING_EDIT

    window = _window(qtbot, tmp_path)
    window.show()
    qtbot.waitExposed(window)
    editor = window.center_stage.xml_editor
    editor.setReadOnly(True)
    editor.setFocus()
    QApplication.processEvents()
    window._refresh_mode_indicator()
    text = window._mode_label.text()
    assert EDITING_EDIT not in text and EDITING_COMMAND not in text
    editor.setReadOnly(False)


def test_the_segment_is_ABSENT_on_a_non_editor_focus(qtbot, tmp_path):
    from pgtp_editor.ui.mode_indicator import EDITING_EDIT

    window = _window(qtbot, tmp_path)
    window.show()
    qtbot.waitExposed(window)
    window.project_tree.setFocus()
    QApplication.processEvents()
    window._refresh_mode_indicator()
    assert EDITING_EDIT not in window._mode_label.text()
    assert window.focused_editing_mode() is None


def test_the_palette_namespace_IS_the_menu_tree(qtbot, tmp_path):
    """Derive, don't design: the `:` verbs are the shipped FQ-012 enumeration, so
    the namespace auto-syncs as the menus change."""
    window = _window(qtbot, tmp_path)
    entries = window.vim_command_entries()
    assert entries
    labels = {label for _cid, label in entries}
    assert any("›" in label for label in labels), "the verb is the FULL menu path"
    command_id = entries[0][0]
    assert window.vim_command_action(command_id) is not None
    assert window.vim_command_action("no.such.command") is None


def test_an_editor_inside_the_window_resolves_the_palette_namespace(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.show()
    qtbot.waitExposed(window)
    editor = window.center_stage.xml_editor
    assert editor.vim_command_entries()
