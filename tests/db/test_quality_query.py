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

# tests/db/test_quality_query.py
"""Tests for the quality (production) ad-hoc execution path — §18.5 D4b,
`FQ-260811020328`, commit model `DEC-260811023646`.

**No test here opens a connection.** The `QualityConnector` seam is injected
with a fake connection that records what it was asked to do, which is the whole
point of the seam: the durability behaviour — *nothing is committed until the
commit gesture* — is a property of this module's bookkeeping, and it must be
assertable without a server.
"""
import pytest

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.quality_query import (
    ABORTED_TEXT,
    CONNECTION_LOST_TEXT,
    DISCARD_TAB_CLOSED,
    DISCARD_WINDOW_CLOSED,
    NOTHING_PENDING_TEXT,
    QualityConnectionLost,
    QualitySession,
    TransactionOutcome,
    result_from_raw,
    run_quality_query,
    transaction_message,
)
from pgtp_editor.db.sandbox_query import (
    DEFAULT_STATEMENT_TIMEOUT_MS,
    MIN_STATEMENT_TIMEOUT_MS,
    TIMEOUT_SQLSTATE,
    QueryOutcome,
    RawResult,
)

PARAMS = ConnectionParams(
    host="db01", port=5432, database="prod", user="app", password="s3cret"
)


class Boom(Exception):
    """A rejected statement: the database said no, but the connection lives."""

    def __init__(self, message="ERROR: boom", sqlstate=""):
        super().__init__(message)
        self.sqlstate = sqlstate


