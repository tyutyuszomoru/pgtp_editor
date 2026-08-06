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

# tests/db/test_sandbox_query.py
"""Tests for pgtp_editor.db.sandbox_query -- ad-hoc SQL against the sandbox.

psycopg is never imported: every run goes through an injected `runner=`, and
one test asserts that the default path is not even reached. The `SandboxSession`
is constructed directly (not via `open_sandbox`) because these tests are about
the result model, not the ownership gate -- which `test_sandbox.py` covers.
"""
import pytest

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.sandbox import SandboxMode, SandboxSession
from pgtp_editor.db.sandbox_query import (
    DEFAULT_MAX_ROWS,
    QueryOutcome,
    QueryResult,
    RawResult,
    run_sandbox_query,
    status_line,
)

PARAMS = ConnectionParams(host="localhost", port="5432", database="pgtp_sandbox_demo")


def make_session() -> SandboxSession:
    return SandboxSession(params=PARAMS, mode=SandboxMode.SCHEMA_ONLY)


class RecordingRunner:
    """A `QueryRunner` that records its call and returns a canned `RawResult`."""

    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[ConnectionParams, str, int]] = []

    def __call__(self, params, sql, *, max_rows):
        self.calls.append((params, sql, max_rows))
        if self.error is not None:
            raise self.error
        return self.result


# -- rows ------------------------------------------------------------------


def test_rows_and_columns_are_parsed():
    runner = RecordingRunner(
        RawResult(columns=("id", "name"), rows=[(1, "a"), (2, None)], affected=2)
    )
    result = run_sandbox_query(make_session(), "SELECT id, name FROM t", runner=runner)

    assert result.outcome is QueryOutcome.ROWS
    assert result.returns_rows is True
    assert result.ok is True
    assert result.columns == ("id", "name")
    assert result.rows == ((1, "a"), (2, None))
    assert result.row_count == 2
    assert result.truncated is False
    assert result.error is None
    assert result.sql == "SELECT id, name FROM t"


def test_zero_rows_is_still_a_result_set():
    runner = RecordingRunner(RawResult(columns=("id",), rows=[]))
    result = run_sandbox_query(make_session(), "SELECT id FROM t WHERE false", runner=runner)

    assert result.outcome is QueryOutcome.ROWS
    assert result.row_count == 0
    assert result.columns == ("id",)


def test_query_targets_the_sessions_params():
    runner = RecordingRunner(RawResult(columns=("x",), rows=[(1,)]))
    run_sandbox_query(make_session(), "SELECT 1", runner=runner)

    params, sql, max_rows = runner.calls[0]
    assert params is PARAMS
    assert sql == "SELECT 1"
    assert max_rows == DEFAULT_MAX_ROWS


def test_run_sandbox_query_requires_a_session_not_bare_params():
    """Sandbox-targeted by construction: there is no ConnectionParams overload,
    so a caller cannot casually point ad-hoc SQL at production."""
    runner = RecordingRunner(RawResult(columns=("x",), rows=[(1,)]))
    with pytest.raises(TypeError):
        run_sandbox_query(PARAMS, "SELECT 1", runner=runner)  # type: ignore[arg-type]
    # Loud, and nothing was sent anywhere -- not turned into a tidy "error
    # result" that would read as if the server had refused it.
    assert runner.calls == []


# -- no result set ---------------------------------------------------------


def test_statement_without_a_result_set_is_distinguishable():
    runner = RecordingRunner(RawResult(columns=None, affected=3, status="UPDATE 3"))
    result = run_sandbox_query(make_session(), "UPDATE t SET x = 1", runner=runner)

    assert result.outcome is QueryOutcome.NO_ROWS
    assert result.returns_rows is False
    assert result.ok is True
    assert result.columns == ()
    assert result.rows == ()
    assert result.affected == 3
    assert result.status == "UPDATE 3"
    assert "UPDATE 3" in status_line(result)
    assert "3 rows affected" in status_line(result)


def test_no_rows_and_empty_select_produce_different_status_lines():
    empty_select = run_sandbox_query(
        make_session(), "SELECT 1 WHERE false", runner=RecordingRunner(RawResult(columns=("x",)))
    )
    dml = run_sandbox_query(
        make_session(), "DELETE FROM t", runner=RecordingRunner(RawResult(columns=None, affected=0, status="DELETE 0"))
    )
    assert status_line(empty_select) != status_line(dml)
    assert "0 rows" in status_line(empty_select)
    assert "no result set" in status_line(dml)


