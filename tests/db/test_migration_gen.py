# tests/db/test_migration_gen.py
"""Pure tests for the routine/trigger migration emitter (no Qt, no live DB).

Output is deterministic by contract, so most assertions are golden strings.
"""
import inspect

import pytest

from pgtp_editor.db import migration_gen
from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.migration_gen import (
    UnsupportedDifference,
    connection_summary,
    generate_migration,
)
from pgtp_editor.db.schema_diff import SchemaDifference

NOTE = (
    "-- NOTE: table and column changes are NOT included in this script; it covers\n"
    "--       routine and trigger changes only (CONSOLIDATED_SPEC.md 18.3)."
)

FUNC_DEF = (
    "CREATE OR REPLACE FUNCTION pr.f()\n"
    " RETURNS void\n"
    " LANGUAGE plpgsql\n"
    "AS $function$BEGIN END$function$"
)


def _routine(kind, identity, *, old_def=None, new_def=None, language="plpgsql"):
    return SchemaDifference(
        kind=kind,
        object_kind="routine",
        identity=identity,
        old_def=old_def,
        new_def=new_def,
        language=language,
    )


def _trigger(kind, identity, *, old_def=None, new_def=None):
    return SchemaDifference(
        kind=kind,
        object_kind="trigger",
        identity=identity,
        old_def=old_def,
        new_def=new_def,
        language="",
    )


# --- the R18 docstring guard ------------------------------------------------


def test_module_docstring_opens_with_the_limitation():
    first_line = (migration_gen.__doc__ or "").splitlines()[0].lower()
    assert "routine" in first_line and "trigger" in first_line
    assert "table" in first_line


# --- golden output ----------------------------------------------------------


def test_added_routine_golden():
    sql = generate_migration(
        [_routine("added", "pr.f()", new_def=FUNC_DEF)],
        header="pgtp-editor deployment script",
    )
    assert sql == (
        "-- pgtp-editor deployment script\n"
        f"{NOTE}\n"
        "\n"
        f"{FUNC_DEF};\n"
    )


def test_changed_routine_golden():
    sql = generate_migration(
        [_routine("changed", "pr.f()", old_def="OLD", new_def=FUNC_DEF)]
    )
    assert sql == f"{NOTE}\n\n{FUNC_DEF};\n"


def test_multiline_header_is_fully_commented():
    sql = generate_migration([], header="line one\nline two")
    assert sql == f"-- line one\n-- line two\n{NOTE}\n"


def test_empty_difference_list_still_states_the_limitation():
    assert generate_migration([]) == f"{NOTE}\n"


def test_trigger_drop_if_exists_precedes_the_create():
    definition = "CREATE TRIGGER trg BEFORE INSERT ON pr.t FOR EACH ROW EXECUTE FUNCTION pr.f()"
    sql = generate_migration([_trigger("added", "pr.t.trg", new_def=definition)])
    assert sql == (
        f"{NOTE}\n"
        "\n"
        "DROP TRIGGER IF EXISTS trg ON pr.t;\n"
        "\n"
        f"{definition};\n"
    )
    assert sql.index("DROP TRIGGER IF EXISTS") < sql.index("CREATE TRIGGER")


def test_changed_trigger_also_drops_first():
    sql = generate_migration([_trigger("changed", "pr.t.trg", old_def="OLD", new_def="NEW")])
    assert "DROP TRIGGER IF EXISTS trg ON pr.t;" in sql
    assert sql.index("DROP TRIGGER IF EXISTS trg ON pr.t;") < sql.index("NEW;")


def test_each_trigger_drop_immediately_precedes_its_own_create():
    # With several triggers the DROPs must stay paired with their creates, not
    # be hoisted into one block -- a hoisted DROP would delete a trigger the
    # script then fails to recreate if a later statement errors.
    sql = generate_migration(
        [
            _trigger("added", "pr.t.b_trg", new_def="CREATE TRIGGER b_trg"),
            _trigger("changed", "pr.t.a_trg", old_def="o", new_def="CREATE TRIGGER a_trg"),
        ]
    )
    statements = [block.strip() for block in sql.split("\n\n") if block.strip()]
    assert statements[-4:] == [
        "DROP TRIGGER IF EXISTS a_trg ON pr.t;",
        "CREATE TRIGGER a_trg;",
        "DROP TRIGGER IF EXISTS b_trg ON pr.t;",
        "CREATE TRIGGER b_trg;",
    ]


def test_added_routine_gets_no_drop_at_all():
    # Routines rely on `pg_get_functiondef`'s own CREATE OR REPLACE; emitting a
    # DROP FUNCTION first would break dependent views and grants.
    sql = generate_migration([_routine("added", "pr.f()", new_def=FUNC_DEF)])
    assert "DROP" not in sql


