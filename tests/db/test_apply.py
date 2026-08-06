# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# tests/db/test_apply.py
"""Tests for pgtp_editor.db.apply -- the ladder's write seam (§18.5 D3a).

psycopg is never imported: every run goes through an injected `runner=`, and one
test asserts the default runner is not even touched. The point of most of these
tests is **attribution**: a failure in the check SELECT must never come back
looking like a failure in the user's DDL.
"""
import pytest

from pgtp_editor.db.apply import (
    ApplyOutcome,
    StatementFailure,
    StatementResult,
    apply_ddl,
    line_of_position,
)
from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.sandbox import SandboxMode, SandboxSession

PARAMS = ConnectionParams(host="localhost", port="5432", database="pgtp_sandbox_demo")

#: The ladder D3a describes: session SETs, the DDL, then the check SELECT.
LADDER = [
    "SET plpgsql.extra_warnings TO 'all'",
    "CREATE FUNCTION s.f() RETURNS int LANGUAGE plpgsql AS $$BEGIN RETURN 1; END$$",
    "SELECT * FROM plpgsql_check_function_tb(fnname => 's.f()')",
]
DDL_INDEX = 1
CHECK_INDEX = 2


class RecordingRunner:
    """An `ApplyRunner` that records its call and replays a canned answer."""

    def __init__(self, results=None, error: BaseException | None = None) -> None:
        self.results = results
        self.error = error
        self.calls: list[tuple[ConnectionParams, list[str], bool]] = []

    def __call__(self, params, statements, *, commit):
        self.calls.append((params, list(statements), commit))
        if self.error is not None:
            raise self.error
        if self.results is not None:
            return self.results
        return [
            StatementResult(index=i, statement=s, status="OK")
            for i, s in enumerate(statements)
        ]


class FakePgError(Exception):
    """A stand-in for a psycopg `Error`: `sqlstate` plus a `diag` object.
    Read by `getattr`, so the real driver and this double behave identically."""

    class Diag:
        def __init__(self, detail="", hint="", position=None):
            self.message_detail = detail
            self.message_hint = hint
            self.statement_position = position

    def __init__(self, message, sqlstate="", detail="", hint="", position=None):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = self.Diag(detail, hint, position)


def exploding_runner(*args, **kwargs):  # pragma: no cover - must never run
    raise AssertionError("the default runner must never be reached in tests")


# -- success ---------------------------------------------------------------

def test_success_reports_no_statement_index_and_commits():
    runner = RecordingRunner()
    outcome = apply_ddl(PARAMS, LADDER, runner=runner)
    assert outcome.ok is True
    # A successful run must NOT carry an index: "statement 0" and "no statement
    # failed" are different facts and the panel prints the former.
    assert outcome.statement_index is None
    assert outcome.committed is True
    assert len(outcome.results) == 3
    assert outcome.statuses == ("OK", "OK", "OK")


def test_one_call_one_transaction_with_the_whole_ladder():
    """The ladder is necessarily ONE call: the SETs are session-scoped and the
    check must see the uncommitted DDL."""
    runner = RecordingRunner()
    apply_ddl(PARAMS, LADDER, runner=runner)
    assert len(runner.calls) == 1
    params, statements, commit = runner.calls[0]
    assert params is PARAMS
    assert statements == LADDER
    assert commit is True


def test_probe_run_is_not_committed_and_says_so():
    runner = RecordingRunner()
    outcome = apply_ddl(PARAMS, LADDER, commit=False, runner=runner)
    assert outcome.ok is True
    # `committed` is a stated fact, not inferred from `ok`.
    assert outcome.committed is False
    assert runner.calls[0][2] is False


def test_rows_come_from_the_last_result_set():
    results = [
        StatementResult(index=0, statement=LADDER[0], status="SET"),
        StatementResult(index=1, statement=LADDER[1], status="CREATE FUNCTION"),
        StatementResult(
            index=2,
            statement=LADDER[2],
            columns=("functionid", "lineno", "level"),
            rows=((1234, 3, "warning"),),
            status="SELECT 1",
        ),
    ]
    outcome = apply_ddl(PARAMS, LADDER, runner=RecordingRunner(results))
    assert outcome.rows == ((1234, 3, "warning"),)
    assert outcome.results[2].returns_rows is True
    assert outcome.results[0].returns_rows is False


def test_no_result_set_anywhere_means_no_rows():
    outcome = apply_ddl(PARAMS, LADDER, runner=RecordingRunner())
    assert outcome.rows == ()


