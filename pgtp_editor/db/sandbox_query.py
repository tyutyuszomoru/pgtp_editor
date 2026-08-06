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

# pgtp_editor/db/sandbox_query.py
"""Running one ad-hoc SQL statement **against the sandbox** and modelling what
came back (§18.5 D2's disposable sandbox; §29's "seeing a function's results"
open question).

**Why this is allowed to execute at all.** §18.3 states twice, as a hard
non-goal, that DDL is never executed silently, and §18.5's Apply is
confirm-gated naming the database. Ad-hoc execution is a deliberate exception
justified by exactly one property: the sandbox is **disposable and resettable**
(`SandboxSession.reset()` drops and re-provisions every app schema). That
justification only holds while the statement genuinely cannot reach anywhere
else, so this module is **sandbox-targeted by construction**:
`run_sandbox_query` takes a `SandboxSession` -- never a bare
`ConnectionParams` -- and reads `session.params` itself. A `SandboxSession` is
creatable only through `db/sandbox.py::open_sandbox`, the single ownership gate
(name prefix **and** the `pg_database` marker comment). There is deliberately
no free function here that runs SQL against an arbitrary connection, exactly as
`install_plpgsql_check(session)` has none.

**A truncated result is a wrong answer.** An unbounded `SELECT *` against a
"with data" clone of a production table would freeze or OOM the app, so every
run is capped (`DEFAULT_MAX_ROWS`, overridable per call). The cap is enforced
by fetching one row *past* it, so `QueryResult.truncated` is a fact rather than
a guess, and the panel says so out loud -- this project treats a silently
short result set as the worst failure class.

**Three outcomes, never conflated** (`QueryOutcome`): a statement that returned
rows, a statement that returned none (DML/DDL, carrying the driver's own
`statusmessage` and affected-row count), and an error carrying **the database's
own message**, which is the useful part. Exceptions are never swallowed into an
empty grid: an error is an error.

Qt-free, and like the rest of `db/`, opens no connection except through the
injectable `runner` seam -- the whole test suite runs with psycopg absent.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .config import ConnectionParams
from .sandbox import SandboxSession

#: How many rows one ad-hoc run may bring back before it is cut off. Chosen to
#: be comfortably renderable in a `QTableWidget` (a grid this size builds in
#: well under a frame) while still being more rows than anyone reads by eye;
#: anyone who needs more should add their own `LIMIT`/`WHERE`, which is also
#: the only honest way to say *which* rows they want.
DEFAULT_MAX_ROWS = 1000


class QueryOutcome(str, Enum):
    """Which of the three genuinely different things happened. Kept as an
    explicit tag rather than being inferred from "are there rows?", because
    `SELECT` returning zero rows and `UPDATE` returning no result set are
    different answers and must never render the same way."""

    #: The statement returned a result set (possibly of zero rows).
    ROWS = "rows"
    #: The statement completed and returned no result set (DML/DDL).
    NO_ROWS = "no_rows"
    #: The statement failed; `QueryResult.error` carries the server's message.
    ERROR = "error"


@dataclass(frozen=True)
class RawResult:
    """What a `QueryRunner` hands back -- the driver's raw answer, before any
    capping or timing. Deliberately dumb: the runner's whole job is the wire,
    and every decision about truncation, timing and presentation is made in
    `run_sandbox_query` where it can be tested without a database.

    `columns` is None exactly when the statement produced no result set
    (psycopg leaves `cursor.description` None for DML/DDL) -- that is the
    single signal separating `ROWS` from `NO_ROWS`, and it is the driver's, not
    a guess made by pattern-matching the SQL text.

    `rows` may contain **one row more** than the caller's cap; that extra row
    is how truncation is detected and is dropped before it reaches a
    `QueryResult`.
    """

    columns: tuple[str, ...] | None
    rows: Sequence[Sequence[Any]] = ()
    #: `cursor.rowcount` -- rows affected by a DML statement, or -1/None when
    #: the driver does not know.
    affected: int | None = None
    #: `cursor.statusmessage` (e.g. `"UPDATE 3"`, `"CREATE FUNCTION"`), shown
    #: verbatim for the no-rows case rather than being re-worded here.
    status: str = ""


class QueryRunner(Protocol):
    """The execution seam, sibling of `db/introspect.py::Runner` and
    `db/sandbox.py::SandboxExecutor`. One call, one connection, one statement.

    `max_rows` is passed down rather than applied afterwards so a real
    implementation can `fetchmany` instead of dragging a million rows across
    the wire first and discarding them.
    """

    def __call__(
        self, params: ConnectionParams, sql: str, *, max_rows: int
    ) -> RawResult:
        ...


def _psycopg_runner(
    params: ConnectionParams, sql: str, *, max_rows: int
) -> RawResult:
    """The real `QueryRunner`. Lazily imports psycopg exactly like
    `db/introspect.py::run_queries` and `db/sandbox.py`'s executors do, so
    importing this module never requires the driver.

    Fetches `max_rows + 1` rows: the extra one never reaches the UI, it only
    proves the result set was longer than the cap. Commits, because an ad-hoc
    statement may legitimately be DML against the (disposable) sandbox and
    leaving it in a rolled-back limbo would be the surprising behaviour;
    a failure rolls back and re-raises, so nothing lands half-applied.
    """
    import psycopg  # noqa: PLC0415 -- lazy on purpose (see module docstring)

    connection = psycopg.connect(
        host=params.host or None,
        port=params.port or None,
        dbname=params.database or None,
        user=params.user or None,
        password=params.password or None,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            description = cursor.description
            if description is None:
                result = RawResult(
                    columns=None,
                    rows=(),
                    affected=cursor.rowcount,
                    status=cursor.statusmessage or "",
                )
            else:
                result = RawResult(
                    columns=tuple(str(column[0]) for column in description),
                    rows=cursor.fetchmany(max_rows + 1),
                    affected=cursor.rowcount,
                    status=cursor.statusmessage or "",
                )
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


#: The default, real `QueryRunner` -- module-level so callers can default to it
#: the way `probe`/`open_sandbox` default to `run_queries`/the real executor.
DEFAULT_QUERY_RUNNER: QueryRunner = _psycopg_runner


@dataclass(frozen=True)
class QueryResult:
    """One ad-hoc statement's complete answer -- rows, or no rows, or an
    error. **Pure data**: nothing here touches a database, and a panel can be
    driven entirely from hand-built instances.

    Never construct an "empty result" to stand in for a failure: use
    `QueryResult.failed`, so `outcome is QueryOutcome.ERROR` and `error` carry
    the truth. `sql` is kept so a results surface can label what it is showing
    without the caller having to pair the two up again.
    """

    outcome: QueryOutcome
    sql: str = ""
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    #: True when the server had more rows than `max_rows` and this result is a
    #: prefix. Always surfaced -- a silently short answer is a wrong answer.
    truncated: bool = False
    #: The cap that was in force, so the notice can name it.
    max_rows: int = DEFAULT_MAX_ROWS
    #: Rows affected for a `NO_ROWS` statement (`cursor.rowcount`), or None.
    affected: int | None = None
    #: The driver's own status line (e.g. `"UPDATE 3"`), never re-worded.
    status: str = ""
    #: The database's own error message, verbatim. Set iff `outcome is ERROR`.
    error: str | None = None
    elapsed_ms: float = 0.0

    @classmethod
    def failed(
        cls,
        sql: str,
        error: str,
        *,
        elapsed_ms: float = 0.0,
        max_rows: int = DEFAULT_MAX_ROWS,
    ) -> QueryResult:
        """The error case, spelled out so no caller has to remember to set
        both `outcome` and `error` consistently."""
        return cls(
            outcome=QueryOutcome.ERROR,
            sql=sql,
            error=error,
            elapsed_ms=elapsed_ms,
            max_rows=max_rows,
        )

    @property
    def ok(self) -> bool:
        """Whether the statement ran. False only for `QueryOutcome.ERROR`."""
        return self.outcome is not QueryOutcome.ERROR

    @property
    def row_count(self) -> int:
        """How many rows this result actually carries -- **what is shown**, not
        what the server had. When `truncated`, the server had more; that is
        what `truncated` is for and why this is never quietly reported as the
        total."""
        return len(self.rows)

    @property
    def returns_rows(self) -> bool:
        """Whether the statement produced a result set at all -- the DML/DDL
        distinction, taken from the driver rather than from the SQL text."""
        return self.outcome is QueryOutcome.ROWS


def run_sandbox_query(
    session: SandboxSession,
    sql: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    runner: QueryRunner = DEFAULT_QUERY_RUNNER,
    clock: Callable[[], float] = time.perf_counter,
) -> QueryResult:
    """Run one ad-hoc statement against `session`'s sandbox and model the
    answer. **Never raises** -- every failure becomes a `QueryOutcome.ERROR`
    result carrying the database's own message, mirroring `probe`'s
    never-raises contract, so a UI host has exactly one thing to render.

    **Sandbox-targeted by construction.** The first parameter is a
    `SandboxSession`, whose existence already means `open_sandbox` accepted the
    database as app-owned; the connection params are read off it and cannot be
    supplied separately. There is no target/production-database variant of this
    function, deliberately (§18.3's never-execute-silently non-goal is untouched
    for every database that is not the disposable sandbox).

    Blocking -- call it through `ui/sandbox_controller.py`'s `_run_async` seam
    (or any other off-GUI-thread runner), never on the GUI thread.
    """
    if max_rows < 0:
        raise ValueError(f"max_rows must not be negative, got {max_rows!r}")
    # Read *outside* the never-raises block on purpose: the never-raises
    # contract covers the database, not the caller. Handing this function
    # something that is not a `SandboxSession` (a bare `ConnectionParams`, say)
    # is a programming error that must be loud, never a tidy "error result"
    # that reads as "the server said no".
    params = _sandbox_params(session)

    started = clock()
    try:
        raw = runner(params, sql, max_rows=max_rows)
    except Exception as exc:  # noqa: BLE001 -- the DB's message IS the result
        return QueryResult.failed(
            sql,
            _error_message(exc),
            elapsed_ms=(clock() - started) * 1000.0,
            max_rows=max_rows,
        )
    elapsed_ms = (clock() - started) * 1000.0

    if raw.columns is None:
        return QueryResult(
            outcome=QueryOutcome.NO_ROWS,
            sql=sql,
            affected=raw.affected,
            status=raw.status,
            max_rows=max_rows,
            elapsed_ms=elapsed_ms,
        )

    fetched = [tuple(row) for row in raw.rows]
    truncated = len(fetched) > max_rows
    return QueryResult(
        outcome=QueryOutcome.ROWS,
        sql=sql,
        columns=tuple(raw.columns),
        rows=tuple(fetched[:max_rows]),
        truncated=truncated,
        max_rows=max_rows,
        affected=raw.affected,
        status=raw.status,
        elapsed_ms=elapsed_ms,
    )


def _sandbox_params(session: SandboxSession) -> ConnectionParams:
    """`session.params`, with a message naming the safety property when the
    caller passed something else. The `isinstance` check is the enforcement
    point for "sandbox-targeted by construction": a `SandboxSession` exists
    only because `open_sandbox` accepted the database as app-owned, so
    accepting any other object here would quietly reopen the production door.
    """
    if not isinstance(session, SandboxSession):
        raise TypeError(
            "run_sandbox_query runs ad-hoc SQL and therefore accepts only a "
            "SandboxSession (which db/sandbox.py::open_sandbox has already "
            f"verified is an app-owned, disposable sandbox), not a "
            f"{type(session).__name__}"
        )
    return session.params


def _error_message(exc: BaseException) -> str:
    """The database's own words where there are any -- psycopg's exception
    `str()` is the server's `ERROR: …` line, which is the whole reason to show
    an error at all. Falls back to the class name so an exception with an empty
    message never renders as a blank "error"."""
    return str(exc).strip() or exc.__class__.__name__


def status_line(result: QueryResult) -> str:
    """The one-line human summary of `result` -- **pure**, so the exact
    sentences are testable without a widget and any other surface (a status
    bar, a log) can reuse them verbatim instead of inventing a second wording.

    Three shapes, one per outcome: the error message; the driver's status plus
    affected count for a no-result-set statement; the row count plus, when it
    applies, an explicit truncation notice naming the cap.
    """
    if result.outcome is QueryOutcome.ERROR:
        return f"Error: {result.error}"

    elapsed = f"{result.elapsed_ms:.0f} ms"
    if result.outcome is QueryOutcome.NO_ROWS:
        head = result.status or "Statement completed"
        if result.affected is not None and result.affected >= 0:
            noun = "row" if result.affected == 1 else "rows"
            head = f"{head} — {result.affected} {noun} affected"
        return f"{head} — no result set — {elapsed}"

    noun = "row" if result.row_count == 1 else "rows"
    head = f"{result.row_count} {noun}"
    if result.truncated:
        head = (
            f"{head} — TRUNCATED at the {result.max_rows}-row limit; "
            "there are more rows. Add a LIMIT or WHERE to see the rest"
        )
    return f"{head} — {elapsed}"