def test_statement_terminator_is_not_doubled():
    sql = generate_migration([_routine("added", "pr.f()", new_def="SELECT 1;")])
    assert sql.endswith("SELECT 1;\n")
    assert ";;" not in sql


# --- removed objects: commented-out DROPs only ------------------------------


def test_removed_routine_drop_is_commented_and_marked_for_review():
    sql = generate_migration([_routine("removed", "pr.gone(integer)", old_def="OLD")])
    assert "-- REVIEW:" in sql
    assert "pr.gone(integer)" in sql
    assert "-- DROP ROUTINE pr.gone(integer);" in sql
    # Never live DROP text: every DROP-bearing line is a comment.
    for line in sql.splitlines():
        if "DROP" in line:
            assert line.startswith("--"), line


def test_removed_trigger_drop_is_commented_and_marked_for_review():
    sql = generate_migration([_trigger("removed", "pr.t.trg", old_def="OLD")])
    assert "-- REVIEW:" in sql
    assert "-- DROP TRIGGER IF EXISTS trg ON pr.t;" in sql
    for line in sql.splitlines():
        if "DROP" in line:
            assert line.startswith("--"), line


def test_removed_objects_come_after_the_creates():
    sql = generate_migration(
        [
            _routine("removed", "pr.gone()", old_def="OLD"),
            _routine("added", "pr.new()", new_def="NEW"),
        ]
    )
    assert sql.index("NEW;") < sql.index("-- REVIEW:")


# --- Task 3: ordering -------------------------------------------------------


def test_routines_come_before_triggers_each_group_alphabetical():
    differences = [
        _trigger("added", "pr.t.z_trg", new_def="TZ"),
        _routine("added", "pr.m()", new_def="RM"),
        _trigger("added", "pr.t.a_trg", new_def="TA"),
        _routine("changed", "pr.a()", old_def="o", new_def="RA"),
        _routine("added", "pr.z()", new_def="RZ"),
    ]
    sql = generate_migration(differences)
    positions = [sql.index(marker) for marker in ("RA;", "RM;", "RZ;", "TA;", "TZ;")]
    assert positions == sorted(positions)


def test_ordering_is_independent_of_input_order():
    a = _routine("added", "pr.a()", new_def="RA")
    b = _routine("added", "pr.b()", new_def="RB")
    assert generate_migration([a, b]) == generate_migration([b, a])


def test_removed_objects_are_also_ordered_routines_then_triggers():
    differences = [
        _trigger("removed", "pr.t.trg", old_def="o"),
        _routine("removed", "pr.z()", old_def="o"),
        _routine("removed", "pr.a()", old_def="o"),
    ]
    sql = generate_migration(differences)
    positions = [
        sql.index("-- DROP ROUTINE pr.a();"),
        sql.index("-- DROP ROUTINE pr.z();"),
        sql.index("-- DROP TRIGGER IF EXISTS trg ON pr.t;"),
    ]
    assert positions == sorted(positions)


# --- Task 3: the non-plpgsql warning ----------------------------------------


def test_non_plpgsql_routine_triggers_the_header_warning():
    sql = generate_migration(
        [
            _routine("added", "pr.f()", new_def="F", language="sql"),
            _routine("added", "pr.g()", new_def="G", language="plpgsql"),
        ]
    )
    assert "-- WARNING: 1 non-PL/pgSQL routine(s) are included" in sql
    assert "resolved at CREATE time" in sql
    # The warning is part of the header block, before any statement.
    assert sql.index("-- WARNING:") < sql.index("F;")


def test_all_plpgsql_set_has_no_warning():
    sql = generate_migration(
        [
            _routine("added", "pr.f()", new_def="F", language="plpgsql"),
            _trigger("added", "pr.t.trg", new_def="T"),
        ]
    )
    assert "WARNING" not in sql


def test_language_case_is_not_load_bearing():
    sql = generate_migration([_routine("added", "pr.f()", new_def="F", language="PLpgSQL")])
    assert "WARNING" not in sql


def test_removed_non_plpgsql_routine_does_not_warn():
    # Only emitted (added/changed) routines can be mis-ordered; a commented-out
    # DROP cannot fail at CREATE time.
    sql = generate_migration([_routine("removed", "pr.f()", old_def="O", language="sql")])
    assert "WARNING" not in sql


def test_warning_counts_each_non_plpgsql_routine():
    sql = generate_migration(
        [
            _routine("added", "pr.f()", new_def="F", language="sql"),
            _routine("changed", "pr.g()", old_def="o", new_def="G", language="c"),
        ]
    )
    assert "-- WARNING: 2 non-PL/pgSQL routine(s) are included" in sql


