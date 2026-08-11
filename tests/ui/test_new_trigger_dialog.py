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
    TRIGGER_TIMINGS_BY_KIND,
    SkeletonError,
    trigger_skeleton,
)
from pgtp_editor.db.introspect import TableInfo
from pgtp_editor.ui.new_trigger_dialog import NO_TRIGGERS_MESSAGE, NewTriggerDialog

#: `(kind, timing)` for every legal combination — the matview row contributes
#: none, which is the point of it.
KIND_TIMINGS = [
    (kind, timing)
    for kind, timings in sorted(TRIGGER_TIMINGS_BY_KIND.items())
    for timing in timings
]

FUNCTIONS = ["public.audit_stamp", "public.touch_updated_at"]


def _dialog(qtbot, table="public.orders", functions=None, kind="table"):
    dialog = NewTriggerDialog(
        table, FUNCTIONS if functions is None else functions, kind=kind
    )
    qtbot.addWidget(dialog)
    return dialog


def _offered_timings(dialog):
    combo = dialog._timing_combo
    return [combo.itemText(i) for i in range(combo.count())]


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
@pytest.mark.parametrize("kind", sorted(TRIGGER_TIMINGS_BY_KIND))
def test_offered_timings_are_exactly_the_emitters_for_that_kind(qtbot, kind):
    """**Supersedes** the original assertion that the combo equalled
    `TRIGGER_TIMINGS` verbatim (DEC-260811025733). That union is no longer a
    legal offer for any single target: a table takes `BEFORE`/`AFTER`, a view
    takes `INSTEAD OF`, a matview takes nothing. The offer is still not re-typed
    here — it is read from `TRIGGER_TIMINGS_BY_KIND`, so widget and emitter still
    cannot drift — but it is now read PER KIND.

    Asserted through the dialog, and the constant only says which kinds exist."""
    dialog = _dialog(qtbot, kind=kind)
    assert _offered_timings(dialog) == list(TRIGGER_TIMINGS_BY_KIND[kind])


def test_a_table_offers_before_and_after_only(qtbot):
    """Spelled out rather than derived, so a wrong edit to the constant cannot
    quietly redefine what "correct" means here."""
    assert _offered_timings(_dialog(qtbot, kind="table")) == ["BEFORE", "AFTER"]


def test_a_view_offers_instead_of_only(qtbot):
    assert _offered_timings(_dialog(qtbot, kind="view")) == ["INSTEAD OF"]


def test_a_partitioned_table_still_gets_the_ordinary_table_timings(qtbot):
    """`introspect` maps `relkind` `'p'` to the kind string `"table"` alongside
    `'r'`, so a partitioned table arrives here indistinguishable from a plain
    one — and must keep `BEFORE`/`AFTER`. Pinned because the mapping is the only
    thing standing between a partitioned table and a view-shaped offer."""
    info = TableInfo(name="pr.events", kind="table", columns=[])
    dialog = _dialog(qtbot, table=info.name, kind=info.kind)

    assert _offered_timings(dialog) == ["BEFORE", "AFTER"]
    _fill(dialog, "events_audit")
    assert dialog.is_valid()


def test_a_view_target_renders_an_instead_of_trigger(qtbot):
    dialog = _dialog(qtbot, table="public.orders_v", kind="view")
    _fill(dialog, "orders_v_ins", ("INSERT",))
    dialog._function_combo.setCurrentText("public.audit_stamp")

    assert dialog.timing() == "INSTEAD OF"
    assert dialog.is_valid()
    assert 'INSTEAD OF INSERT ON "public"."orders_v"' in dialog.skeleton()


def test_a_matview_target_offers_nothing_and_says_why(qtbot):
    """The tree does not offer `Add Trigger…` on a matview at all; this is the
    safety net behind that gate, and it refuses with a sentence rather than
    raising."""
    dialog = _dialog(qtbot, table="public.orders_mv", kind="matview")
    _fill(dialog, "orders_mv_ins", ("INSERT",))

    assert _offered_timings(dialog) == []
    assert not dialog._timing_combo.isEnabled()
    assert dialog.skeleton() == ""
    assert dialog.validation_error() == NO_TRIGGERS_MESSAGE
    assert not _ok(dialog).isEnabled()


def test_an_unknown_kind_is_refused_rather_than_treated_as_a_table(qtbot):
    with pytest.raises(SkeletonError, match="unknown relation kind"):
        NewTriggerDialog("public.orders", FUNCTIONS, kind="sequence")


def test_the_target_row_names_what_was_clicked(qtbot):
    def label(kind):
        dialog = _dialog(qtbot, kind=kind)
        return dialog.layout().itemAt(0).layout().itemAt(0).widget().text()

    assert label("table") == "Table:"
    assert label("view") == "View:"


def test_the_kind_is_readable_back(qtbot):
    dialog = _dialog(qtbot, kind="view")
    assert dialog.kind() == "view"
    assert dialog.offered_timings() == ["INSTEAD OF"]


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


@pytest.mark.parametrize("kind,timing", KIND_TIMINGS)
@pytest.mark.parametrize("level", TRIGGER_LEVELS)
def test_every_offered_timing_and_level_renders(qtbot, kind, timing, level):
    # Each timing is exercised on the kind that may carry it — the pair, not the
    # cross product, since half of that product is now illegal by design.
    dialog = _dialog(qtbot, kind=kind)
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
