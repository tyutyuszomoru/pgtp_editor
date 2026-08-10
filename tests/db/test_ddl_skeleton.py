# tests/db/test_ddl_skeleton.py
"""Pure tests for FQ-002's `CREATE` skeleton rendering (no Qt, no live DB).

Golden-string assertions throughout: `ddl_skeleton` is deterministic by
contract, so the exact emitted text is the thing worth pinning -- this is
output a user runs against a real database.
"""
import pytest

from pgtp_editor.db.ddl_skeleton import (
    COLUMN_CONSTRAINT_TYPES,
    CONSTRAINT_TYPES,
    EXCLUDE_METHODS,
    EXPRESSION_CONSTRAINT_TYPES,
    FK_ACTIONS,
    INDEX_METHODS,
    TRIGGER_EVENTS,
    TRIGGER_LEVELS,
    TRIGGER_TIMINGS,
    ColumnSpec,
    SkeletonError,
    add_column_skeleton,
    add_constraint_skeleton,
    add_foreign_key_skeleton,
    alter_column_type_skeleton,
    create_index_skeleton,
    create_table_skeleton,
    drop_column_default_skeleton,
    drop_column_not_null_skeleton,
    drop_column_skeleton,
    drop_constraint_skeleton,
    drop_index_skeleton,
    drop_table_skeleton,
    function_skeleton,
    procedure_skeleton,
    rename_column_skeleton,
    rename_constraint_skeleton,
    set_column_comment_skeleton,
    set_column_default_skeleton,
    set_column_not_null_skeleton,
    set_table_comment_skeleton,
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


# --- FQ-025 slice 2: constraints & foreign keys ----------------------------
#: Every constraint-op entry point with a minimal valid kwargs set — the same
#: registry idea as `_COLUMN_OPS`, so the cross-cutting rules (table quoting,
#: empty/hostile table, empty/hostile constraint name, determinism) are
#: parametrized over ALL of them and a fifth operation cannot skip them.
_CONSTRAINT_OPS = {
    "add_constraint_skeleton": (
        add_constraint_skeleton,
        {"constraint_type": "UNIQUE", "columns": ["code"]},
    ),
    "add_foreign_key_skeleton": (
        add_foreign_key_skeleton,
        {
            "columns": ["customer_id"],
            "ref_table": "public.customer",
            "ref_columns": ["id"],
        },
    ),
    "drop_constraint_skeleton": (drop_constraint_skeleton, {}),
    "rename_constraint_skeleton": (
        rename_constraint_skeleton,
        {"new_name": "renamed_ck"},
    ),
}


def _constraint_op(op, **overrides):
    # The positional is `op`, not `name`: `name` is a real kwarg of every
    # constraint emitter (the constraint's own name), which the tests override.
    func, extra = _CONSTRAINT_OPS[op]
    kwargs = {"table": "public.orders", "name": "orders_ck"}
    kwargs.update(extra)
    kwargs.update(overrides)
    return func(**kwargs)


# --- add constraint --------------------------------------------------------
def test_add_primary_key_golden_text():
    assert add_constraint_skeleton(
        table="public.orders",
        name="orders_pkey",
        constraint_type="PRIMARY KEY",
        columns=["id"],
    ) == ('ALTER TABLE "public"."orders" ADD CONSTRAINT "orders_pkey" '
          'PRIMARY KEY ("id");\n')


def test_add_unique_golden_text():
    assert add_constraint_skeleton(
        table="orders", name="orders_code_key", constraint_type="UNIQUE",
        columns=["code"],
    ) == ('ALTER TABLE "orders" ADD CONSTRAINT "orders_code_key" '
          'UNIQUE ("code");\n')


def test_add_check_golden_text():
    assert add_constraint_skeleton(
        table="public.orders",
        name="orders_qty_positive",
        constraint_type="CHECK",
        expression="qty > 0",
    ) == ('ALTER TABLE "public"."orders" ADD CONSTRAINT "orders_qty_positive" '
          "CHECK (qty > 0);\n")


def test_add_exclude_golden_text():
    assert add_constraint_skeleton(
        table="booking",
        name="no_overlap",
        constraint_type="EXCLUDE",
        expression="room WITH =, during WITH &&",
    ) == ('ALTER TABLE "booking" ADD CONSTRAINT "no_overlap" '
          "EXCLUDE USING gist (room WITH =, during WITH &&);\n")


def test_add_exclude_honours_the_index_method():
    assert "EXCLUDE USING btree (a WITH =)" in add_constraint_skeleton(
        table="t", name="c", constraint_type="EXCLUDE",
        expression="a WITH =", method="btree",
    )


def test_add_multi_column_key_preserves_caller_order():
    # A key's column ORDER is semantic (unlike trigger events, which are
    # canonicalised), so it must survive exactly as passed.
    forwards = add_constraint_skeleton(
        table="t", name="c", constraint_type="PRIMARY KEY",
        columns=["tenant", "id"],
    )
    backwards = add_constraint_skeleton(
        table="t", name="c", constraint_type="PRIMARY KEY",
        columns=["id", "tenant"],
    )
    assert 'PRIMARY KEY ("tenant", "id")' in forwards
    assert 'PRIMARY KEY ("id", "tenant")' in backwards
    assert forwards != backwards


@pytest.mark.parametrize("constraint_type", COLUMN_CONSTRAINT_TYPES)
def test_column_shaped_types_reject_an_empty_column_list(constraint_type):
    with pytest.raises(SkeletonError, match="needs at least one column"):
        add_constraint_skeleton(
            table="t", name="c", constraint_type=constraint_type, columns=[]
        )


@pytest.mark.parametrize("constraint_type", COLUMN_CONSTRAINT_TYPES)
def test_column_shaped_types_reject_an_expression(constraint_type):
    # Silently ignoring it would ship a key that constrains the wrong thing.
    with pytest.raises(SkeletonError, match="column list, not an expression"):
        add_constraint_skeleton(
            table="t", name="c", constraint_type=constraint_type,
            columns=["a"], expression="a > 0",
        )


@pytest.mark.parametrize("constraint_type", EXPRESSION_CONSTRAINT_TYPES)
def test_expression_shaped_types_reject_a_column_list(constraint_type):
    with pytest.raises(SkeletonError, match="expression, not a column list"):
        add_constraint_skeleton(
            table="t", name="c", constraint_type=constraint_type,
            columns=["a"], expression="a > 0",
        )


@pytest.mark.parametrize("constraint_type", EXPRESSION_CONSTRAINT_TYPES)
def test_expression_shaped_types_require_an_expression(constraint_type):
    with pytest.raises(SkeletonError, match="needs an expression"):
        add_constraint_skeleton(
            table="t", name="c", constraint_type=constraint_type
        )


def test_add_constraint_rejects_a_duplicate_column():
    # `PRIMARY KEY (a, a)` is a Postgres error; collapsing it silently would
    # emit a key the user did not ask for.
    with pytest.raises(SkeletonError, match="same column twice"):
        add_constraint_skeleton(
            table="t", name="c", constraint_type="PRIMARY KEY", columns=["a", "a"]
        )


def test_add_constraint_rejects_an_unknown_type():
    with pytest.raises(SkeletonError, match="constraint type must be one of"):
        add_constraint_skeleton(
            table="t", name="c", constraint_type="FOREIGN KEY", columns=["a"]
        )


def test_foreign_key_is_not_an_add_constraint_type():
    # It needs a referenced table and column list, so it is its own emitter.
    assert "FOREIGN KEY" not in CONSTRAINT_TYPES


def test_add_exclude_rejects_an_unknown_method():
    with pytest.raises(SkeletonError, match="index method must be one of"):
        add_constraint_skeleton(
            table="t", name="c", constraint_type="EXCLUDE",
            expression="a WITH =", method="magic",
        )


@pytest.mark.parametrize("method", EXCLUDE_METHODS)
def test_every_declared_exclude_method_is_accepted(method):
    assert f"EXCLUDE USING {method} (" in add_constraint_skeleton(
        table="t", name="c", constraint_type="EXCLUDE",
        expression="a WITH =", method=method,
    )


@pytest.mark.parametrize(
    ("hostile", "match"),
    [
        ("qty > 0'", "unterminated string literal"),
        ("(qty > 0", "unbalanced parentheses"),
        ("qty > 0)", "unbalanced parentheses"),
        ("qty > 0 -- ", "must not contain a SQL comment"),
        ("qty > 0 /* x", "must not contain a SQL comment"),
        ("   ", "must not be empty"),
    ],
)
def test_check_expression_that_could_break_the_statement_is_refused(hostile, match):
    # The CHECK body reuses slice 1's `_expression` guard verbatim, so it
    # inherits exactly the same guarantees -- and no more.
    with pytest.raises(SkeletonError, match=match):
        add_constraint_skeleton(
            table="t", name="c", constraint_type="CHECK", expression=hostile
        )


def test_check_expression_may_contain_a_string_literal():
    assert "CHECK (status <> 'void');\n" in add_constraint_skeleton(
        table="t", name="c", constraint_type="CHECK", expression="status <> 'void'"
    )


def test_check_expression_injection_attempt_is_refused():
    with pytest.raises(SkeletonError):
        add_constraint_skeleton(
            table="t", name="c", constraint_type="CHECK",
            expression="1); DROP TABLE t; --",
        )


# --- add foreign key -------------------------------------------------------
def test_add_foreign_key_golden_text():
    assert add_foreign_key_skeleton(
        table="public.orders",
        name="orders_customer_fk",
        columns=["customer_id"],
        ref_table="public.customer",
        ref_columns=["id"],
    ) == (
        'ALTER TABLE "public"."orders" ADD CONSTRAINT "orders_customer_fk" '
        'FOREIGN KEY ("customer_id") REFERENCES "public"."customer" ("id");\n'
    )


def test_add_foreign_key_multi_column_golden_text():
    assert add_foreign_key_skeleton(
        table="orders",
        name="fk",
        columns=["tenant", "customer_id"],
        ref_table="customer",
        ref_columns=["tenant", "id"],
    ) == (
        'ALTER TABLE "orders" ADD CONSTRAINT "fk" '
        'FOREIGN KEY ("tenant", "customer_id") '
        'REFERENCES "customer" ("tenant", "id");\n'
    )


def test_add_foreign_key_referenced_table_may_be_unqualified():
    assert 'REFERENCES "customer" ("id")' in add_foreign_key_skeleton(
        table="orders", name="fk", columns=["c"], ref_table="customer",
        ref_columns=["id"],
    )


def test_add_foreign_key_referenced_columns_are_always_rendered():
    # Postgres would let the list be omitted (meaning "the referenced table's
    # primary key"); a generated statement must say what it binds to.
    text = add_foreign_key_skeleton(
        table="orders", name="fk", columns=["c"], ref_table="customer",
        ref_columns=["id"],
    )
    assert text.count("(") == 2


def test_add_foreign_key_with_referential_actions_golden_text():
    assert add_foreign_key_skeleton(
        table="orders",
        name="fk",
        columns=["c"],
        ref_table="customer",
        ref_columns=["id"],
        on_delete="CASCADE",
        on_update="RESTRICT",
    ) == (
        'ALTER TABLE "orders" ADD CONSTRAINT "fk" FOREIGN KEY ("c") '
        'REFERENCES "customer" ("id") ON DELETE CASCADE ON UPDATE RESTRICT;\n'
    )


def test_add_foreign_key_omits_the_action_clauses_by_default():
    text = add_foreign_key_skeleton(
        table="orders", name="fk", columns=["c"], ref_table="customer",
        ref_columns=["id"],
    )
    assert "ON DELETE" not in text
    assert "ON UPDATE" not in text


@pytest.mark.parametrize("action", FK_ACTIONS)
def test_every_declared_referential_action_is_accepted(action):
    assert f"ON DELETE {action};\n" in add_foreign_key_skeleton(
        table="t", name="fk", columns=["c"], ref_table="r", ref_columns=["id"],
        on_delete=action,
    )


def test_add_foreign_key_rejects_an_unknown_referential_action():
    with pytest.raises(SkeletonError, match="ON DELETE must be one of"):
        add_foreign_key_skeleton(
            table="t", name="fk", columns=["c"], ref_table="r",
            ref_columns=["id"], on_delete="EXPLODE",
        )


def test_add_foreign_key_rejects_mismatched_column_counts():
    with pytest.raises(SkeletonError, match="exactly as many columns"):
        add_foreign_key_skeleton(
            table="t", name="fk", columns=["a", "b"], ref_table="r",
            ref_columns=["id"],
        )


def test_add_foreign_key_rejects_an_empty_local_column_list():
    with pytest.raises(SkeletonError, match="needs at least one column"):
        add_foreign_key_skeleton(
            table="t", name="fk", columns=[], ref_table="r", ref_columns=["id"]
        )


def test_add_foreign_key_rejects_an_empty_referenced_column_list():
    with pytest.raises(SkeletonError, match="needs at least one column"):
        add_foreign_key_skeleton(
            table="t", name="fk", columns=["a"], ref_table="r", ref_columns=[]
        )


def test_add_foreign_key_rejects_an_empty_referenced_table():
    with pytest.raises(SkeletonError, match="referenced table must not be empty"):
        add_foreign_key_skeleton(
            table="t", name="fk", columns=["a"], ref_table="  ", ref_columns=["id"]
        )


@pytest.mark.parametrize("hostile", ['r"; DROP TABLE users; --', "public.a b"])
def test_add_foreign_key_refuses_a_hostile_referenced_table(hostile):
    with pytest.raises(UnsafeIdentifierError):
        add_foreign_key_skeleton(
            table="t", name="fk", columns=["a"], ref_table=hostile,
            ref_columns=["id"],
        )


@pytest.mark.parametrize("hostile", ['id"', "id; DROP TABLE users", "has space"])
def test_add_foreign_key_refuses_a_hostile_referenced_column(hostile):
    with pytest.raises(UnsafeIdentifierError):
        add_foreign_key_skeleton(
            table="t", name="fk", columns=["a"], ref_table="r",
            ref_columns=[hostile],
        )


# --- drop / rename constraint ----------------------------------------------
def test_drop_constraint_golden_text():
    assert drop_constraint_skeleton(table="public.orders", name="orders_pkey") == (
        'ALTER TABLE "public"."orders" DROP CONSTRAINT "orders_pkey";\n'
    )


def test_drop_constraint_is_type_agnostic():
    # The unified drop's entire justification: in Postgres a FK IS a
    # constraint, so the statement cannot depend on the type -- the emitter is
    # not even told what the type is.
    for name in ("orders_pkey", "orders_customer_fk", "qty_positive", "no_overlap"):
        assert drop_constraint_skeleton(table="t", name=name) == (
            f'ALTER TABLE "t" DROP CONSTRAINT "{name}";\n'
        )


def test_there_is_no_separate_drop_foreign_key_emitter():
    # A second emitter would be the same statement under a name implying
    # otherwise. Guarding the absence keeps a later slice from adding one.
    import pgtp_editor.db.ddl_skeleton as skeleton

    assert not hasattr(skeleton, "drop_foreign_key_skeleton")


def test_drop_constraint_never_emits_cascade_or_if_exists():
    text = drop_constraint_skeleton(table="t", name="c")
    assert "CASCADE" not in text
    assert "IF EXISTS" not in text


def test_rename_constraint_golden_text():
    assert rename_constraint_skeleton(
        table="public.orders", name="orders_ck", new_name="orders_qty_ck"
    ) == (
        'ALTER TABLE "public"."orders" RENAME CONSTRAINT "orders_ck" '
        'TO "orders_qty_ck";\n'
    )


def test_rename_constraint_to_the_same_name_is_refused():
    with pytest.raises(SkeletonError, match="same as the current one"):
        rename_constraint_skeleton(table="t", name="ck", new_name="ck")


def test_rename_constraint_rejects_an_empty_new_name():
    with pytest.raises(SkeletonError, match="must not be empty"):
        rename_constraint_skeleton(table="t", name="ck", new_name="  ")


def test_rename_constraint_refuses_a_hostile_new_name():
    with pytest.raises(UnsafeIdentifierError):
        rename_constraint_skeleton(table="t", name="ck", new_name='bad"name')


# --- rules that hold across every constraint operation ---------------------
@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
def test_every_constraint_op_quotes_the_table_and_name(op):
    text = _constraint_op(op)
    assert text.startswith('ALTER TABLE "public"."orders" ')
    assert '"orders_ck"' in text
    assert text.endswith(";\n")


@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
def test_every_constraint_op_accepts_an_unqualified_table(op):
    assert _constraint_op(op, table="orders").startswith('ALTER TABLE "orders" ')


@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
def test_every_constraint_op_rejects_an_empty_table(op):
    with pytest.raises(SkeletonError, match="table must not be empty"):
        _constraint_op(op, table="   ")


@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
def test_every_constraint_op_rejects_an_empty_table_name_part(op):
    with pytest.raises(SkeletonError, match="empty name part"):
        _constraint_op(op, table="public.")


@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
def test_every_constraint_op_rejects_an_empty_constraint_name(op):
    with pytest.raises(SkeletonError, match="constraint name must not be empty"):
        _constraint_op(op, name="  ")


@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
@pytest.mark.parametrize("hostile", ['weird"name', "has space", "drop;table", "x'y"])
def test_every_constraint_op_refuses_a_hostile_constraint_name(op, hostile):
    with pytest.raises(UnsafeIdentifierError):
        _constraint_op(op, name=hostile)


@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
@pytest.mark.parametrize("hostile", ['t"; DROP TABLE users; --', "public.a b"])
def test_every_constraint_op_refuses_a_hostile_table(op, hostile):
    with pytest.raises(UnsafeIdentifierError):
        _constraint_op(op, table=hostile)


@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
def test_every_constraint_op_preserves_mixed_case_by_quoting(op):
    text = _constraint_op(op, table="MySchema.MyTable", name="MyConstraint")
    assert '"MySchema"."MyTable"' in text
    assert '"MyConstraint"' in text


@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
def test_every_constraint_op_quotes_a_reserved_word_table(op):
    assert 'ALTER TABLE "order" ' in _constraint_op(op, table="order")


@pytest.mark.parametrize("op", sorted(_CONSTRAINT_OPS))
def test_every_constraint_op_is_deterministic(op):
    assert _constraint_op(op) == _constraint_op(op)


@pytest.mark.parametrize("op", ["add_constraint_skeleton", "add_foreign_key_skeleton"])
@pytest.mark.parametrize("hostile", ['weird"name', "has space", "drop;table"])
def test_every_add_op_refuses_a_hostile_column(op, hostile):
    with pytest.raises(UnsafeIdentifierError):
        _constraint_op(op, columns=[hostile])


# --- FQ-025 slice 3: indexes, comments, whole-table ------------------------
#: Every slice-3 entry point, with the kwarg that carries a **qualified name**
#: named explicitly. The same registry idea as `_COLUMN_OPS`/`_CONSTRAINT_OPS`,
#: with one twist the slice forces: `drop_index_skeleton` takes no table at all
#: (an index's identity is its own `schema.name`), so the registry records
#: *which* argument is the qualified one instead of assuming it is `table`.
#: A seventh operation therefore still cannot skip the shared quoting,
#: rejection and determinism checks.
_TABLE_OPS = {
    "create_index_skeleton": (
        create_index_skeleton,
        "table",
        {"name": "idx_orders_code", "table": "public.orders", "columns": ["code"]},
    ),
    "drop_index_skeleton": (
        drop_index_skeleton,
        "index",
        {"index": "public.orders"},
    ),
    "set_table_comment_skeleton": (
        set_table_comment_skeleton,
        "table",
        {"table": "public.orders", "comment": "the orders"},
    ),
    "set_column_comment_skeleton": (
        set_column_comment_skeleton,
        "table",
        {"table": "public.orders", "column": "notes", "comment": "free text"},
    ),
    "create_table_skeleton": (
        create_table_skeleton,
        "table",
        {"table": "public.orders", "columns": [ColumnSpec("id", "bigint")]},
    ),
    "drop_table_skeleton": (drop_table_skeleton, "table", {"table": "public.orders"}),
}


def _table_op(op, qualified=None, **overrides):
    func, key, extra = _TABLE_OPS[op]
    kwargs = dict(extra)
    if qualified is not None:
        kwargs[key] = qualified
    kwargs.update(overrides)
    return func(**kwargs)


# --- create index ----------------------------------------------------------
def test_create_index_golden_text():
    assert create_index_skeleton(
        name="idx_orders_code", table="public.orders", columns=["code"]
    ) == (
        'CREATE INDEX "idx_orders_code" ON "public"."orders" '
        'USING btree ("code");\n'
    )


def test_create_index_unique_golden_text():
    assert create_index_skeleton(
        name="idx_orders_code", table="orders", columns=["code"], unique=True
    ) == ('CREATE UNIQUE INDEX "idx_orders_code" ON "orders" '
          'USING btree ("code");\n')


def test_create_index_is_not_an_alter_table():
    # `CREATE INDEX` is its own statement -- it does not go through the
    # `_alter_column` shape every slice-1 operation shares.
    assert not create_index_skeleton(
        name="i", table="t", columns=["c"]
    ).startswith("ALTER TABLE")


def test_create_index_always_states_its_method_even_for_the_default():
    # Generated text should say which method it means rather than relying on
    # the reader knowing Postgres's default.
    assert "USING btree" in create_index_skeleton(name="i", table="t", columns=["c"])


@pytest.mark.parametrize("method", INDEX_METHODS)
def test_every_declared_index_method_is_accepted(method):
    assert f"USING {method} (" in create_index_skeleton(
        name="i", table="t", columns=["c"], method=method
    )


def test_create_index_rejects_an_unknown_method():
    with pytest.raises(SkeletonError, match="index method must be one of"):
        create_index_skeleton(name="i", table="t", columns=["c"], method="magic")


def test_index_methods_are_a_superset_of_the_exclude_methods():
    # An EXCLUDE constraint can only use methods supporting its operators; a
    # plain index has no such restriction, so the wider list is the right one
    # here and the narrower one must stay contained in it.
    assert set(EXCLUDE_METHODS) <= set(INDEX_METHODS)


def test_create_index_multi_column_preserves_caller_order():
    forwards = create_index_skeleton(name="i", table="t", columns=["a", "b"])
    backwards = create_index_skeleton(name="i", table="t", columns=["b", "a"])
    assert '("a", "b")' in forwards
    assert '("b", "a")' in backwards


def test_create_index_rejects_an_empty_column_list():
    with pytest.raises(SkeletonError, match="needs at least one column"):
        create_index_skeleton(name="i", table="t", columns=[])


def test_create_index_rejects_a_duplicate_column():
    with pytest.raises(SkeletonError, match="same column twice"):
        create_index_skeleton(name="i", table="t", columns=["a", "a"])


def test_create_index_name_may_not_be_schema_qualified():
    # `CREATE INDEX` creates the index in its table's schema; a dotted index
    # name is a syntax error, so it is refused rather than emitted.
    with pytest.raises(UnsafeIdentifierError):
        create_index_skeleton(name="public.idx", table="public.orders", columns=["c"])


def test_create_index_refuses_an_expression_as_a_column():
    # `("lower(email)")` would be an index on a column that does not exist.
    with pytest.raises(UnsafeIdentifierError):
        create_index_skeleton(name="i", table="t", columns=["lower(email)"])


def test_create_index_never_emits_concurrently():
    # CONCURRENTLY cannot run inside a transaction block, which is how the
    # Apply paths execute generated statements.
    assert "CONCURRENTLY" not in create_index_skeleton(
        name="i", table="t", columns=["c"], unique=True
    )


# --- drop index ------------------------------------------------------------
def test_drop_index_golden_text():
    assert drop_index_skeleton(index="public.idx_orders_code") == (
        'DROP INDEX "public"."idx_orders_code";\n'
    )


def test_drop_index_takes_the_index_identity_not_the_table():
    # An index name is unique within its SCHEMA, so `schema.name` is its
    # identity -- there is no `DROP INDEX ... ON table` in Postgres, and the
    # emitter is not even given a table.
    with pytest.raises(TypeError):
        drop_index_skeleton(table="public.orders", name="idx")


def test_drop_index_accepts_an_unqualified_name():
    assert drop_index_skeleton(index="idx_orders_code") == (
        'DROP INDEX "idx_orders_code";\n'
    )


def test_drop_index_never_emits_cascade_or_if_exists():
    text = drop_index_skeleton(index="public.i")
    assert "CASCADE" not in text
    assert "IF EXISTS" not in text


def test_drop_index_rejects_an_empty_name():
    with pytest.raises(SkeletonError, match="index must not be empty"):
        drop_index_skeleton(index="   ")


# --- comments --------------------------------------------------------------
def test_set_table_comment_golden_text():
    assert set_table_comment_skeleton(
        table="public.orders", comment="Customer orders"
    ) == ('COMMENT ON TABLE "public"."orders" IS \'Customer orders\';\n')


def test_set_column_comment_golden_text():
    assert set_column_comment_skeleton(
        table="public.orders", column="notes", comment="Free-form notes"
    ) == (
        'COMMENT ON COLUMN "public"."orders"."notes" IS \'Free-form notes\';\n'
    )


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_a_blank_comment_removes_the_comment_rather_than_emitting_nothing(blank):
    # `IS NULL` is Postgres's only spelling for "no comment"; `IS ''` would
    # leave an invisible empty-string comment behind.
    assert set_table_comment_skeleton(table="t", comment=blank) == (
        'COMMENT ON TABLE "t" IS NULL;\n'
    )
    assert set_column_comment_skeleton(table="t", column="c", comment=blank) == (
        'COMMENT ON COLUMN "t"."c" IS NULL;\n'
    )


def test_comment_single_quotes_are_doubled_not_refused():
    # A comment is a VALUE, not an identifier -- an apostrophe is ordinary
    # English prose, so it is escaped rather than rejected.
    assert set_table_comment_skeleton(table="t", comment="the user's table") == (
        "COMMENT ON TABLE \"t\" IS 'the user''s table';\n"
    )


def test_comment_cannot_close_the_statement():
    text = set_column_comment_skeleton(
        table="t", column="c", comment="'; DROP TABLE users; --"
    )
    assert text == (
        "COMMENT ON COLUMN \"t\".\"c\" IS '''; DROP TABLE users; --';\n"
    )
    # One statement -- the payload stayed inside the literal.
    assert text.count(";\n") == 1


def test_comment_may_contain_sql_comment_introducers_and_parens():
    # Unlike a USING clause, a comment is not an expression: `--` and an
    # unbalanced paren are ordinary characters inside a string literal.
    assert "IS 'see -- note (draft';\n" in set_table_comment_skeleton(
        table="t", comment="see -- note (draft"
    )


def test_comment_rejects_a_nul_character():
    with pytest.raises(SkeletonError, match="NUL character"):
        set_table_comment_skeleton(table="t", comment="bad\x00comment")


def test_add_column_and_set_column_comment_share_one_renderer():
    # Slice 1 built the column-comment renderer for Add column; slice 3
    # promoted it rather than writing a second one, so the two must agree
    # character for character.
    from_add = add_column_skeleton(
        table="public.orders", column="notes", datatype="text", comment="hello"
    )
    standalone = set_column_comment_skeleton(
        table="public.orders", column="notes", comment="hello"
    )
    assert from_add.endswith(standalone)


def test_add_column_blank_comment_still_emits_no_statement_at_all():
    # The one place blank does NOT mean `IS NULL`: an Add-column statement
    # without a comment simply carries no comment clause.
    text = add_column_skeleton(table="t", column="c", datatype="text", comment="")
    assert "COMMENT ON" not in text


# --- create table ----------------------------------------------------------
def test_create_table_golden_text():
    assert create_table_skeleton(
        table="public.orders",
        columns=[
            ColumnSpec("id", "bigint", nullable=False),
            ColumnSpec("code", "text"),
            ColumnSpec("created_at", "timestamptz", default="now()"),
        ],
        primary_key=["id"],
    ) == (
        'CREATE TABLE "public"."orders" (\n'
        '    "id" bigint NOT NULL,\n'
        '    "code" text,\n'
        '    "created_at" timestamptz DEFAULT now(),\n'
        '    PRIMARY KEY ("id")\n'
        ");\n"
    )


def test_create_table_without_a_primary_key_emits_none():
    text = create_table_skeleton(table="t", columns=[ColumnSpec("a", "text")])
    assert text == 'CREATE TABLE "t" (\n    "a" text\n);\n'
    assert "PRIMARY KEY" not in text


def test_create_table_primary_key_is_emitted_unnamed():
    # Unlike slice 2's ADD CONSTRAINT, whose auto-names are unpredictable to a
    # human, a table's PK auto-name (`orders_pkey`) is the convention already.
    text = create_table_skeleton(
        table="orders", columns=[ColumnSpec("id", "bigint")], primary_key=["id"]
    )
    assert "CONSTRAINT" not in text
    assert 'PRIMARY KEY ("id")' in text


def test_create_table_multi_column_primary_key_preserves_order():
    text = create_table_skeleton(
        table="t",
        columns=[ColumnSpec("tenant", "text"), ColumnSpec("id", "bigint")],
        primary_key=["tenant", "id"],
    )
    assert 'PRIMARY KEY ("tenant", "id")' in text


def test_create_table_column_order_is_the_caller_order():
    text = create_table_skeleton(
        table="t", columns=[ColumnSpec("b", "text"), ColumnSpec("a", "text")]
    )
    assert text.index('"b"') < text.index('"a"')


def test_create_table_rejects_no_columns():
    with pytest.raises(SkeletonError, match="at least one column"):
        create_table_skeleton(table="t", columns=[])


def test_create_table_rejects_a_duplicate_column():
    with pytest.raises(SkeletonError, match="same column twice"):
        create_table_skeleton(
            table="t", columns=[ColumnSpec("a", "text"), ColumnSpec("a", "integer")]
        )


def test_create_table_rejects_a_primary_key_naming_an_undefined_column():
    with pytest.raises(SkeletonError, match="does not define"):
        create_table_skeleton(
            table="t", columns=[ColumnSpec("a", "text")], primary_key=["b"]
        )


def test_create_table_rejects_an_empty_column_name():
    with pytest.raises(SkeletonError, match="column name must not be empty"):
        create_table_skeleton(table="t", columns=[ColumnSpec("  ", "text")])


def test_create_table_rejects_a_missing_datatype():
    with pytest.raises(SkeletonError, match="needs a datatype"):
        create_table_skeleton(table="t", columns=[ColumnSpec("a", "")])


def test_create_table_rejects_an_unsafe_datatype():
    with pytest.raises(SkeletonError, match="unsafe or malformed datatype"):
        create_table_skeleton(
            table="t", columns=[ColumnSpec("a", "text; DROP TABLE users")]
        )


def test_create_table_refuses_a_hostile_column_name():
    with pytest.raises(UnsafeIdentifierError):
        create_table_skeleton(table="t", columns=[ColumnSpec('a"b', "text")])


def test_create_table_default_is_validated_like_every_other_expression():
    with pytest.raises(SkeletonError, match="unbalanced parentheses"):
        create_table_skeleton(
            table="t", columns=[ColumnSpec("a", "text", default="coalesce(x, 0")]
        )


def test_create_table_default_names_the_offending_column():
    with pytest.raises(SkeletonError, match='"a"'):
        create_table_skeleton(
            table="t", columns=[ColumnSpec("a", "text", default="0 -- x")]
        )


def test_create_table_blank_default_is_refused_not_silently_dropped():
    # `None` is "no DEFAULT"; an empty string is a syntax error, and the
    # dialog layer is the one that maps blank to None.
    with pytest.raises(SkeletonError, match="must not be empty"):
        create_table_skeleton(table="t", columns=[ColumnSpec("a", "text", default="")])


def test_create_table_expresses_nothing_it_cannot_express_correctly():
    # The refusal list from `create_table_skeleton`'s docstring: no FK, no
    # UNIQUE/CHECK, no identity, no partitioning, no IF NOT EXISTS. Those are
    # the other dialogs' job, applied once the table exists.
    text = create_table_skeleton(
        table="t",
        columns=[ColumnSpec("id", "bigint", nullable=False)],
        primary_key=["id"],
    )
    for absent in (
        "REFERENCES",
        "UNIQUE",
        "CHECK",
        "GENERATED",
        "PARTITION",
        "INHERITS",
        "IF NOT EXISTS",
        "UNLOGGED",
    ):
        assert absent not in text


def test_create_table_column_spec_defaults_are_nullable_and_defaultless():
    spec = ColumnSpec("a", "text")
    assert spec.nullable is True
    assert spec.default is None


# --- drop table ------------------------------------------------------------
def test_drop_table_golden_text():
    assert drop_table_skeleton(table="public.orders") == (
        'DROP TABLE "public"."orders";\n'
    )


def test_drop_table_never_emits_cascade_or_if_exists():
    # No CASCADE for `drop_column_skeleton`'s reason; the tab-is-the-safeguard
    # ruling is about confirmations, not about widening the statement.
    text = drop_table_skeleton(table="t")
    assert "CASCADE" not in text
    assert "IF EXISTS" not in text


# --- rules that hold across every slice-3 operation ------------------------
@pytest.mark.parametrize("op", sorted(_TABLE_OPS))
def test_every_table_op_quotes_its_qualified_name(op):
    text = _table_op(op)
    assert '"public"."orders"' in text
    assert text.endswith(";\n")


@pytest.mark.parametrize("op", sorted(_TABLE_OPS))
def test_every_table_op_accepts_an_unqualified_name(op):
    assert '"orders"' in _table_op(op, qualified="orders")


@pytest.mark.parametrize("op", sorted(_TABLE_OPS))
def test_every_table_op_rejects_an_empty_qualified_name(op):
    with pytest.raises(SkeletonError, match="must not be empty"):
        _table_op(op, qualified="   ")


@pytest.mark.parametrize("op", sorted(_TABLE_OPS))
def test_every_table_op_rejects_an_empty_name_part(op):
    with pytest.raises(SkeletonError, match="empty name part"):
        _table_op(op, qualified="public.")


@pytest.mark.parametrize("op", sorted(_TABLE_OPS))
@pytest.mark.parametrize("hostile", ['t"; DROP TABLE users; --', "public.a b", "x'y"])
def test_every_table_op_refuses_a_hostile_qualified_name(op, hostile):
    with pytest.raises(UnsafeIdentifierError):
        _table_op(op, qualified=hostile)


@pytest.mark.parametrize("op", sorted(_TABLE_OPS))
def test_every_table_op_preserves_mixed_case_by_quoting(op):
    assert '"MySchema"."MyTable"' in _table_op(op, qualified="MySchema.MyTable")


@pytest.mark.parametrize("op", sorted(_TABLE_OPS))
def test_every_table_op_quotes_a_reserved_word_name(op):
    assert '"order"' in _table_op(op, qualified="order")


@pytest.mark.parametrize("op", sorted(_TABLE_OPS))
def test_every_table_op_is_deterministic(op):
    assert _table_op(op) == _table_op(op)


@pytest.mark.parametrize("op", sorted(_TABLE_OPS))
def test_every_table_op_is_keyword_only(op):
    # Positional arguments would make `drop_index_skeleton(t)` look like every
    # other emitter while meaning something different.
    func, _key, extra = _TABLE_OPS[op]
    with pytest.raises(TypeError):
        func(*extra.values())


def test_skeletons_are_deterministic():
    assert function_skeleton(name="f", return_type="integer") == function_skeleton(
        name="f", return_type="integer"
    )
    assert _trigger() == _trigger()
