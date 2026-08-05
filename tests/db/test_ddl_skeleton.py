# tests/db/test_ddl_skeleton.py
"""Pure tests for FQ-002's `CREATE` skeleton rendering (no Qt, no live DB).

Golden-string assertions throughout: `ddl_skeleton` is deterministic by
contract, so the exact emitted text is the thing worth pinning -- this is
output a user runs against a real database.
"""
import pytest

from pgtp_editor.db.ddl_skeleton import (
    TRIGGER_EVENTS,
    TRIGGER_LEVELS,
    TRIGGER_TIMINGS,
    SkeletonError,
    function_skeleton,
    procedure_skeleton,
    trigger_skeleton,
)
from pgtp_editor.db.sandbox import UnsafeIdentifierError


def _trigger(**overrides):
    kwargs = {
        "name": "audit_orders",
        "table": "public.orders",
        "timing": "BEFORE",
        "events": ["INSERT"],
        "level": "FOR EACH ROW",
        "function_name": "audit_fn",
    }
    kwargs.update(overrides)
    return trigger_skeleton(**kwargs)


# --- trigger ---------------------------------------------------------------
def test_trigger_skeleton_golden_text():
    assert _trigger() == (
        'CREATE TRIGGER "audit_orders"\n'
        'BEFORE INSERT ON "public"."orders"\n'
        "FOR EACH ROW\n"
        'EXECUTE FUNCTION "audit_fn"();\n'
    )


def test_trigger_events_are_emitted_in_canonical_order_not_call_order():
    # Passed backwards; must still read INSERT OR UPDATE OR DELETE.
    text = _trigger(events=["DELETE", "UPDATE", "INSERT"])
    assert "BEFORE INSERT OR UPDATE OR DELETE ON" in text


def test_trigger_events_from_an_unordered_set_are_still_stable():
    # A dialog backed by checkboxes hands over a set; two runs must agree.
    first = _trigger(events={"UPDATE", "INSERT"})
    second = _trigger(events={"INSERT", "UPDATE"})
    assert first == second
    assert "BEFORE INSERT OR UPDATE ON" in first


def test_trigger_duplicate_events_are_collapsed():
    # `INSERT OR INSERT` is a syntax error.
    assert "BEFORE INSERT ON" in _trigger(events=["INSERT", "INSERT"])


def test_trigger_unqualified_table_is_quoted_as_one_part():
    assert 'ON "orders"\n' in _trigger(table="orders")


@pytest.mark.parametrize("timing", TRIGGER_TIMINGS)
def test_every_declared_timing_is_accepted(timing):
    assert _trigger(timing=timing).startswith("CREATE TRIGGER")


@pytest.mark.parametrize("level", TRIGGER_LEVELS)
def test_every_declared_level_is_accepted(level):
    assert f"{level}\n" in _trigger(level=level)


@pytest.mark.parametrize("event", TRIGGER_EVENTS)
def test_every_declared_event_is_accepted(event):
    assert f"BEFORE {event} ON" in _trigger(events=[event])


def test_trigger_rejects_empty_event_list():
    with pytest.raises(SkeletonError, match="at least one event"):
        _trigger(events=[])


def test_trigger_rejects_unknown_event():
    with pytest.raises(SkeletonError, match="TRUNCATE"):
        _trigger(events=["TRUNCATE"])


def test_trigger_rejects_unknown_timing():
    with pytest.raises(SkeletonError, match="timing must be one of"):
        _trigger(timing="DURING")


def test_trigger_rejects_transaction_level():
    # The original FQ-002 request asked for "for each transaction"; Postgres
    # has no such level, so it must be refused rather than emitted.
    with pytest.raises(SkeletonError, match="level must be one of"):
        _trigger(level="FOR EACH TRANSACTION")


def test_trigger_rejects_empty_name():
    with pytest.raises(SkeletonError, match="must not be empty"):
        _trigger(name="")


def test_trigger_rejects_empty_table_name_part():
    with pytest.raises(SkeletonError, match="empty name part"):
        _trigger(table="public.")


