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
    add_column_skeleton,
    alter_column_type_skeleton,
    drop_column_default_skeleton,
    drop_column_not_null_skeleton,
    drop_column_skeleton,
    function_skeleton,
    procedure_skeleton,
    rename_column_skeleton,
    set_column_default_skeleton,
    set_column_not_null_skeleton,
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


# --- FQ-025 slice 1: column operations -------------------------------------
#: Every column-op entry point, keyed by name, with a minimal valid kwargs set.
#: Used for the rules that must hold across ALL of them (empty table, empty
#: column, hostile identifiers) so a ninth operation added later cannot quietly
#: skip them.
_COLUMN_OPS = {
    "add_column_skeleton": (add_column_skeleton, {"datatype": "text"}),
    "drop_column_skeleton": (drop_column_skeleton, {}),
    "rename_column_skeleton": (rename_column_skeleton, {"new_name": "renamed"}),
    "alter_column_type_skeleton": (alter_column_type_skeleton, {"datatype": "text"}),
    "set_column_not_null_skeleton": (set_column_not_null_skeleton, {}),
    "drop_column_not_null_skeleton": (drop_column_not_null_skeleton, {}),
    "set_column_default_skeleton": (set_column_default_skeleton, {"expression": "0"}),
    "drop_column_default_skeleton": (drop_column_default_skeleton, {}),
}


def _column_op(name, **overrides):
    func, extra = _COLUMN_OPS[name]
    kwargs = {"table": "public.orders", "column": "notes"}
    kwargs.update(extra)
    kwargs.update(overrides)
    return func(**kwargs)


# --- add column ------------------------------------------------------------
def test_add_column_golden_text():
    assert add_column_skeleton(
        table="public.orders", column="notes", datatype="text"
    ) == ('ALTER TABLE "public"."orders" ADD COLUMN "notes" text;\n')


def test_add_column_not_nullable_emits_not_null():
    assert add_column_skeleton(
        table="orders", column="notes", datatype="text", nullable=False
    ) == ('ALTER TABLE "orders" ADD COLUMN "notes" text NOT NULL;\n')


def test_add_column_nullable_true_emits_no_null_clause():
    # `NULL` is legal but noise; the absence of NOT NULL is the default.
    text = add_column_skeleton(
        table="orders", column="notes", datatype="text", nullable=True
    )
    assert "NULL" not in text


def test_add_column_with_comment_emits_a_second_statement():
    assert add_column_skeleton(
        table="public.orders",
        column="notes",
        datatype="text",
        comment="Free-form notes",
    ) == (
        'ALTER TABLE "public"."orders" ADD COLUMN "notes" text;\n'
        'COMMENT ON COLUMN "public"."orders"."notes" IS \'Free-form notes\';\n'
    )


def test_add_column_comment_single_quotes_are_doubled_not_refused():
    # A comment is a VALUE, not an identifier -- an apostrophe is ordinary
    # English, so it is escaped rather than rejected.
    text = add_column_skeleton(
        table="orders", column="notes", datatype="text", comment="the user's note"
    )
    assert "IS 'the user''s note';\n" in text


def test_add_column_comment_cannot_close_the_statement():
    text = add_column_skeleton(
        table="orders",
        column="notes",
        datatype="text",
        comment="'; DROP TABLE users; --",
    )
    assert "IS '''; DROP TABLE users; --';\n" in text
    # Exactly two statements -- the payload stayed inside the literal.
    assert text.count(";\n") == 2


def test_add_column_blank_comment_emits_no_comment_statement():
    for blank in (None, "", "   "):
        text = add_column_skeleton(
            table="orders", column="notes", datatype="text", comment=blank
        )
        assert "COMMENT ON" not in text


def test_add_column_datatype_may_carry_precision_and_arrays():
    assert "numeric(10,2);\n" in add_column_skeleton(
        table="t", column="c", datatype="numeric(10,2)"
    )
    assert "integer[];\n" in add_column_skeleton(
        table="t", column="c", datatype="integer[]"
    )
    assert "character varying(255);\n" in add_column_skeleton(
        table="t", column="c", datatype="character varying(255)"
    )


def test_add_column_rejects_missing_datatype():
    with pytest.raises(SkeletonError, match="needs a datatype"):
        add_column_skeleton(table="t", column="c", datatype="   ")


@pytest.mark.parametrize(
    "hostile",
    ["text; DROP TABLE users", "text'", 'text"', "text$$"],
)
def test_add_column_refuses_an_unsafe_datatype(hostile):
    with pytest.raises(SkeletonError, match="unsafe or malformed datatype"):
        add_column_skeleton(table="t", column="c", datatype=hostile)