# --- the refusals -----------------------------------------------------------


@pytest.mark.parametrize("object_kind", ["table", "column"])
def test_table_or_column_difference_raises_unsupported(object_kind):
    difference = SchemaDifference(
        kind="added",
        object_kind=object_kind,
        identity="pr.a",
        old_def=None,
        new_def="whatever",
    )
    with pytest.raises(UnsupportedDifference) as excinfo:
        generate_migration([difference])
    assert object_kind in str(excinfo.value)
    assert "pr.a" in str(excinfo.value)


def test_unsupported_is_raised_before_any_output_even_with_valid_siblings():
    differences = [
        _routine("added", "pr.f()", new_def="F"),
        SchemaDifference("added", "table", "pr.a", None, "T"),
    ]
    with pytest.raises(UnsupportedDifference):
        generate_migration(differences)


def test_unknown_object_kind_is_refused_not_skipped():
    difference = SchemaDifference("added", "sequence", "pr.s", None, "S")
    with pytest.raises(UnsupportedDifference):
        generate_migration([difference])


def test_unknown_kind_is_refused_not_skipped():
    with pytest.raises(ValueError):
        generate_migration([_routine("renamed", "pr.f()", new_def="F")])


# --- no password, ever ------------------------------------------------------


def test_connection_summary_never_renders_the_password():
    params = ConnectionParams(
        host="127.0.0.1", port="5432", database="d", user="u", password="s3cret"
    )
    summary = connection_summary(params)
    assert summary == "u@127.0.0.1:5432/d"
    assert "s3cret" not in summary


def test_header_built_from_connection_summaries_contains_no_password():
    params = ConnectionParams(
        host="db.example", port="5432", database="prod", user="deploy", password="hunter2"
    )
    header = "sandbox: {}\nproduction: {}".format(
        connection_summary(params), connection_summary(params)
    )
    sql = generate_migration([_routine("added", "pr.f()", new_def="F")], header=header)
    assert "hunter2" not in sql
    assert "password" not in sql.lower()
    assert "deploy@db.example:5432/prod" in sql


def test_connection_summary_never_reads_the_password_attribute():
    # Stronger than "the password is absent from the output": the function must
    # not even touch the field, so no future f-string edit can leak it and no
    # logging of the accessed attributes can either.
    class Exploding:
        host = "h"
        port = "5432"
        database = "d"
        user = "u"

        @property
        def password(self):  # pragma: no cover - must never be reached
            raise AssertionError("connection_summary read the password")

    assert connection_summary(Exploding()) == "u@h:5432/d"


def test_generated_script_never_contains_a_password_from_any_field():
    # The password is the only ConnectionParams field the header must not carry;
    # host/port/database/user are all expected to appear.
    params = ConnectionParams(
        host="db.example", port="5432", database="prod", user="deploy", password="p@ss w0rd!"
    )
    sql = generate_migration(
        [_routine("changed", "pr.f()", old_def="OLD", new_def=FUNC_DEF)],
        header="target: " + connection_summary(params),
    )
    assert params.password not in sql
    for field_value in (params.host, params.port, params.database, params.user):
        assert field_value in sql


# --- determinism ------------------------------------------------------------


def test_two_runs_over_identical_input_produce_identical_bytes():
    differences = [
        _routine("added", "pr.f()", new_def="F"),
        _trigger("added", "pr.t.trg", new_def="T"),
        _routine("removed", "pr.gone()", old_def="O"),
    ]
    first = generate_migration(differences, header="h")
    second = generate_migration(differences, header="h")
    assert first.encode("utf-8") == second.encode("utf-8")


def test_output_is_ascii_only():
    # Deployment scripts get pasted into psql on both platforms; a stray
    # non-ASCII character in the header block is a needless encoding hazard.
    sql = generate_migration([_routine("added", "pr.f()", new_def="F", language="sql")])
    sql.encode("ascii")


# --- purity guards ----------------------------------------------------------


def test_module_is_qt_free_and_psycopg_free():
    # Import lines only -- the docstring names both on purpose. `db.config`
    # (which imports Qt) is deliberately not imported either: `connection_summary`
    # is duck-typed on ConnectionParams.
    offenders = [
        line
        for line in inspect.getsource(migration_gen).splitlines()
        if line.startswith(("import ", "from "))
        and ("PySide6" in line or "psycopg" in line or "config" in line)
    ]
    assert offenders == []


def test_generate_migration_signature_matches_the_plan():
    parameters = inspect.signature(generate_migration).parameters
    assert list(parameters) == ["differences", "header"]
    assert parameters["header"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["header"].default == ""
