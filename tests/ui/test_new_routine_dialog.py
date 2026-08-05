# tests/ui/test_new_routine_dialog.py
"""Tests for NewRoutineDialog (FQ-002) — driven entirely by methods.

The dialog is never `.exec()`-ed (modal-hang guardrail) and never touches a
database: it collects three fields and delegates to the pure renderer in
`db/ddl_skeleton.py`, so the assertions are on returned text and widget state.

The load-bearing correctness property here is the procedure/return-type
interaction: a procedure must not merely *tolerate* a blank return type, it
must be structurally incapable of emitting a `RETURNS` clause.
"""
import pytest

from pgtp_editor.db.ddl_skeleton import SkeletonError
from pgtp_editor.ui.new_routine_dialog import (
    KIND_FUNCTION,
    KIND_PROCEDURE,
    NewRoutineDialog,
)


def _dialog(qtbot, *, name="", kind=None, return_type=None):
    dialog = NewRoutineDialog()
    qtbot.addWidget(dialog)
    if name:
        dialog._name_edit.setText(name)
    if kind is not None:
        dialog._kind_combo.setCurrentIndex(dialog._kind_combo.findData(kind))
    if return_type is not None:
        dialog._return_type_combo.setCurrentText(return_type)
    return dialog


def _ok_enabled(dialog):
    from PySide6.QtWidgets import QDialogButtonBox

    return dialog._buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


# --- Defaults ---------------------------------------------------------------
def test_defaults_to_a_function_returning_trigger(qtbot):
    """The headline FQ-002 flow (a trigger function) should need no field
    changes beyond the name."""
    dialog = _dialog(qtbot)
    assert dialog.kind() == KIND_FUNCTION
    assert dialog.return_type() == "trigger"


def test_blank_form_does_not_scold_but_blocks_ok(qtbot):
    dialog = _dialog(qtbot)
    assert dialog._error_label.text() == ""
    assert not _ok_enabled(dialog)


# --- Rendered skeletons -----------------------------------------------------
def test_function_skeleton(qtbot):
    dialog = _dialog(qtbot, name="touch_updated_at", return_type="trigger")

    sql = dialog.skeleton()

    assert sql == (
        'CREATE OR REPLACE FUNCTION "touch_updated_at"()\n'
        "RETURNS trigger\n"
        "LANGUAGE plpgsql\n"
        "AS $$\n"
        "BEGIN\n"
        "    -- TODO: implement\n"
        "    RETURN NULL;\n"
        "END;\n"
        "$$;\n"
    )
    assert dialog.validation_error() is None
    assert _ok_enabled(dialog)


def test_procedure_skeleton(qtbot):
    dialog = _dialog(qtbot, name="rebuild_cache", kind=KIND_PROCEDURE)

    sql = dialog.skeleton()

    assert sql == (
        'CREATE OR REPLACE PROCEDURE "rebuild_cache"()\n'
        "LANGUAGE plpgsql\n"
        "AS $$\n"
        "BEGIN\n"
        "    -- TODO: implement\n"
        "END;\n"
        "$$;\n"
    )


def test_void_function_omits_the_return_null_stub(qtbot):
    """`RETURN NULL;` is a runtime error in a void function."""
    dialog = _dialog(qtbot, name="do_stuff", return_type="void")

    sql = dialog.skeleton()

    assert "RETURNS void" in sql
    assert "RETURN NULL;" not in sql


def test_precision_and_array_types_reach_the_renderer(qtbot):
    """The combo is editable, so a type that is not in the seeded list still
    renders — the renderer's allowlist, not the dropdown, is the constraint."""
    for return_type in ("numeric(10,2)", "integer[]", "pr.my_domain"):
        dialog = _dialog(qtbot, name="calc", return_type=return_type)
        assert dialog.validation_error() is None, return_type
        assert f"RETURNS {return_type}\n" in dialog.skeleton()