# --- drop / rename column --------------------------------------------------
def test_drop_column_golden_text():
    assert drop_column_skeleton(table="public.orders", column="notes") == (
        'ALTER TABLE "public"."orders" DROP COLUMN "notes";\n'
    )


def test_drop_column_never_emits_cascade():
    # Failing loudly on a dependent view is the safer generated default.
    assert "CASCADE" not in drop_column_skeleton(table="t", column="c")


def test_rename_column_golden_text():
    assert rename_column_skeleton(
        table="public.orders", column="notes", new_name="remarks"
    ) == ('ALTER TABLE "public"."orders" RENAME COLUMN "notes" TO "remarks";\n')


def test_rename_column_to_the_same_name_is_refused():
    with pytest.raises(SkeletonError, match="same as the current one"):
        rename_column_skeleton(table="t", column="notes", new_name="notes")


def test_rename_column_rejects_empty_new_name():
    with pytest.raises(SkeletonError, match="must not be empty"):
        rename_column_skeleton(table="t", column="c", new_name="  ")


def test_rename_column_refuses_a_hostile_new_name():
    with pytest.raises(UnsafeIdentifierError):
        rename_column_skeleton(table="t", column="c", new_name='bad"name')


# --- change type (USING) ---------------------------------------------------
def test_alter_column_type_without_using_golden_text():
    assert alter_column_type_skeleton(
        table="public.orders", column="amount", datatype="numeric(10,2)"
    ) == ('ALTER TABLE "public"."orders" ALTER COLUMN "amount" TYPE numeric(10,2);\n')


def test_alter_column_type_with_using_golden_text():
    assert alter_column_type_skeleton(
        table="public.orders",
        column="code",
        datatype="integer",
        using="trim(code)::integer",
    ) == (
        'ALTER TABLE "public"."orders" ALTER COLUMN "code" TYPE integer '
        "USING trim(code)::integer;\n"
    )


def test_alter_column_type_using_is_omitted_when_none():
    assert "USING" not in alter_column_type_skeleton(
        table="t", column="c", datatype="integer"
    )


def test_alter_column_type_using_is_stripped():
    text = alter_column_type_skeleton(
        table="t", column="c", datatype="integer", using="  c::integer  "
    )
    assert text.endswith("USING c::integer;\n")


def test_alter_column_type_rejects_a_blank_using():
    # An empty USING is a syntax error, so it must not be emitted as one.
    with pytest.raises(SkeletonError, match="USING clause must not be empty"):
        alter_column_type_skeleton(
            table="t", column="c", datatype="integer", using="   "
        )


def test_alter_column_type_using_may_contain_a_string_literal():
    text = alter_column_type_skeleton(
        table="t",
        column="c",
        datatype="integer",
        using="nullif(c, 'n/a')::integer",
    )
    assert "USING nullif(c, 'n/a')::integer;\n" in text


@pytest.mark.parametrize(
    ("hostile", "match"),
    [
        ("c::integer'", "unterminated string literal"),
        ("coalesce(c, 0", "unbalanced parentheses"),
        ("coalesce(c, 0))", "unbalanced parentheses"),
        ("c::integer -- ", "must not contain a SQL comment"),
        ("c::integer /* x", "must not contain a SQL comment"),
    ],
)
def test_alter_column_type_refuses_a_using_that_could_break_the_statement(
    hostile, match
):
    # The expression's MEANING cannot be validated; its ability to escape the
    # statement it sits in can be, and is.
    with pytest.raises(SkeletonError, match=match):
        alter_column_type_skeleton(
            table="t", column="c", datatype="integer", using=hostile
        )


def test_alter_column_type_using_injection_attempt_is_refused():
    # `1); DROP TABLE t; --` -- caught by the paren and comment checks, not by
    # understanding the payload.
    with pytest.raises(SkeletonError):
        alter_column_type_skeleton(
            table="t", column="c", datatype="integer", using="1); DROP TABLE t; --"
        )


def test_alter_column_type_rejects_an_unsafe_datatype():
    with pytest.raises(SkeletonError, match="unsafe or malformed datatype"):
        alter_column_type_skeleton(
            table="t", column="c", datatype="integer; DROP TABLE users"
        )


# --- NOT NULL --------------------------------------------------------------
def test_set_not_null_golden_text():
    assert set_column_not_null_skeleton(table="public.orders", column="notes") == (
        'ALTER TABLE "public"."orders" ALTER COLUMN "notes" SET NOT NULL;\n'
    )