def test_empty_statement_list_is_a_no_op_that_opens_nothing():
    outcome = apply_ddl(PARAMS, [], runner=exploding_runner)
    assert outcome.ok is True
    assert outcome.committed is False
    assert outcome.results == ()


def test_blank_statements_are_dropped_not_sent():
    runner = RecordingRunner()
    apply_ddl(PARAMS, ["", "   \n", "SELECT 1"], runner=runner)
    assert runner.calls[0][1] == ["SELECT 1"]


# -- attribution: WHICH statement failed -----------------------------------

def test_failure_in_the_check_call_is_attributed_to_the_check_call():
    """D3a's core requirement: a failure in the `plpgsql_check` SELECT must not
    be reported as 'your DDL is broken'."""
    error = FakePgError("ERROR:  missing trigger relation", sqlstate="42883")
    runner = RecordingRunner(error=StatementFailure(CHECK_INDEX, LADDER[CHECK_INDEX], error))
    outcome = apply_ddl(PARAMS, LADDER, runner=runner)
    assert outcome.ok is False
    assert outcome.statement_index == CHECK_INDEX
    assert outcome.statement_index != DDL_INDEX
    assert outcome.statement == LADDER[CHECK_INDEX]
    assert outcome.committed is False


def test_failure_in_the_ddl_is_attributed_to_the_ddl():
    error = FakePgError('ERROR:  syntax error at or near "RETRUN"', sqlstate="42601")
    runner = RecordingRunner(error=StatementFailure(DDL_INDEX, LADDER[DDL_INDEX], error))
    outcome = apply_ddl(PARAMS, LADDER, runner=runner)
    assert outcome.statement_index == DDL_INDEX
    assert outcome.sqlstate == "42601"


def test_failure_with_no_statement_text_recovers_it_from_the_list():
    runner = RecordingRunner(error=StatementFailure(DDL_INDEX, "", FakePgError("boom")))
    outcome = apply_ddl(PARAMS, LADDER, runner=runner)
    assert outcome.statement == LADDER[DDL_INDEX]


def test_connection_failure_blames_no_statement():
    """No index means nothing of the caller's was judged -- never statement 0."""
    runner = RecordingRunner(error=OSError("could not connect to server"))
    outcome = apply_ddl(PARAMS, LADDER, runner=runner)
    assert outcome.ok is False
    assert outcome.statement_index is None
    assert "could not connect" in outcome.message


def test_failure_carries_the_servers_own_words():
    error = FakePgError(
        'ERROR:  column "qty" does not exist',
        sqlstate="42703",
        detail="the table was renamed",
        hint="Perhaps you meant quantity.",
        position=18,
    )
    runner = RecordingRunner(error=StatementFailure(0, "SELECT qty\n  FROM t", error))
    outcome = apply_ddl(PARAMS, ["SELECT qty\n  FROM t"], runner=runner)
    assert outcome.sqlstate == "42703"
    assert outcome.message == 'ERROR:  column "qty" does not exist'
    assert outcome.detail == "the table was renamed"
    assert outcome.hint == "Perhaps you meant quantity."
    assert outcome.position == 18


def test_error_with_no_diagnostics_degrades_quietly():
    runner = RecordingRunner(error=StatementFailure(0, "SELECT 1", RuntimeError("nope")))
    outcome = apply_ddl(PARAMS, ["SELECT 1"], runner=runner)
    assert outcome.message == "nope"
    assert (outcome.sqlstate, outcome.detail, outcome.hint) == ("", "", "")
    assert outcome.position is None
    assert outcome.line is None


def test_blank_error_message_falls_back_to_the_class_name():
    runner = RecordingRunner(error=StatementFailure(0, "SELECT 1", RuntimeError("")))
    outcome = apply_ddl(PARAMS, ["SELECT 1"], runner=runner)
    assert outcome.message == "RuntimeError"


# -- position -> line (§18.5 D4's exact rule) -------------------------------

@pytest.mark.parametrize(
    "position,expected",
    [
        (None, None),
        (0, None),
        (-1, None),
        (1, 1),
        (5, 1),
        (12, 2),
        (999, None),  # past the end: no line rather than a guessed one
    ],
)
def test_line_of_position(position, expected):
    statement = "SELECT 1\nFROM t\nWHERE x"
    assert line_of_position(statement, position) == expected


def test_line_of_position_on_empty_statement_is_none():
    assert line_of_position("", 3) is None


