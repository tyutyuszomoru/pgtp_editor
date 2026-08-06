# tests/ui/test_new_trigger_dialog.py
"""Tests for NewTriggerDialog (FQ-002) — driven entirely by methods.

The dialog is never `.exec()`-ed (modal-hang guardrail) and opens no
connection: the candidate trigger-function list is injected, so these tests
never touch a database. The SQL is asserted against `db/ddl_skeleton.py`'s
output rather than a hand-typed string wherever the point is "the dialog feeds
the emitter", and against a golden string where the point is "this is what the
user sees pasted into the tab".
"""
import pytest
from PySide6.QtWidgets import QDialogButtonBox

from pgtp_editor.db.ddl_skeleton import (
    TRIGGER_EVENTS,
    TRIGGER_LEVELS,
    TRIGGER_TIMINGS,
    trigger_skeleton,
)
from pgtp_editor.ui.new_trigger_dialog import NewTriggerDialog

FUNCTIONS = ["public.audit_stamp", "public.touch_updated_at"]


def _dialog(qtbot, table="public.orders", functions=None):
    dialog = NewTriggerDialog(table, FUNCTIONS if functions is None else functions)
    qtbot.addWidget(dialog)
    return dialog


def _ok(dialog):
    return dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)


def _fill(dialog, name="orders_audit", events=("INSERT",)):
    dialog._name_edit.setText(name)
    for event in events:
        dialog._event_checks[event].setChecked(True)
    return dialog


# --- The rendered skeleton ------------------------------------------------
def test_representative_selection_renders_the_expected_skeleton(qtbot):
    dialog = _dialog(qtbot)
    _fill(dialog, "orders_audit", ("INSERT",))
    dialog._timing_combo.setCurrentText("AFTER")
    dialog._level_combo.setCurrentText("FOR EACH ROW")
    dialog._function_combo.setCurrentText("public.audit_stamp")

    assert dialog.skeleton() == (
        'CREATE TRIGGER "orders_audit"\n'
        'AFTER INSERT ON "public"."orders"\n'
        "FOR EACH ROW\n"
        'EXECUTE FUNCTION "public"."audit_stamp"();\n'
    )
    assert dialog.validation_error() is None
    assert dialog.is_valid()


def test_skeleton_matches_the_emitter_for_the_current_field_state(qtbot):
    dialog = _dialog(qtbot)
    _fill(dialog, "orders_touch", ("UPDATE",))
    dialog._timing_combo.setCurrentText("BEFORE")
    dialog._level_combo.setCurrentText("FOR EACH STATEMENT")
    dialog._function_combo.setCurrentText("public.touch_updated_at")

    assert dialog.skeleton() == trigger_skeleton(
        name="orders_touch",
        table="public.orders",
        timing="BEFORE",
        events=["UPDATE"],
        level="FOR EACH STATEMENT",
        function_name="public.touch_updated_at",
    )


def test_multiple_events_reach_the_renderer_combined_with_or(qtbot):
    dialog = _dialog(qtbot)
    _fill(dialog, "orders_audit", ("DELETE", "INSERT", "UPDATE"))
    dialog._timing_combo.setCurrentText("AFTER")

    assert dialog.events() == ["INSERT", "UPDATE", "DELETE"]  # canonical order
    assert "AFTER INSERT OR UPDATE OR DELETE" in dialog.skeleton()
    assert dialog.is_valid()


def test_unqualified_table_is_passed_through_verbatim(qtbot):
    dialog = _dialog(qtbot, table="orders")
    _fill(dialog)

    assert dialog.table() == "orders"
    assert 'ON "orders"\n' in dialog.skeleton()


# --- Choices are driven off the emitter's constants -----------------------
def test_offered_timings_are_exactly_the_emitters(qtbot):
    dialog = _dialog(qtbot)
    offered = [dialog._timing_combo.itemText(i) for i in range(dialog._timing_combo.count())]
    assert offered == list(TRIGGER_TIMINGS)


def test_offered_levels_are_exactly_the_emitters(qtbot):
    dialog = _dialog(qtbot)
    offered = [dialog._level_combo.itemText(i) for i in range(dialog._level_combo.count())]
    assert offered == list(TRIGGER_LEVELS)
    # Postgres has no transaction-level trigger — FQ-002's original wording was
    # corrected and must not reappear.
    assert not any("TRANSACTION" in level.upper() for level in offered)


def test_offered_events_are_exactly_the_emitters(qtbot):
    dialog = _dialog(qtbot)
    assert list(dialog._event_checks) == list(TRIGGER_EVENTS)