# --- function --------------------------------------------------------------
def test_function_skeleton_golden_text():
    assert function_skeleton(name="recalc", return_type="integer") == (
        'CREATE OR REPLACE FUNCTION "recalc"()\n'
        "RETURNS integer\n"
        "LANGUAGE plpgsql\n"
        "AS $$\n"
        "BEGIN\n"
        "    -- TODO: implement\n"
        "    RETURN NULL;\n"
        "END;\n"
        "$$;\n"
    )


def test_function_returning_void_omits_the_return_statement():
    # `RETURN NULL;` in a void function is a runtime error, so the stub must
    # not emit one -- a skeleton that fails on first run is worse than a no-op.
    text = function_skeleton(name="do_thing", return_type="void")
    # Match the statement, not the substring -- `RETURNS void` contains "RETURN".
    assert "RETURN NULL;" not in text
    assert "BEGIN\n    -- TODO: implement\nEND;" in text


def test_function_void_is_detected_case_insensitively():
    assert "RETURN NULL" not in function_skeleton(name="f", return_type="VOID")


def test_function_return_type_may_carry_precision_and_arrays():
    assert "RETURNS numeric(10,2)\n" in function_skeleton(
        name="f", return_type="numeric(10,2)"
    )
    assert "RETURNS integer[]\n" in function_skeleton(name="f", return_type="integer[]")


def test_function_trigger_return_type_is_ordinary():
    # The common case for FQ-002: a trigger function to attach a trigger to.
    assert "RETURNS trigger\n" in function_skeleton(name="f", return_type="trigger")


def test_function_name_may_be_schema_qualified():
    assert function_skeleton(name="pr.recalc", return_type="integer").startswith(
        'CREATE OR REPLACE FUNCTION "pr"."recalc"()'
    )


def test_function_rejects_missing_return_type():
    with pytest.raises(SkeletonError, match="needs a return type"):
        function_skeleton(name="f", return_type="   ")


@pytest.mark.parametrize(
    "hostile",
    [
        "integer; DROP TABLE users",
        "integer$$; DROP TABLE users; --",
        'integer" ',
        "integer'",
    ],
)
def test_function_refuses_a_return_type_that_could_escape_the_statement(hostile):
    # The return type is the one free-text field, so it is the injection seam.
    with pytest.raises(SkeletonError, match="unsafe or malformed return type"):
        function_skeleton(name="f", return_type=hostile)


# --- procedure -------------------------------------------------------------
def test_procedure_skeleton_golden_text():
    assert procedure_skeleton(name="reconcile") == (
        'CREATE OR REPLACE PROCEDURE "reconcile"()\n'
        "LANGUAGE plpgsql\n"
        "AS $$\n"
        "BEGIN\n"
        "    -- TODO: implement\n"
        "END;\n"
        "$$;\n"
    )


def test_procedure_never_emits_a_returns_clause():
    # `CREATE PROCEDURE ... RETURNS ...` is a syntax error in Postgres, so this
    # is a correctness requirement, not a formatting preference.
    assert "RETURNS" not in procedure_skeleton(name="reconcile")


def test_procedure_takes_no_return_type_at_all():
    # Enforced by the signature: a procedure that returned something would not
    # be a procedure, so there is no argument to accept-and-ignore.
    with pytest.raises(TypeError):
        procedure_skeleton(name="reconcile", return_type="integer")


# --- identifier safety (shared) --------------------------------------------
def test_mixed_case_names_are_preserved_by_quoting():
    # Unquoted, Postgres would fold `MyFunc` to `myfunc`.
    assert function_skeleton(name="MyFunc", return_type="integer").startswith(
        'CREATE OR REPLACE FUNCTION "MyFunc"()'
    )


@pytest.mark.parametrize("hostile", ['weird"name', "has space", "drop;table", "x'y"])
def test_hostile_identifiers_are_refused_not_escaped(hostile):
    # The codebase's "validated, not sanitized" posture (sandbox.quote_ident):
    # arbitrary content never reaches the output, quoted or otherwise.
    with pytest.raises(UnsafeIdentifierError):
        function_skeleton(name=hostile, return_type="integer")


def test_hostile_trigger_function_name_is_refused():
    with pytest.raises(UnsafeIdentifierError):
        _trigger(function_name="fn(); DROP TABLE users; --")


def test_skeletons_are_deterministic():
    assert function_skeleton(name="f", return_type="integer") == function_skeleton(
        name="f", return_type="integer"
    )
    assert _trigger() == _trigger()