def test_drop_not_null_golden_text():
    assert drop_column_not_null_skeleton(table="public.orders", column="notes") == (
        'ALTER TABLE "public"."orders" ALTER COLUMN "notes" DROP NOT NULL;\n'
    )


# --- DEFAULT ---------------------------------------------------------------
def test_set_default_golden_text():
    assert set_column_default_skeleton(
        table="public.orders", column="created_at", expression="now()"
    ) == (
        'ALTER TABLE "public"."orders" ALTER COLUMN "created_at" '
        "SET DEFAULT now();\n"
    )


def test_set_default_accepts_a_quoted_literal_expression():
    assert "SET DEFAULT 'pending'::text;\n" in set_column_default_skeleton(
        table="t", column="status", expression="'pending'::text"
    )


def test_set_default_doubled_quotes_inside_a_literal_are_not_unbalanced():
    assert "SET DEFAULT 'it''s'::text;\n" in set_column_default_skeleton(
        table="t", column="s", expression="'it''s'::text"
    )


def test_drop_default_golden_text():
    assert drop_column_default_skeleton(table="orders", column="created_at") == (
        'ALTER TABLE "orders" ALTER COLUMN "created_at" DROP DEFAULT;\n'
    )


def test_set_default_rejects_a_blank_expression():
    # "No default" is `drop_column_default_skeleton`, not an empty SET DEFAULT.
    with pytest.raises(SkeletonError, match="default expression must not be empty"):
        set_column_default_skeleton(table="t", column="c", expression="  ")


@pytest.mark.parametrize(
    "hostile",
    ["0; DROP TABLE users; --", "'unterminated", "now(", "0 -- x"],
)
def test_set_default_refuses_an_expression_that_could_break_the_statement(hostile):
    with pytest.raises(SkeletonError):
        set_column_default_skeleton(table="t", column="c", expression=hostile)


def test_set_default_expression_is_required_not_optional():
    with pytest.raises(TypeError):
        set_column_default_skeleton(table="t", column="c")


# --- rules that hold across every column operation -------------------------
@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
def test_every_column_op_quotes_the_table_and_column(op):
    text = _column_op(op)
    assert text.startswith('ALTER TABLE "public"."orders" ')
    assert '"notes"' in text
    assert text.endswith(";\n")


@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
def test_every_column_op_accepts_an_unqualified_table(op):
    assert _column_op(op, table="orders").startswith('ALTER TABLE "orders" ')


@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
def test_every_column_op_rejects_an_empty_table(op):
    with pytest.raises(SkeletonError, match="table must not be empty"):
        _column_op(op, table="   ")


@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
def test_every_column_op_rejects_an_empty_table_name_part(op):
    with pytest.raises(SkeletonError, match="empty name part"):
        _column_op(op, table="public.")


@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
def test_every_column_op_rejects_an_empty_column(op):
    with pytest.raises(SkeletonError, match="column name must not be empty"):
        _column_op(op, column="")


@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
@pytest.mark.parametrize("hostile", ['weird"name', "has space", "drop;table", "x'y"])
def test_every_column_op_refuses_a_hostile_column(op, hostile):
    with pytest.raises(UnsafeIdentifierError):
        _column_op(op, column=hostile)


@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
@pytest.mark.parametrize("hostile", ['t"; DROP TABLE users; --', "public.a b"])
def test_every_column_op_refuses_a_hostile_table(op, hostile):
    with pytest.raises(UnsafeIdentifierError):
        _column_op(op, table=hostile)


@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
def test_every_column_op_preserves_mixed_case_by_quoting(op):
    # Unquoted, Postgres folds `MyTable`/`MyCol` to lower case.
    text = _column_op(op, table="MySchema.MyTable", column="MyCol")
    assert '"MySchema"."MyTable"' in text
    assert '"MyCol"' in text


@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
def test_every_column_op_quotes_a_reserved_word_name(op):
    # `order`/`select` are reserved; the quoting is what makes them usable.
    text = _column_op(op, table="order", column="select")
    assert 'ALTER TABLE "order" ' in text
    assert '"select"' in text


@pytest.mark.parametrize("op", sorted(_COLUMN_OPS))
def test_every_column_op_is_deterministic(op):
    assert _column_op(op) == _column_op(op)


def test_skeletons_are_deterministic():
    assert function_skeleton(name="f", return_type="integer") == function_skeleton(
        name="f", return_type="integer"
    )
    assert _trigger() == _trigger()
