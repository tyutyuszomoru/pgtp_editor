"""Sub-project E -- CustomizeToolbarDialog tests.

The dialog is driven via its slot methods and accessors; never `.exec()`'d.
"""
from pgtp_editor.ui.customize_toolbar_dialog import CustomizeToolbarDialog
from pgtp_editor.ui.toolbar_registry import AVAILABLE_COMMANDS


def _dialog(qtbot, current_ids):
    dialog = CustomizeToolbarDialog(AVAILABLE_COMMANDS, current_ids)
    qtbot.addWidget(dialog)
    return dialog


def _enabled(dialog):
    return dialog._available_enabled_ids()


def _all_available(dialog):
    return dialog._available_ids()


def test_available_lists_all_commands_present_ones_disabled(qtbot):
    # default toolbar = all commands -> Available lists all, all disabled
    dialog = _dialog(qtbot, ["open", "save", "undo", "redo", "find", "validate", "generate"])
    assert _all_available(dialog) == ["open", "save", "undo", "redo", "find",
                                      "validate", "generate"]
    assert _enabled(dialog) == []            # everything already on the toolbar


def test_partial_toolbar_disables_only_present(qtbot):
    dialog = _dialog(qtbot, ["open", "save"])
    assert _all_available(dialog) == ["open", "save", "undo", "redo", "find",
                                      "validate", "generate"]
    assert _enabled(dialog) == ["undo", "redo", "find", "validate", "generate"]


def test_result_ids_matches_selected(qtbot):
    dialog = _dialog(qtbot, ["find", "validate"])
    assert dialog.result_ids() == dialog.selected_ids() == ["find", "validate"]


def test_set_ids_resets_both_lists(qtbot):
    dialog = _dialog(qtbot, ["save"])
    dialog.set_ids(["generate", "undo"])
    assert dialog.selected_ids() == ["generate", "undo"]
    assert _all_available(dialog) == ["open", "save", "undo", "redo", "find",
                                      "validate", "generate"]
    assert _enabled(dialog) == ["open", "save", "redo", "find", "validate"]


def test_add_enabled_command_moves_to_toolbar_and_disables_in_available(qtbot):
    dialog = _dialog(qtbot, ["open"])
    dialog._select_available("undo")
    dialog._add_selected()
    assert dialog.result_ids() == ["open", "undo"]
    assert "undo" not in _enabled(dialog)          # now greyed
    assert "undo" in _all_available(dialog)        # still listed


def test_remove_reenables_in_available(qtbot):
    dialog = _dialog(qtbot, ["open", "save"])
    dialog._select_toolbar("save")
    dialog._remove_selected()
    assert dialog.result_ids() == ["open"]
    assert "save" in _enabled(dialog)              # re-enabled


def test_add_on_present_id_is_noop(qtbot):
    dialog = _dialog(qtbot, ["open", "save"])
    dialog._select_available("open")   # already on toolbar (disabled)
    dialog._add_selected()
    assert dialog.result_ids() == ["open", "save"]   # unchanged, no duplicate


def test_move_up_reorders(qtbot):
    dialog = _dialog(qtbot, ["open", "save", "undo"])
    dialog._select_toolbar("undo")
    dialog._move_up()
    assert dialog.selected_ids() == ["open", "undo", "save"]


def test_move_down_reorders(qtbot):
    dialog = _dialog(qtbot, ["open", "save", "undo"])
    dialog._select_toolbar("open")
    dialog._move_down()
    assert dialog.selected_ids() == ["save", "open", "undo"]


def test_move_up_at_top_is_noop(qtbot):
    dialog = _dialog(qtbot, ["open", "save"])
    dialog._select_toolbar("open")
    dialog._move_up()
    assert dialog.selected_ids() == ["open", "save"]


def test_move_down_at_bottom_is_noop(qtbot):
    dialog = _dialog(qtbot, ["open", "save"])
    dialog._select_toolbar("save")
    dialog._move_down()
    assert dialog.selected_ids() == ["open", "save"]