def test_failure_line_is_derived_from_position():
    error = FakePgError("bad", position=12)
    statement = "SELECT 1\nFROM nope"
    runner = RecordingRunner(error=StatementFailure(0, statement, error))
    outcome = apply_ddl(PARAMS, [statement], runner=runner)
    assert outcome.line == 2


def test_non_numeric_position_yields_no_line():
    error = FakePgError("bad", position="somewhere")
    runner = RecordingRunner(error=StatementFailure(0, "SELECT 1", error))
    outcome = apply_ddl(PARAMS, ["SELECT 1"], runner=runner)
    assert outcome.position is None
    assert outcome.line is None


# -- the target seam -------------------------------------------------------

def test_a_sandbox_session_may_be_passed_directly():
    session = SandboxSession(params=PARAMS, mode=SandboxMode.SCHEMA_ONLY)
    runner = RecordingRunner()
    apply_ddl(session, LADDER, runner=runner)
    assert runner.calls[0][0] is PARAMS


def test_a_non_target_is_a_loud_programming_error():
    with pytest.raises(TypeError, match="ConnectionParams"):
        apply_ddl("prod on db01", LADDER, runner=exploding_runner)


def test_a_bare_string_statement_is_refused():
    with pytest.raises(TypeError, match="SEQUENCE"):
        apply_ddl(PARAMS, "SELECT 1", runner=exploding_runner)


def test_a_non_string_statement_is_refused():
    with pytest.raises(TypeError, match="not str"):
        apply_ddl(PARAMS, ["SELECT 1", None], runner=exploding_runner)


# -- the panel's duck-typed read ------------------------------------------

def test_the_audit_panel_renders_a_failed_outcome():
    """`ui/ddl_object_editor.py::_result_lines` reads `ok`, `statement_index`,
    `sqlstate` and `message` by attribute -- this asserts the contract it
    depends on, without importing Qt."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel

    outcome = ApplyOutcome.failed(
        "ERROR:  syntax error",
        statement_index=CHECK_INDEX,
        statement=LADDER[CHECK_INDEX],
        sqlstate="42601",
    )
    lines = DdlObjectEditorPanel._result_lines(None, outcome)
    assert lines == [f"  failed at statement {CHECK_INDEX}: 42601 ERROR:  syntax error"]


def test_a_successful_outcome_produces_no_failure_line():
    from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel

    outcome = ApplyOutcome.succeeded((), committed=True)
    assert DdlObjectEditorPanel._result_lines(None, outcome) == []


# -- no connection is ever opened ------------------------------------------

def test_psycopg_is_imported_lazily_inside_the_runner_only():
    import inspect

    import pgtp_editor.db.apply as module

    # No module-scope name: the driver import lives inside `_psycopg_runner`,
    # so importing this module never requires psycopg to be installed.
    assert "psycopg" not in vars(module)
    assert "import psycopg" in inspect.getsource(module._psycopg_runner)


def test_module_is_qt_free():
    import inspect

    import pgtp_editor.db.apply as module

    source = inspect.getsource(module)
    assert "PySide6" not in source
    assert "QtCore" not in source


# -- the notice channel (§18.5 D3's tier 1 has no other one) ----------------


class FakeDiagnostic:
    """A stand-in for psycopg's `Diagnostic`, read by `getattr` -- the real
    driver object and this double are interchangeable by construction."""

    def __init__(
        self,
        message_primary="",
        severity_nonlocalized="WARNING",
        severity="WARNUNG",
        message_detail="",
        message_hint="",
        context="",
        sqlstate="",
    ):
        self.message_primary = message_primary
        self.severity_nonlocalized = severity_nonlocalized
        self.severity = severity
        self.message_detail = message_detail
        self.message_hint = message_hint
        self.context = context
        self.sqlstate = sqlstate


def test_normalize_notice_prefers_the_nonlocalized_severity():
    """A server under a non-English `lc_messages` localizes `severity`; anything
    matching on "WARNING" would then silently miss every finding."""
    from pgtp_editor.db.apply import normalize_notice

    notice = normalize_notice(
        FakeDiagnostic(
            message_primary="variable \"x\" shadows a previously defined variable",
            context='compilation of PL/pgSQL function "f" near line 3',
            sqlstate="42000",
            message_detail="d",
            message_hint="h",
        )
    )
    assert notice.severity == "WARNING"
    assert "shadows" in notice.message
    assert notice.context.endswith("near line 3")
    assert (notice.sqlstate, notice.detail, notice.hint) == ("42000", "d", "h")


def test_normalize_notice_never_raises_on_a_hostile_diagnostic():
    from pgtp_editor.db.apply import normalize_notice

    class Hostile:
        @property
        def message_primary(self):
            raise RuntimeError("boom")

    assert normalize_notice(Hostile()).message == ""


def test_notices_reach_the_outcome_when_the_runner_captures_them():
    from pgtp_editor.db.apply import Notice, RunOutcome

    notice = Notice(message="too many rows", severity="WARNING", context="near line 2")

    def runner(params, statements, *, commit):
        return RunOutcome(
            results=tuple(
                StatementResult(index=i, statement=s) for i, s in enumerate(statements)
            ),
            notices=(notice,),
        )

    outcome = apply_ddl(PARAMS, LADDER, commit=True, runner=runner)

    assert outcome.ok is True
    assert outcome.notices == (notice,)
    assert outcome.notices_captured is True


def test_a_runner_that_returns_a_bare_list_did_not_capture_notices():
    """The distinction tier 1 depends on: "there were no warnings" and "nobody
    was listening" must never be the same answer (§18.5 D3)."""
    outcome = apply_ddl(PARAMS, LADDER, commit=True, runner=RecordingRunner())

    assert outcome.ok is True
    assert outcome.notices == ()
    assert outcome.notices_captured is False