class FakeConnection:
    """A `QualityConnection` that records the whole conversation.

    `answers` maps statement text to either a `RawResult` (success) or an
    exception instance (raised). Everything else succeeds as a no-result-set
    statement, so a test only spells out the statement it cares about.
    """

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.executed: list[tuple[str, int, int]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0
        self.commit_raises: BaseException | None = None
        self.rollback_raises: BaseException | None = None

    def execute(self, sql, *, max_rows, statement_timeout_ms):
        self.executed.append((sql, max_rows, statement_timeout_ms))
        answer = self.answers.get(sql)
        if isinstance(answer, BaseException):
            raise answer
        if answer is not None:
            return answer
        return RawResult(columns=None, rows=(), affected=1, status="UPDATE 1")

    def commit(self):
        if self.commit_raises is not None:
            raise self.commit_raises
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        if self.rollback_raises is not None:
            raise self.rollback_raises

    def close(self):
        self.closed += 1


def session_with(connection=None, params=PARAMS):
    """A session wired to a `FakeConnection`. Pass a dict of canned answers, or a
    prepared `FakeConnection`, or nothing."""
    if connection is None:
        connection = FakeConnection()
    elif isinstance(connection, dict):
        connection = FakeConnection(connection)
    opened: list[ConnectionParams] = []

    def connector(p):
        opened.append(p)
        return connection

    session = QualitySession(params, connector=connector)
    return session, connection, opened


# -- the held-open connection ----------------------------------------------


def test_no_connection_is_opened_until_the_first_statement():
    """Opening the console must connect to nothing: the connection is the
    session's, and a console someone opened and walked away from holds none."""
    session, connection, opened = session_with()
    assert opened == []
    assert session.is_open is False
    session.run("SELECT 1")
    assert opened == [PARAMS]
    assert session.is_open is True


def test_every_statement_of_a_run_shares_one_connection_and_one_transaction():
    session, connection, opened = session_with()
    session.run("UPDATE a SET x = 1")
    session.run("UPDATE b SET y = 2")
    assert len(opened) == 1
    assert [sql for sql, _r, _t in connection.executed] == [
        "UPDATE a SET x = 1",
        "UPDATE b SET y = 2",
    ]
    assert connection.commits == 0
    assert connection.rollbacks == 0


def test_a_run_leaves_nothing_durable_until_the_commit_gesture():
    """The safety property `DEC-260811023646` bought, asserted directly."""
    session, connection, _opened = session_with()
    session.run("DELETE FROM t")
    assert session.has_uncommitted_work is True
    assert connection.commits == 0

    outcome = session.commit()

    assert connection.commits == 1
    assert outcome.committed is True
    assert outcome.statements == 1
    assert session.has_uncommitted_work is False
    assert "COMMITTED" in transaction_message(outcome)


def test_discard_rolls_back_and_keeps_the_connection_for_the_next_run():
    session, connection, opened = session_with()
    session.run("DELETE FROM t")
    outcome = session.discard("you rolled it back")
    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert connection.closed == 0
    assert outcome.discarded is True
    assert session.has_uncommitted_work is False
    session.run("SELECT 1")
    assert len(opened) == 1


def test_committing_twice_is_refused_rather_than_committing_nothing_twice():
    session, connection, _opened = session_with()
    session.run("DELETE FROM t")
    session.commit()
    second = session.commit()
    assert second.committed is False
    assert connection.commits == 1
    assert transaction_message(second) == NOTHING_PENDING_TEXT


# -- a failed statement ----------------------------------------------------


def test_a_failed_statement_aborts_the_transaction_and_refuses_the_commit():
    session, connection, _opened = session_with({"BAD": Boom()})
    session.run("UPDATE a SET x = 1")
    result = session.run("BAD")

    assert result.ok is False
    assert "boom" in str(result.error)
    assert session.transaction_aborted is True

    refused = session.commit()
    assert refused.committed is False
    assert connection.commits == 0
    assert transaction_message(refused) == ABORTED_TEXT


def test_the_statement_timeout_reaches_the_quality_connection():
    session, connection, _opened = session_with()
    session.run("SELECT 1", max_rows=5, statement_timeout_ms=1234)
    assert connection.executed == [("SELECT 1", 5, 1234)]


def test_a_timeout_is_reworded_but_keeps_its_sqlstate_position_and_line():
    """The `57014` mapping is D4's, produced by D4's own named helper — the
    sentence must not be a second copy, and the clickable position must survive
    (a cancelled statement stays as navigable as any other failure)."""
    cancelled = Boom("canceling statement due to statement timeout")
    cancelled.sqlstate = TIMEOUT_SQLSTATE

    class Diag:
        message_primary = "canceling statement due to statement timeout"
        context = None
        message_detail = ""
        message_hint = ""
        statement_position = "9"

    cancelled.diag = Diag()

    session, _connection, _opened = session_with({"SELECT pg_sleep(9)": cancelled})
    result = session.run("SELECT pg_sleep(9)", statement_timeout_ms=30_000)

    assert result.ok is False
    assert "statement cancelled" in result.error.message
    assert "30 s" in result.error.message
    assert result.error.sqlstate == TIMEOUT_SQLSTATE
    assert result.error.position == 9
    assert result.error.line == 1


def test_a_timeout_below_the_floor_is_a_loud_caller_bug():
    session, _connection, _opened = session_with()
    with pytest.raises(ValueError) as excinfo:
        session.run("SELECT 1", statement_timeout_ms=MIN_STATEMENT_TIMEOUT_MS - 1)
    assert "unlimited" in str(excinfo.value)


def test_a_negative_row_cap_is_a_loud_caller_bug():
    session, _connection, _opened = session_with()
    with pytest.raises(ValueError):
        session.run("SELECT 1", max_rows=-1)


# -- the three lifecycle edges ---------------------------------------------


@pytest.mark.parametrize(
    "reason", [DISCARD_TAB_CLOSED, DISCARD_WINDOW_CLOSED], ids=["tab", "window"]
)
def test_closing_rolls_back_closes_the_connection_and_names_the_reason(reason):
    """Edges 1 and 2: an uncommitted run may be discarded, but never silently,
    and the connection may never be left open on production."""
    session, connection, _opened = session_with()
    session.run("DELETE FROM t")

    outcome = session.close(reason)

    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert connection.closed == 1
    assert session.is_open is False
    assert outcome.discarded is True
    assert outcome.reason == reason
    assert reason in transaction_message(outcome)
    assert "Rolled back" in transaction_message(outcome)


def test_close_still_closes_the_connection_when_the_rollback_itself_fails():
    """The leak this method exists to prevent. A failing rollback must not
    become a held connection, and it must not be reported as a clean discard."""
    session, connection, _opened = session_with()
    connection.rollback_raises = Boom("ERROR: cannot roll back")
    session.run("DELETE FROM t")

    outcome = session.close(DISCARD_WINDOW_CLOSED)

    assert connection.closed == 1
    assert session.is_open is False
    assert outcome.error is not None
    assert "cannot roll back" in transaction_message(outcome)


def test_connection_loss_during_a_statement_is_terminal_stated_and_leaks_nothing():
    """Edge 3. The server has already rolled the transaction back, so the only
    honest sentence is *nothing was committed* — and the dead handle is closed
    rather than kept."""
    lost = QualityConnectionLost("server closed the connection unexpectedly")
    session, connection, _opened = session_with({"UPDATE b SET y = 2": lost})
    session.run("UPDATE a SET x = 1")

    result = session.run("UPDATE b SET y = 2")

    assert result.ok is False
    assert CONNECTION_LOST_TEXT in result.error.message
    assert "server closed the connection" in result.error.message
    assert session.is_lost is True
    assert session.is_open is False
    assert session.has_uncommitted_work is False
    assert connection.closed == 1
    assert connection.commits == 0


def test_a_lost_session_commits_nothing_and_runs_nothing_further():
    lost = QualityConnectionLost("gone")
    session, connection, _opened = session_with({"X": lost})
    session.run("X")

    refused = session.commit()
    assert refused.committed is False
    assert transaction_message(refused) == CONNECTION_LOST_TEXT
    assert connection.commits == 0

    later = session.run("SELECT 1")
    assert later.ok is False
    assert CONNECTION_LOST_TEXT in later.error.message


def test_a_commit_that_loses_the_connection_reports_the_loss_not_a_success():
    session, connection, _opened = session_with()
    connection.commit_raises = QualityConnectionLost("gone mid-commit")
    session.run("DELETE FROM t")

    outcome = session.commit()

    assert outcome.committed is False
    assert session.is_lost is True
    assert session.is_open is False
    assert connection.closed == 1


def test_a_rejected_commit_leaves_a_rollbackable_transaction():
    session, connection, _opened = session_with()
    connection.commit_raises = Boom("ERROR: deferred constraint violated")
    session.run("INSERT INTO t VALUES (1)")

    outcome = session.commit()

    assert outcome.committed is False
    assert "deferred constraint" in str(outcome.error)
    assert session.transaction_aborted is True
    assert session.is_lost is False
    assert session.close(DISCARD_TAB_CLOSED).discarded is True
    assert connection.closed == 1


def test_closing_a_session_that_never_ran_anything_is_a_no_op():
    session, connection, opened = session_with()
    outcome = session.close(DISCARD_TAB_CLOSED)
    assert opened == []
    assert connection.closed == 0
    assert outcome.committed is False


# -- the shared result shape ----------------------------------------------


def test_rows_are_capped_and_truncation_is_a_fact_not_a_guess():
    raw = RawResult(columns=("id",), rows=((1,), (2,), (3,)), affected=3, status="SELECT 3")
    result = result_from_raw("SELECT id FROM t", raw, max_rows=2, elapsed_ms=1.0)
    assert result.outcome is QueryOutcome.ROWS
    assert result.rows == ((1,), (2,))
    assert result.truncated is True
    assert result.max_rows == 2


def test_a_result_exactly_on_the_cap_is_not_truncated():
    raw = RawResult(columns=("id",), rows=((1,), (2,)), affected=2, status="SELECT 2")
    result = result_from_raw("SELECT id FROM t", raw, max_rows=2, elapsed_ms=1.0)
    assert result.truncated is False


def test_a_no_result_set_statement_keeps_the_drivers_own_status():
    raw = RawResult(columns=None, rows=(), affected=3, status="UPDATE 3")
    result = result_from_raw("UPDATE t SET x = 1", raw, max_rows=10, elapsed_ms=1.0)
    assert result.outcome is QueryOutcome.NO_ROWS
    assert result.status == "UPDATE 3"
    assert result.affected == 3


# -- the panel-facing seam -------------------------------------------------


def test_run_quality_query_has_the_sandbox_call_shape():
    """One `SqlConsolePanel` serves both consoles, so the executor seams must be
    call-compatible: `(session, sql, *, max_rows, statement_timeout_ms)`."""
    session, connection, _opened = session_with()
    result = run_quality_query(
        session, "SELECT 1", max_rows=7, statement_timeout_ms=DEFAULT_STATEMENT_TIMEOUT_MS
    )
    assert result.ok is True
    assert connection.executed == [("SELECT 1", 7, DEFAULT_STATEMENT_TIMEOUT_MS)]


def test_run_quality_query_refuses_anything_that_is_not_a_quality_session():
    """The mirror of `run_sandbox_query`'s `SandboxSession` check: bare
    `ConnectionParams` must not be a thing this function accepts, or the
    held-transaction guarantee stops being structural."""
    with pytest.raises(TypeError) as excinfo:
        run_quality_query(PARAMS, "SELECT 1")
    assert "QualitySession" in str(excinfo.value)


def test_a_connection_that_cannot_be_opened_is_an_error_result_not_a_raise():
    def connector(_params):
        raise Boom("connection refused")

    session = QualitySession(PARAMS, connector=connector)
    result = session.run("SELECT 1")
    assert result.ok is False
    assert "connection refused" in str(result.error)
    assert session.is_lost is False  # retriable: no transaction was ever held


def test_transaction_message_states_the_count_and_never_invents_one():
    assert "2 statements" in transaction_message(
        TransactionOutcome("committed", statements=2)
    )
    assert "1 statement " in transaction_message(
        TransactionOutcome("committed", statements=1)
    )