def test_schema_qualified_name_is_quoted_part_by_part(qtbot):
    dialog = _dialog(qtbot, name="pr.touch_row", return_type="trigger")
    assert 'FUNCTION "pr"."touch_row"()' in dialog.skeleton()


# --- Kind switching hides/disables the return type -------------------------
def test_switching_to_procedure_hides_and_disables_the_return_type(qtbot):
    dialog = _dialog(qtbot, name="rebuild_cache", return_type="integer")
    assert dialog._return_type_combo.isEnabled()

    dialog._kind_combo.setCurrentIndex(dialog._kind_combo.findData(KIND_PROCEDURE))

    assert not dialog._return_type_combo.isVisibleTo(dialog)
    assert not dialog._return_type_label.isVisibleTo(dialog)
    assert not dialog._return_type_combo.isEnabled()
    # Not merely optional: no return type is reported, and none is emitted.
    assert dialog.return_type() == ""
    assert "RETURNS" not in dialog.skeleton()
    assert "integer" not in dialog.skeleton()


def test_switching_back_to_function_restores_the_return_type(qtbot):
    dialog = _dialog(qtbot, name="calc", return_type="bigint", kind=KIND_PROCEDURE)

    dialog._kind_combo.setCurrentIndex(dialog._kind_combo.findData(KIND_FUNCTION))

    assert dialog._return_type_combo.isEnabled()
    assert dialog._return_type_label.isVisibleTo(dialog)
    assert dialog.return_type() == "bigint"
    assert "RETURNS bigint" in dialog.skeleton()


def test_a_procedure_never_needs_a_return_type_to_be_valid(qtbot):
    dialog = _dialog(qtbot, name="rebuild_cache", return_type="", kind=KIND_PROCEDURE)
    assert dialog.validation_error() is None
    assert _ok_enabled(dialog)


# --- Validation -------------------------------------------------------------
def test_empty_name_blocks_accept(qtbot):
    dialog = _dialog(qtbot, return_type="trigger")
    got = []
    dialog.accepted.connect(lambda: got.append(True))

    dialog._on_accept_clicked()

    assert got == []
    assert "name" in dialog.validation_error().lower()
    assert not _ok_enabled(dialog)


def test_whitespace_only_name_is_treated_as_empty(qtbot):
    dialog = _dialog(qtbot, name="   ", return_type="trigger")
    assert dialog.validation_error() is not None
    assert not _ok_enabled(dialog)


def test_function_without_a_return_type_blocks_accept(qtbot):
    dialog = _dialog(qtbot, name="calc", return_type="")
    got = []
    dialog.accepted.connect(lambda: got.append(True))

    dialog._on_accept_clicked()

    assert got == []
    assert "return type" in dialog.validation_error().lower()
    assert not _ok_enabled(dialog)


def test_hostile_name_surfaces_as_inline_validation(qtbot):
    """Refused, not escaped — and no exception escapes to the caller."""
    dialog = _dialog(qtbot, name='evil"; DROP TABLE t; --', return_type="trigger")

    error = dialog.validation_error()

    assert error is not None
    assert "identifier" in error.lower()
    assert not _ok_enabled(dialog)
    assert dialog._error_label.text() == error


def test_hostile_return_type_surfaces_as_inline_validation(qtbot):
    dialog = _dialog(qtbot, name="calc", return_type="integer; DROP TABLE t")

    error = dialog.validation_error()

    assert error is not None
    assert not _ok_enabled(dialog)


def test_accept_with_valid_fields_emits_accepted(qtbot):
    dialog = _dialog(qtbot, name="touch_updated_at", return_type="trigger")
    got = []
    dialog.accepted.connect(lambda: got.append(True))

    dialog._on_accept_clicked()

    assert got == [True]


def test_skeleton_raises_rather_than_emitting_half_formed_sql(qtbot):
    """`skeleton()` is not a silent-degrade path: for input the dialog would
    have refused, it propagates the renderer's refusal."""
    dialog = _dialog(qtbot, name="calc", return_type="")
    with pytest.raises(SkeletonError):
        dialog.skeleton()