# -- errors ----------------------------------------------------------------


def test_error_carries_the_database_message_and_is_not_an_empty_result():
    runner = RecordingRunner(
        error=RuntimeError('ERROR:  relation "nope" does not exist\nLINE 1: SELECT * FROM nope')
    )
    result = run_sandbox_query(make_session(), "SELECT * FROM nope", runner=runner)

    assert result.outcome is QueryOutcome.ERROR
    assert result.ok is False
    assert result.returns_rows is False
    assert 'relation "nope" does not exist' in result.error
    assert result.rows == ()
    assert status_line(result).startswith("Error: ")


def test_error_with_empty_message_still_names_something():
    result = run_sandbox_query(
        make_session(), "SELECT 1", runner=RecordingRunner(error=ValueError(""))
    )
    assert result.error == "ValueError"


def test_run_sandbox_query_never_raises():
    result = run_sandbox_query(
        make_session(), "SELECT 1", runner=RecordingRunner(error=KeyError("boom"))
    )
    assert result.outcome is QueryOutcome.ERROR


# -- the row cap -----------------------------------------------------------


def test_row_cap_truncates_and_flags_it():
    # The runner is asked for max_rows + 1 and hands back that many: truncation
    # is then a fact, not a guess.
    runner = RecordingRunner(RawResult(columns=("n",), rows=[(i,) for i in range(4)]))
    result = run_sandbox_query(make_session(), "SELECT n FROM big", max_rows=3, runner=runner)

    assert result.truncated is True
    assert result.row_count == 3
    assert result.rows == ((0,), (1,), (2,))
    assert result.max_rows == 3
    assert runner.calls[0][2] == 3


def test_truncation_is_visible_in_the_status_line():
    runner = RecordingRunner(RawResult(columns=("n",), rows=[(i,) for i in range(4)]))
    result = run_sandbox_query(make_session(), "SELECT n FROM big", max_rows=3, runner=runner)
    line = status_line(result)
    assert "TRUNCATED" in line
    assert "3" in line


def test_exactly_the_cap_is_not_truncated():
    runner = RecordingRunner(RawResult(columns=("n",), rows=[(i,) for i in range(3)]))
    result = run_sandbox_query(make_session(), "SELECT n FROM big", max_rows=3, runner=runner)
    assert result.truncated is False
    assert result.row_count == 3
    assert "TRUNCATED" not in status_line(result)


def test_negative_cap_is_refused():
    with pytest.raises(ValueError):
        run_sandbox_query(make_session(), "SELECT 1", max_rows=-1, runner=RecordingRunner())


def test_default_cap_is_sane():
    assert 100 <= DEFAULT_MAX_ROWS <= 100_000


# -- no connection ---------------------------------------------------------


def test_no_connection_is_opened(monkeypatch):
    """The default runner is the only psycopg touchpoint; with a runner
    injected it must never be consulted, so importing/using this module cannot
    open a socket."""
    import pgtp_editor.db.sandbox_query as module

    def explode(*_args, **_kwargs):  # pragma: no cover - must not be called
        raise AssertionError("the real psycopg runner was invoked")

    monkeypatch.setattr(module, "_psycopg_runner", explode)
    monkeypatch.setattr(module, "DEFAULT_QUERY_RUNNER", explode)

    result = run_sandbox_query(
        make_session(), "SELECT 1", runner=RecordingRunner(RawResult(columns=("x",), rows=[(1,)]))
    )
    assert result.outcome is QueryOutcome.ROWS


# -- timing ----------------------------------------------------------------


def test_elapsed_is_measured_through_the_injected_clock():
    ticks = iter([1.0, 1.25])
    result = run_sandbox_query(
        make_session(),
        "SELECT 1",
        runner=RecordingRunner(RawResult(columns=("x",), rows=[(1,)])),
        clock=lambda: next(ticks),
    )
    assert result.elapsed_ms == pytest.approx(250.0)
    assert "250 ms" in status_line(result)


def test_failed_helper_sets_both_outcome_and_error():
    result = QueryResult.failed("SELECT 1", "boom")
    assert result.outcome is QueryOutcome.ERROR
    assert result.error == "boom"
    assert result.ok is False
