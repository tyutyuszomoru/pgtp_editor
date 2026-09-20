"""FQ-012 -- the Customize Shortcuts dialog.

Everything here is built from **stub rows**: the dialog takes its command list
injected and never walks a `QMenuBar`, so none of these tests constructs a
MainWindow, and none of them reaches `.exec()` (§30).
"""
import pytest
from PySide6.QtCore import Qt

from pgtp_editor.ui.customize_shortcuts_dialog import (
    COLUMN_COMMAND,
    COLUMN_NOTE,
    COLUMN_SHORTCUT,
    CustomizeShortcutsDialog,
)
from pgtp_editor.ui.shortcut_registry import CommandBinding, detect_conflicts

COMMANDS = [
    CommandBinding("file.open", "File › Open", "Ctrl+O"),
    CommandBinding("file.close", "File › Close", "Ctrl+W"),
    CommandBinding("navigation.next-bookmark", "Navigation › Next Bookmark", "F2"),
    CommandBinding("help.manual", "Help › Manual", "F1"),
    CommandBinding("tools.next-difference", "Tools › Next Difference", ""),
]


@pytest.fixture
def dialog(qtbot):
    dlg = CustomizeShortcutsDialog(COMMANDS)
    qtbot.addWidget(dlg)
    return dlg


def _row_of(dlg, command_id):
    for row in range(dlg.table.rowCount()):
        item = dlg.table.item(row, COLUMN_COMMAND)
        if item.data(Qt.ItemDataRole.UserRole) == command_id:
            return row
    raise AssertionError(f"no row for {command_id}")


# -- construction ------------------------------------------------------------


def test_builds_from_stub_data_with_no_menu_bar(dialog):
    # The load-bearing property: no QMenuBar, no MainWindow, no QAction. The
    # host owns the menu walk (`ToolbarController.collect_menu_commands`) and
    # injects its result.
    assert dialog.command_ids() == [c.command_id for c in COMMANDS]
    assert dialog.binding_of("file.open") == "Ctrl+O"
    assert dialog.binding_of("tools.next-difference") == ""


def test_shown_non_modally(dialog):
    # §30: never `.exec()`. `show()` is the whole interaction model, with the
    # caller reading the accessors back after `accepted`.
    dialog.show()
    assert dialog.isVisible()
    assert not dialog.isModal()
    dialog.close()


def test_overrides_are_applied_and_the_callers_map_is_not_aliased(qtbot):
    overrides = {"file.close": "Ctrl+M"}
    dlg = CustomizeShortcutsDialog(COMMANDS, overrides)
    qtbot.addWidget(dlg)
    assert dlg.binding_of("file.close") == "Ctrl+M"
    dlg.set_binding("file.close", "Ctrl+J")
    assert overrides == {"file.close": "Ctrl+M"}


def test_reserved_rows_are_listed_read_only(dialog):
    # FQ-012 decision 1: shown, greyed, with the reason -- an incomplete list
    # would read as a bug.
    assert "Ctrl+F" in dialog.reserved_sequences()
    assert "Ctrl+Z" in dialog.reserved_sequences()
    reserved_row = dialog.table.rowCount() - 1
    item = dialog.table.item(reserved_row, COLUMN_COMMAND)
    assert not item.flags() & Qt.ItemFlag.ItemIsSelectable
    assert dialog.table.item(reserved_row, COLUMN_NOTE).text()


def test_a_pinned_command_gets_a_read_only_row_too(dialog):
    row = _row_of(dialog, "help.manual")
    item = dialog.table.item(row, COLUMN_COMMAND)
    assert not item.flags() & Qt.ItemFlag.ItemIsSelectable
    assert "reserved" in dialog.table.item(row, COLUMN_NOTE).text()
    assert dialog.table.item(row, COLUMN_SHORTCUT).text() == "F1"


# -- conflicts ---------------------------------------------------------------


def test_conflict_is_announced_before_anything_is_committed(dialog):
    message = dialog.conflict_message("file.close", "ctrl+o")
    assert message and "File › Open" in message and "Ctrl+O" in message
    # Nothing changed by asking.
    assert dialog.binding_of("file.open") == "Ctrl+O"
    assert dialog.binding_of("file.close") == "Ctrl+W"


def test_no_conflict_message_for_a_free_key_or_the_commands_own_key(dialog):
    assert dialog.conflict_message("file.close", "Ctrl+M") is None
    assert dialog.conflict_message("file.open", "Ctrl+O") is None


