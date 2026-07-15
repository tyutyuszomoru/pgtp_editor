"""Sub-project E -- CustomizeToolbarDialog tests.

The dialog is driven via its slot methods and accessors; never `.exec()`'d.
"""
from pgtp_editor.ui.customize_toolbar_dialog import CustomizeToolbarDialog
from pgtp_editor.ui.toolbar_registry import AVAILABLE_COMMANDS


def _dialog(qtbot, current_ids):
    dialog = CustomizeToolbarDialog(AVAILABLE_COMMANDS, current_ids)
    qtbot.addWidget(dialog)
    return dialog


def test_constructed_splits_current_and_available(qtbot):
    dialog = _dialog(qtbot, ["save", "open"])
    # On-toolbar shows current ids in order.
    assert dialog.selected_ids() == ["save", "open"]
    # Available shows the complement in registry order.
    assert dialog._available_ids() == ["undo", "redo", "find", "validate", "generate"]


def test_result_ids_matches_selected(qtbot):
    dialog = _dialog(qtbot, ["find", "validate"])
    assert dialog.result_ids() == dialog.selected_ids() == ["find", "validate"]


def test_set_ids_resets_both_lists(qtbot):
    dialog = _dialog(qtbot, ["save"])
    dialog.set_ids(["generate", "undo"])
    assert dialog.selected_ids() == ["generate", "undo"]
    assert dialog._available_ids() == ["open", "save", "redo", "find", "validate"]


def test_add_selected_moves_from_available_to_toolbar(qtbot):
    dialog = _dialog(qtbot, ["open"])
    # Select "undo" in the Available list, then Add.
    dialog._select_available("undo")
    dialog._add_selected()
    assert dialog.selected_ids() == ["open", "undo"]
    assert "undo" not in dialog._available_ids()


def test_remove_selected_moves_back_to_available_in_registry_order(qtbot):
    dialog = _dialog(qtbot, ["open", "save", "undo"])
    dialog._select_toolbar("save")
    dialog._remove_selected()
    assert dialog.selected_ids() == ["open", "undo"]
    # Available complement is kept in registry order.
    assert dialog._available_ids() == ["save", "redo", "find", "validate", "generate"]


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