@pytest.mark.parametrize("timing", TRIGGER_TIMINGS)
@pytest.mark.parametrize("level", TRIGGER_LEVELS)
def test_every_offered_timing_and_level_renders(qtbot, timing, level):
    dialog = _dialog(qtbot)
    _fill(dialog)
    dialog._timing_combo.setCurrentText(timing)
    dialog._level_combo.setCurrentText(level)

    assert dialog.is_valid()
    assert dialog.skeleton().startswith('CREATE TRIGGER "orders_audit"\n')
    assert f"{timing} INSERT" in dialog.skeleton()
    assert f"\n{level}\n" in dialog.skeleton()


# --- Validation -----------------------------------------------------------
def test_ok_is_disabled_until_the_form_is_complete(qtbot):
    dialog = _dialog(qtbot)
    assert not _ok(dialog).isEnabled()

    _fill(dialog)
    assert _ok(dialog).isEnabled()


def test_empty_name_blocks_ok(qtbot):
    dialog = _dialog(qtbot)
    dialog._event_checks["INSERT"].setChecked(True)

    assert dialog.skeleton() == ""
    assert "name" in dialog.validation_error().lower()
    assert not _ok(dialog).isEnabled()


def test_whitespace_only_name_blocks_ok(qtbot):
    dialog = _dialog(qtbot)
    _fill(dialog, "   ")

    assert not dialog.is_valid()
    assert not _ok(dialog).isEnabled()


def test_no_event_selected_blocks_ok(qtbot):
    dialog = _dialog(qtbot)
    dialog._name_edit.setText("orders_audit")

    assert dialog.events() == []
    assert dialog.skeleton() == ""
    assert "event" in dialog.validation_error().lower()
    assert not _ok(dialog).isEnabled()


def test_unchecking_the_last_event_re_blocks_ok(qtbot):
    dialog = _dialog(qtbot)
    _fill(dialog)
    assert _ok(dialog).isEnabled()

    dialog._event_checks["INSERT"].setChecked(False)
    assert not _ok(dialog).isEnabled()


def test_accept_is_refused_while_invalid(qtbot):
    dialog = _dialog(qtbot)
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))

    dialog._on_accept_clicked()  # as if OK were clicked programmatically

    assert accepted == []
    assert dialog.result() != 1


def test_accept_goes_through_once_valid(qtbot):
    dialog = _dialog(qtbot)
    _fill(dialog)
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))

    dialog._on_accept_clicked()

    assert accepted == [True]


# --- No trigger functions in the database --------------------------------
def test_empty_function_list_says_so_and_blocks_ok(qtbot):
    dialog = _dialog(qtbot, functions=[])
    _fill(dialog)

    assert dialog.candidate_functions() == []
    assert dialog.function_name() == ""
    assert dialog.skeleton() == ""
    assert "RETURNS trigger" in dialog.validation_error()
    assert not _ok(dialog).isEnabled()
    assert not dialog._function_combo.isEnabled()


def test_functions_may_be_injected_as_a_callable(qtbot):
    dialog = NewTriggerDialog("public.orders", lambda: ["public.b_fn", "public.a_fn"])
    qtbot.addWidget(dialog)

    assert dialog.candidate_functions() == ["public.a_fn", "public.b_fn"]
    assert dialog.function_name() == "public.a_fn"


def test_duplicate_candidates_are_collapsed(qtbot):
    dialog = _dialog(qtbot, functions=["public.f", "public.f"])
    assert dialog.candidate_functions() == ["public.f"]


# --- Hostile identifiers surface as validation, not a traceback -----------
@pytest.mark.parametrize(
    "hostile",
    [
        'evil"; DROP TABLE users; --',
        "has space",
        "quote\"inside",
        "semi;colon",
    ],
)
def test_hostile_trigger_name_is_a_validation_message(qtbot, hostile):
    dialog = _dialog(qtbot)
    _fill(dialog, hostile)

    assert dialog.skeleton() == ""  # no half-formed SQL reaches the editor
    assert dialog.validation_error()  # explained inline...
    assert dialog._error_label.text()  # ...and shown
    assert not _ok(dialog).isEnabled()


def test_hostile_table_is_a_validation_message(qtbot):
    dialog = _dialog(qtbot, table='orders"; DROP TABLE users; --')
    _fill(dialog)

    assert dialog.skeleton() == ""
    assert dialog.validation_error()
    assert not _ok(dialog).isEnabled()


def test_hostile_function_name_is_a_validation_message(qtbot):
    dialog = _dialog(qtbot, functions=['f"()'])
    _fill(dialog)

    assert dialog.skeleton() == ""
    assert dialog.validation_error()
    assert not _ok(dialog).isEnabled()