def test_assigning_a_taken_key_steals_it_leaving_no_ambiguity(dialog):
    # Qt fires NEITHER action for an ambiguous shortcut, so the map must never
    # hold a duplicate -- the previous holder is cleared in the same step.
    stolen = dialog.set_binding("file.close", "Ctrl+O")
    assert stolen == ["file.open"]
    assert dialog.binding_of("file.open") == ""
    assert dialog.binding_of("file.close") == "Ctrl+O"
    assert detect_conflicts(dialog.bindings()) == {}
    assert dialog.table.item(_row_of(dialog, "file.open"), COLUMN_SHORTCUT).text() == ""


def test_a_reserved_key_is_refused_rather_than_stolen(dialog):
    assert dialog.refusal_message("file.close", "Ctrl+F") is not None
    with pytest.raises(ValueError):
        dialog.set_binding("file.close", "Ctrl+F")
    assert dialog.binding_of("file.close") == "Ctrl+W"


def test_a_pinned_command_refuses_every_assignment(dialog):
    assert dialog.refusal_message("help.manual", "Ctrl+M") is not None
    with pytest.raises(ValueError):
        dialog.set_binding("help.manual", "Ctrl+M")
    assert dialog.binding_of("help.manual") == "F1"


# -- mutations ---------------------------------------------------------------


def test_clear_and_reset_to_default(dialog):
    dialog.clear_binding("file.open")
    assert dialog.binding_of("file.open") == ""
    assert dialog.result_overrides() == {"file.open": ""}
    dialog.reset_to_default("file.open")
    assert dialog.binding_of("file.open") == "Ctrl+O"
    assert dialog.result_overrides() == {}


def test_reset_to_default_steals_its_key_back(dialog):
    dialog.set_binding("file.close", "Ctrl+O")
    stolen = dialog.reset_to_default("file.open")
    assert stolen == ["file.close"]
    assert dialog.binding_of("file.close") == ""


def test_restore_all_defaults_empties_the_override_map(dialog):
    dialog.set_binding("file.close", "Ctrl+J")
    dialog.set_binding("navigation.next-bookmark", "F4")
    assert dialog.result_overrides()
    dialog.restore_all_defaults()
    assert dialog.result_overrides() == {}
    assert dialog.bindings() == {
        "file.open": "Ctrl+O",
        "file.close": "Ctrl+W",
        "navigation.next-bookmark": "F2",
        "help.manual": "F1",
        "tools.next-difference": "",
    }


def test_result_overrides_after_accepted(qtbot, dialog):
    # The host's real wiring: read the map back when `accepted` fires.
    captured = {}
    dialog.accepted.connect(lambda: captured.update(dialog.result_overrides()))
    dialog.set_binding("navigation.next-bookmark", "F4")
    dialog.accept()
    assert captured == {"navigation.next-bookmark": "F4"}


def test_cancelling_changes_nothing(qtbot):
    host = {"overrides": {"file.close": "Ctrl+M"}}
    dlg = CustomizeShortcutsDialog(COMMANDS, host["overrides"])
    qtbot.addWidget(dlg)
    dlg.accepted.connect(lambda: host.update(overrides=dlg.result_overrides()))
    dlg.set_binding("file.close", "Ctrl+J")
    dlg.set_binding("file.open", "F7")
    dlg.reject()
    assert host["overrides"] == {"file.close": "Ctrl+M"}


# -- selection / capture seam ------------------------------------------------


def test_selecting_a_row_loads_its_key_into_the_capture_field(dialog):
    dialog.select_command("navigation.next-bookmark")
    assert dialog.current_command_id() == "navigation.next-bookmark"
    assert dialog.key_edit.keySequence().toString() == "F2"


def test_a_reserved_row_is_never_the_current_command(dialog):
    dialog.table.setCurrentCell(_row_of(dialog, "help.manual"), COLUMN_COMMAND)
    assert dialog.current_command_id() is None


def test_the_inline_label_shows_the_conflict_then_the_refusal(dialog):
    dialog.select_command("file.close")
    dialog.key_edit.setKeySequence("Ctrl+O")
    assert "File › Open" in dialog.message_label.text()
    dialog.key_edit.setKeySequence("Ctrl+F")
    assert "reserved" in dialog.message_label.text()


def test_assign_button_applies_the_captured_key(dialog):
    dialog.select_command("file.close")
    dialog.key_edit.setKeySequence("Ctrl+J")
    dialog.assign_button.click()
    assert dialog.binding_of("file.close") == "Ctrl+J"


def test_assign_button_refuses_a_reserved_key_without_changing_anything(dialog):
    dialog.select_command("file.close")
    dialog.key_edit.setKeySequence("Ctrl+F")
    dialog.assign_button.click()
    assert dialog.binding_of("file.close") == "Ctrl+W"
    assert "reserved" in dialog.message_label.text()
