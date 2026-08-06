"""Sub-project E -- CustomizeToolbarDialog tests.

The dialog is driven via its slot methods and accessors; never `.exec()`'d.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from pgtp_editor.ui.customize_toolbar_dialog import CustomizeToolbarDialog

# The dialog is generic over whatever (id, label) pairs it is handed -- since
# BUG-027 that is the live menu walk, not a registry constant, so these tests
# supply their own fixed sample set rather than importing one.
AVAILABLE_COMMANDS = [
    ("open", "Open"),
    ("save", "Save"),
    ("undo", "Undo"),
    ("redo", "Redo"),
    ("find", "Find"),
    ("validate", "Validate"),
    ("generate", "Generate"),
]


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


def test_adding_all_remaining_leaves_available_all_disabled(qtbot):
    """Starting empty then adding every command reproduces the reported bug's
    end-state (all commands on the toolbar) -- Available must then be fully
    disabled, never emptied."""
    all_ids = [cid for cid, _label in AVAILABLE_COMMANDS]
    dialog = _dialog(qtbot, [])
    assert _enabled(dialog) == all_ids   # nothing on toolbar yet -> all addable

    for cid in list(all_ids):
        dialog._select_available(cid)
        dialog._add_selected()

    assert dialog.result_ids() == all_ids
    assert _all_available(dialog) == all_ids   # still lists every command
    assert _enabled(dialog) == []              # all now greyed


def test_result_order_preserved_through_add_remove_move_sequence(qtbot):
    """result_ids() tracks the toolbar-list order across a mix of operations."""
    dialog = _dialog(qtbot, ["open", "save"])

    dialog._select_available("undo")
    dialog._add_selected()                 # [open, save, undo]
    dialog._select_available("redo")
    dialog._add_selected()                 # [open, save, undo, redo]
    assert dialog.result_ids() == ["open", "save", "undo", "redo"]

    dialog._select_toolbar("save")
    dialog._remove_selected()              # [open, undo, redo]
    assert dialog.result_ids() == ["open", "undo", "redo"]

    dialog._select_toolbar("redo")
    dialog._move_up()                      # [open, redo, undo]
    assert dialog.result_ids() == ["open", "redo", "undo"]

    dialog._select_toolbar("open")
    dialog._move_down()                    # [redo, open, undo]
    assert dialog.result_ids() == ["redo", "open", "undo"]

    # Available reflects the final toolbar set: those three disabled, rest live.
    assert "save" in _enabled(dialog)
    for cid in ("open", "undo", "redo"):
        assert cid not in _enabled(dialog)


# -- FQ-004: per-button icon assignment -------------------------------------
#
# These use MENU-PATH ids so `toolbar_registry.ICON_ID_BY_COMMAND` defaults
# apply, which is what the real dialog is handed since BUG-027.

MENU_COMMANDS = [
    ("file.open", "File › Open"),
    ("file.save", "File › Save"),
    ("file.save-as", "File › Save As"),
    ("edit.undo", "Edit › Undo"),
]


def _menu_dialog(qtbot, current_ids, icon_assignments=None):
    dialog = CustomizeToolbarDialog(
        MENU_COMMANDS, current_ids, None, icon_assignments
    )
    qtbot.addWidget(dialog)
    return dialog


def _row_has_icon(dialog, command_id):
    for row in range(dialog.toolbar_list.count()):
        item = dialog.toolbar_list.item(row)
        if item.data(Qt.ItemDataRole.UserRole) == command_id:
            return not item.icon().isNull()
    raise AssertionError(f"{command_id} not on the toolbar list")


def test_no_assignments_means_default_icons_back_compat(qtbot):
    dialog = _menu_dialog(qtbot, ["file.open", "file.save-as"])
    assert dialog.icon_assignments() == {}
    # Legacy default survives; the icon-less command stays icon-less.
    assert dialog.effective_icon_id("file.open") == "open"
    assert dialog.effective_icon_id("file.save-as") is None
    assert _row_has_icon(dialog, "file.open")
    assert not _row_has_icon(dialog, "file.save-as")


def test_assignment_map_round_trips_through_the_seam(qtbot):
    dialog = _menu_dialog(qtbot, ["file.save-as"])
    dialog.assign_icon("file.save-as", "document-save-as")
    assert dialog.icon_assignments() == {"file.save-as": "document-save-as"}
    assert dialog.effective_icon_id("file.save-as") == "document-save-as"
    assert _row_has_icon(dialog, "file.save-as")


def test_initial_assignments_are_honored(qtbot):
    dialog = _menu_dialog(
        qtbot, ["file.save-as"], {"file.save-as": "zoom-in"}
    )
    assert dialog.effective_icon_id("file.save-as") == "zoom-in"
    assert _row_has_icon(dialog, "file.save-as")


def test_assignment_overrides_a_legacy_default(qtbot):
    dialog = _menu_dialog(qtbot, ["file.open"])
    assert dialog.effective_icon_id("file.open") == "open"
    dialog.assign_icon("file.open", "zoom-in")
    assert dialog.effective_icon_id("file.open") == "zoom-in"


def test_clearing_an_assignment_restores_the_default(qtbot):
    dialog = _menu_dialog(qtbot, ["file.open", "file.save-as"])
    dialog.assign_icon("file.open", "zoom-in")
    dialog.assign_icon("file.save-as", "zoom-in")
    dialog.assign_icon("file.open", None)          # picker "Default" choice
    dialog.assign_icon("file.save-as", None)
    assert dialog.icon_assignments() == {}
    assert dialog.effective_icon_id("file.open") == "open"
    assert dialog.effective_icon_id("file.save-as") is None
    assert not _row_has_icon(dialog, "file.save-as")


def test_set_icon_assignments_replaces_the_map(qtbot):
    dialog = _menu_dialog(qtbot, ["file.open"], {"file.open": "zoom-in"})
    dialog.set_icon_assignments({"file.open": "document-save-as"})
    assert dialog.icon_assignments() == {"file.open": "document-save-as"}
    dialog.set_icon_assignments(None)
    assert dialog.icon_assignments() == {}


def test_assignments_survive_reordering_and_readding(qtbot):
    dialog = _menu_dialog(qtbot, ["file.open", "file.save-as"])
    dialog.assign_icon("file.save-as", "zoom-in")
    dialog._select_toolbar("file.save-as")
    dialog._move_up()
    assert dialog.selected_ids() == ["file.save-as", "file.open"]
    assert dialog.icon_assignments() == {"file.save-as": "zoom-in"}
    assert _row_has_icon(dialog, "file.save-as")


def test_result_icon_assignments_prunes_removed_buttons(qtbot):
    dialog = _menu_dialog(qtbot, ["file.open", "file.save-as"])
    dialog.assign_icon("file.save-as", "zoom-in")
    dialog._select_toolbar("file.save-as")
    dialog._remove_selected()
    assert dialog.result_icon_assignments() == {}


def test_choose_icon_without_a_selection_is_a_no_op(qtbot):
    """The picker slot must not open (or crash) with nothing selected -- this
    is the only path that would `.exec()`."""
    dialog = _menu_dialog(qtbot, ["file.open"])
    dialog.toolbar_list.setCurrentRow(-1)
    dialog._choose_icon()
    assert dialog.icon_assignments() == {}


def _patch_picker(monkeypatch, *, accepted, chosen):
    """Stub out the modal picker: never `.exec()` a real dialog in a test."""
    from pgtp_editor.ui import icon_picker_dialog as picker_module

    seen = {}

    class _StubPicker:
        def __init__(self, current_icon_id, color, parent=None):
            seen["current"] = current_icon_id

        def exec(self):
            return (
                QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
            )

        def chosen_icon_id(self):
            return chosen

    monkeypatch.setattr(picker_module, "IconPickerDialog", _StubPicker)
    return seen


def test_choose_icon_applies_the_pickers_choice_to_the_selected_row(
    qtbot, monkeypatch
):
    dialog = _menu_dialog(qtbot, ["file.open", "file.save-as"])
    seen = _patch_picker(monkeypatch, accepted=True, chosen="zoom-in")
    dialog._select_toolbar("file.save-as")
    dialog._choose_icon()
    # The picker is seeded with that row's current assignment (none yet)...
    assert seen["current"] is None
    # ...and its choice lands on that row only.
    assert dialog.icon_assignments() == {"file.save-as": "zoom-in"}
    assert dialog.effective_icon_id("file.open") == "open"


def test_choose_icon_seeds_the_picker_with_the_rows_existing_assignment(
    qtbot, monkeypatch
):
    dialog = _menu_dialog(qtbot, ["file.save-as"])
    dialog.assign_icon("file.save-as", "zoom-in")
    seen = _patch_picker(monkeypatch, accepted=True, chosen="document-save-as")
    dialog._select_toolbar("file.save-as")
    dialog._choose_icon()
    assert seen["current"] == "zoom-in"
    assert dialog.icon_assignments() == {"file.save-as": "document-save-as"}


def test_choose_icon_reset_to_default_clears_the_assignment(qtbot, monkeypatch):
    """The picker's "Default" cell yields `None`, which must remove the
    assignment rather than store a null one."""
    dialog = _menu_dialog(qtbot, ["file.open"])
    dialog.assign_icon("file.open", "zoom-in")
    _patch_picker(monkeypatch, accepted=True, chosen=None)
    dialog._select_toolbar("file.open")
    dialog._choose_icon()
    assert dialog.icon_assignments() == {}
    assert dialog.effective_icon_id("file.open") == "open"


def test_cancelling_the_picker_leaves_the_assignment_untouched(qtbot, monkeypatch):
    dialog = _menu_dialog(qtbot, ["file.save-as"])
    dialog.assign_icon("file.save-as", "zoom-in")
    _patch_picker(monkeypatch, accepted=False, chosen="document-save-as")
    dialog._select_toolbar("file.save-as")
    dialog._choose_icon()
    assert dialog.icon_assignments() == {"file.save-as": "zoom-in"}