def test_notices_collected_before_a_failure_are_not_discarded():
    """Extra-warnings are emitted WHILE `CREATE FUNCTION` compiles, so a
    statement can produce real findings and then fail."""
    from pgtp_editor.db.apply import Notice

    notice = Notice(message="shadowed variable", severity="WARNING")

    def runner(params, statements, *, commit):
        raise StatementFailure(
            DDL_INDEX,
            statements[DDL_INDEX],
            FakePgError("ERROR:  syntax error", sqlstate="42601"),
            notices=[notice],
            notices_captured=True,
            results=[StatementResult(index=0, statement=statements[0])],
        )

    outcome = apply_ddl(PARAMS, LADDER, commit=True, runner=runner)

    assert outcome.ok is False
    assert outcome.statement_index == DDL_INDEX
    assert outcome.notices == (notice,)
    assert outcome.notices_captured is True
    # The statements that DID run are kept, so tier attribution still works.
    assert outcome.reached(0) is True
    assert outcome.reached(DDL_INDEX) is False


def test_the_real_runner_registers_a_notice_handler():
    """The psycopg 3 API actually used: `Connection.add_notice_handler`."""
    import inspect

    from pgtp_editor.db import apply as module

    source = inspect.getsource(module._psycopg_runner)
    assert "add_notice_handler" in source
    assert "normalize_notice" in source


# -- tier attribution primitives -------------------------------------------


def test_result_at_and_reached_answer_per_statement():
    outcome = apply_ddl(PARAMS, LADDER, commit=True, runner=RecordingRunner())

    assert outcome.result_at(CHECK_INDEX).statement == LADDER[CHECK_INDEX]
    assert outcome.reached(CHECK_INDEX) is True
    assert outcome.result_at(99) is None
    assert outcome.reached(None) is False


def test_a_check_failure_leaves_the_ddl_statement_reported_as_reached():
    """The misattribution this seam exists to prevent, as data."""

    def runner(params, statements, *, commit):
        raise StatementFailure(
            CHECK_INDEX,
            statements[CHECK_INDEX],
            FakePgError("ERROR:  function does not exist", sqlstate="42883"),
            results=[
                StatementResult(index=i, statement=s)
                for i, s in enumerate(statements[:CHECK_INDEX])
            ],
        )

    outcome = apply_ddl(PARAMS, LADDER, commit=True, runner=runner)

    assert outcome.statement_index == CHECK_INDEX
    assert outcome.reached(DDL_INDEX) is True
    assert outcome.reached(CHECK_INDEX) is False


# -- the shared diagnostics reader ------------------------------------------


def test_diagnose_reads_the_shared_fields_once():
    from pgtp_editor.db.apply import diagnose

    fields = diagnose(
        FakePgError(
            "ERROR:  syntax error", sqlstate="42601", detail="d", hint="h", position=10
        ),
        "SELECT 1\nFROM oops",
    )
    assert fields.message == "ERROR:  syntax error"
    assert fields.sqlstate == "42601"
    assert (fields.detail, fields.hint) == ("d", "h")
    assert fields.position == 10
    assert fields.line == 2


def test_diagnose_of_nothing_is_empty_not_a_guess():
    from pgtp_editor.db.apply import diagnose

    assert diagnose(None).message == ""
    assert diagnose(None).line is None
