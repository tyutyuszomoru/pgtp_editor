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

# pgtp_editor/db/quality_query.py
"""Ad-hoc read/write SQL against the **quality (production) database**, run
inside a transaction that stays open until the user commits it (§18.5 D4b,
`FQ-260811020328`; commit model settled by `DEC-260811023646`).

**Why this module exists at all, stated where the door is.** §18.5 D4's
sandbox lane is *sandbox-targeted by construction* -- `run_sandbox_query`'s
first parameter is a `SandboxSession` and there is deliberately no free
function there that runs SQL against a bare `ConnectionParams`. That guarantee
is untouched: this is a **separate module and a fourth connection-opening
seam** (§18.5's "exactly three seams" invariant is amended to four *by name*,
which is the whole difference between a ruling and an erosion), authorized by
the owner's two rulings recorded in §18.5 D4b -- full read/write, always
available whenever a quality connection with a password exists. Nothing here
widens the sandbox function's signature, because a single function accepting
either a session or bare params is exactly how a sandbox gesture ends up
pointed at production.

**The commit model is the engineering, and it is NOT the sandbox's**
(`DEC-260811023646`). The sandbox console commits **per statement** (each
`SandboxExecutor.fetch` opens its own connection and commits it). Against
quality that would import the behaviour this project exists to replace, on the
one surface where it does the most damage. So here:

1. every statement of a submission runs on **one held-open connection** inside
   **one transaction**;
2. the user reads the results while the transaction is still **uncommitted**;
3. **only an explicit commit gesture makes it durable** (`QualitySession.commit`),
   and `discard` throws it away.

`db/apply.py::apply_ddl(..., commit=False)` is the closest existing shape -- one
transaction, per-statement attribution, rolled back on the way out -- but it
**runs and rolls back within one call**, so it cannot hold a transaction open
between the run and a later commit gesture. That held-open connection is
accepted new surface, and its three edges are a **requirement**, not an open
question:

* **tab close** with an uncommitted run: the console asks first, and a
  confirmed close calls `close(DISCARD_TAB_CLOSED)` -- rollback, then close the
  connection -- and says so. A declined close keeps the tab and the transaction.
* **window close** with an uncommitted run: same question at the window level;
  proceeding calls `close(DISCARD_WINDOW_CLOSED)`. The connection is closed on
  every path out, including when the rollback itself fails, so quitting can
  never leak a session holding locks on production.
* **connection loss**: any `QualityConnectionLost` (or a commit that fails)
  marks the session `lost`, closes the handle and reports
  `CONNECTION_LOST_TEXT` -- the server has already rolled the transaction back,
  so the honest sentence is *nothing was committed*, said out loud rather than
  left for the user to infer from a silent grid.

**Nothing is reused by copying.** `DEFAULT_MAX_ROWS`,
`DEFAULT_STATEMENT_TIMEOUT_MS`, `MIN_STATEMENT_TIMEOUT_MS`, `TIMEOUT_SQLSTATE`,
`timeout_error`, `QueryError`, `QueryResult`, `QueryOutcome` and `RawResult` are
imported from `db/sandbox_query.py`, which made them module-level *for this
module* -- so the timeout sentence, the row cap and the rendered shape are one
implementation and every surface keeps rendering one thing. The statement
timeout applies here **more** strongly than in the sandbox, not less: a
forgotten statement against production holds locks.

Qt-free, and it opens a connection only through the injected `QualityConnector`
seam -- the whole test suite runs with psycopg absent and never opens a
connection.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .config import ConnectionParams
from .sandbox_query import (
    DEFAULT_MAX_ROWS,
    DEFAULT_STATEMENT_TIMEOUT_MS,
    MIN_STATEMENT_TIMEOUT_MS,
    TIMEOUT_SQLSTATE,
    QueryError,
    QueryOutcome,
    QueryResult,
    RawResult,
    timeout_error,
)

__all__ = [
    "ABORTED_TEXT",
    "COMMITTED",
    "CONNECTION_LOST_TEXT",
    "DEFAULT_QUALITY_CONNECTOR",
    "DISCARDED",
    "DISCARD_CONNECTION_LOST",
    "DISCARD_ROLLBACK_GESTURE",
    "DISCARD_TAB_CLOSED",
    "DISCARD_TARGET_GONE",
    "DISCARD_WINDOW_CLOSED",
    "NOTHING_PENDING_TEXT",
    "REFUSED",
    "QualityConnection",
    "QualityConnectionLost",
    "QualityConnector",
    "QualitySession",
    "TransactionOutcome",
    "result_from_raw",
    "run_quality_query",
    "transaction_message",
]


class QualityConnectionLost(Exception):
    """The held connection is **gone**, not the statement rejected.

    Raised by a `QualityConnection` implementation (and by the real psycopg one
    on `OperationalError`/`InterfaceError`) so `QualitySession` can tell the two
    apart. The distinction is the whole point: a rejected statement leaves a
    live, aborted transaction the user may still roll back, whereas a lost
    connection means the server already rolled it back and there is nothing left
    to commit -- and the user must be told which of the two happened.
    """


class QualityConnection(Protocol):
    """One **held-open** connection to quality, in a transaction.

    Deliberately not `db/sandbox.py::SandboxExecutor`'s shape: that protocol is
    *one call, one connection, one statement, committed*, which is precisely the
    model `DEC-260811023646` rejected for production. Here `execute` may be
    called many times on the same object and **commits nothing**; `commit` and
    `rollback` are separate gestures the user drives.

    `execute` raises on a rejected statement (the database's own exception, which
    `QualitySession` turns into a `QueryResult`) and raises
    `QualityConnectionLost` when the connection itself died.
    """

    def execute(
        self, sql: str, *, max_rows: int, statement_timeout_ms: int
    ) -> RawResult:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...

    def close(self) -> None:
        ...


#: How a session gets its connection. Injected everywhere in tests, so no test
#: ever opens one (§30).
QualityConnector = Callable[[ConnectionParams], QualityConnection]


class _PsycopgQualityConnection:
    """The real `QualityConnection`. Lazily imports psycopg exactly like
    `db/introspect.py::run_queries`, `db/apply.py::_psycopg_runner` and
    `db/sandbox.py`'s executors do, so importing this module never requires the
    driver.

    **One connection, one transaction, N statements, committed only when asked.**
    psycopg 3 is not in autocommit, so the first `execute` opens a transaction
    that stays open across calls -- which is exactly the property `apply_ddl`
    cannot offer, because it commits or rolls back before returning.

    The timeout goes through **`set_config(..., true)`, not `SET LOCAL
    statement_timeout = %s`**, for `db/sandbox.py::_RealSandboxExecutor.fetch`'s
    stated reason: `SET` is a utility statement and takes no bind parameters, so
    the `SET LOCAL` spelling could only be written by interpolating a number
    from a spin box into SQL. `true` IS `SET LOCAL` scope -- transaction-local,
    discarded at commit -- which here means it covers the whole held
    transaction and is re-asserted before every statement, so changing the spin
    box between two Runs cannot leave an old value in force.
    """

    def __init__(self, params: ConnectionParams) -> None:
        import psycopg  # noqa: PLC0415 -- lazy on purpose (see the docstring)

        self._psycopg = psycopg
        self._connection = psycopg.connect(
            host=params.host or None,
            port=params.port or None,
            dbname=params.database or None,
            user=params.user or None,
            password=params.password or None,
        )

    def _lost(self, exc: BaseException) -> bool:
        psycopg = self._psycopg
        return isinstance(
            exc, (psycopg.OperationalError, psycopg.InterfaceError)
        )

    def execute(
        self, sql: str, *, max_rows: int, statement_timeout_ms: int
    ) -> RawResult:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    (
                        f"{max(int(statement_timeout_ms), MIN_STATEMENT_TIMEOUT_MS)}ms",
                    ),
                )
                cursor.execute(sql)
                description = cursor.description
                if description is None:
                    # DML/DDL: psycopg 3 RAISES on fetch* here, so the guard is
                    # required rather than defensive.
                    return RawResult(
                        columns=None,
                        rows=(),
                        affected=cursor.rowcount,
                        status=cursor.statusmessage or "",
                    )
                return RawResult(
                    columns=tuple(str(column[0]) for column in description),
                    # One row PAST the cap, so `truncated` is a fact and not a
                    # guess -- the sandbox lane's rule, unchanged.
                    rows=cursor.fetchmany(max_rows + 1),
                    affected=cursor.rowcount,
                    status=cursor.statusmessage or "",
                )
        except Exception as exc:  # noqa: BLE001 -- classified, then re-raised
            if self._lost(exc):
                raise QualityConnectionLost(str(exc).strip()) from exc
            # NOT rolled back here: the transaction is the user's, and an
            # aborted transaction they can still discard deliberately is more
            # honest than one this layer silently threw away.
            raise

    def commit(self) -> None:
        try:
            self._connection.commit()
        except Exception as exc:  # noqa: BLE001 -- classified, then re-raised
            if self._lost(exc):
                raise QualityConnectionLost(str(exc).strip()) from exc
            raise

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _open_psycopg_connection(params: ConnectionParams) -> QualityConnection:
    """The default `QualityConnector`. Module-level so callers default to it the
    way `apply_ddl` defaults to `DEFAULT_APPLY_RUNNER`."""
    return _PsycopgQualityConnection(params)


DEFAULT_QUALITY_CONNECTOR: QualityConnector = _open_psycopg_connection

#: The three things a transaction gesture can have done. An explicit tag rather
#: than a bool pair, because "committed", "discarded" and "refused, and here is
#: why" are three different sentences and must never render the same way.
COMMITTED = "committed"
DISCARDED = "discarded"
REFUSED = "refused"

#: Why an uncommitted transaction was thrown away. Every discard names one --
#: `DEC-260811023646`'s surviving invariant is that an uncommitted run being
#: discarded is fine, being discarded **without saying so** is not.
DISCARD_ROLLBACK_GESTURE = "you rolled it back"
DISCARD_TAB_CLOSED = "the Quality SQL Console tab was closed"
DISCARD_WINDOW_CLOSED = "the window was closed"
DISCARD_CONNECTION_LOST = "the connection to the quality database was lost"
DISCARD_TARGET_GONE = "the quality connection is no longer configured"

#: What a commit/discard is told when there is nothing outstanding. Said rather
#: than silently ignored, so a button that appears to do nothing has a reason.
NOTHING_PENDING_TEXT = (
    "Nothing to commit — no statement has run against the quality database "
    "since the last commit or rollback."
)

#: What a commit is refused with while the transaction is aborted. PostgreSQL
#: will not accept anything but a rollback once a statement in a transaction
#: failed, so offering to "commit" would be offering a lie.
ABORTED_TEXT = (
    "This run cannot be committed — a statement failed, so the quality "
    "database has aborted the whole transaction. Roll it back; nothing it did "
    "will be kept."
)

#: The connection-loss sentence. It states the durability fact first, because
#: that is the only thing the user needs in that second.
CONNECTION_LOST_TEXT = (
    "The connection to the quality database was lost, so the server rolled the "
    "run back: NOTHING was committed. Re-open the console to start a new "
    "transaction."
)


@dataclass(frozen=True)
class TransactionOutcome:
    """What one commit/discard gesture did -- **pure data**, so every sentence
    the console shows is assertable without a widget or a database."""

    action: str
    #: How many statements the transaction held. Named in the message, because
    #: "committed" with no number does not tell the user what became durable.
    statements: int = 0
    #: Why it was discarded (one of the `DISCARD_*` constants), or "".
    reason: str = ""
    #: The database's own failure, when the gesture itself failed.
    error: QueryError | None = None

    @property
    def committed(self) -> bool:
        return self.action == COMMITTED

    @property
    def discarded(self) -> bool:
        return self.action == DISCARDED


def transaction_message(outcome: TransactionOutcome) -> str:
    """One `TransactionOutcome` as one line -- pure, so the wording lives in one
    place and both the status strip and the activity journal say the same thing.
    """
    noun = "statement" if outcome.statements == 1 else "statements"
    if outcome.committed:
        return (
            f"COMMITTED — {outcome.statements} {noun} are now durable in the "
            "quality database."
        )
    if outcome.discarded:
        verb = "was" if outcome.statements == 1 else "were"
        head = (
            f"Rolled back — {outcome.statements} {noun} {verb} discarded "
            f"({outcome.reason})."
            if outcome.statements
            else f"Rolled back ({outcome.reason})."
        )
        if outcome.error is not None:
            # The rollback itself failed. The connection is closed regardless,
            # so nothing was committed either way -- but saying only "rolled
            # back" would assert something this layer did not observe.
            return f"{head} The rollback itself reported: {outcome.error}"
        return head
    return str(outcome.error) if outcome.error is not None else NOTHING_PENDING_TEXT


def result_from_raw(
    sql: str, raw: RawResult, *, max_rows: int, elapsed_ms: float
) -> QueryResult:
    """One executed statement's raw rows as the shared `QueryResult` -- the same
    three-outcome mapping the sandbox lane applies, including `truncated` read
    from *one row past the cap* rather than guessed.

    Its own named function because D4b needs it at a different place in the
    lifecycle than `run_sandbox_query` does (there the mapping sits after a
    self-contained call; here it sits inside a session that outlives the
    statement). Pure, so it is assertable without a connection.
    """
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
    return QueryResult(
        outcome=QueryOutcome.ROWS,
        sql=sql,
        columns=tuple(raw.columns),
        rows=tuple(fetched[:max_rows]),
        truncated=len(fetched) > max_rows,
        max_rows=max_rows,
        affected=raw.affected,
        status=raw.status,
        elapsed_ms=elapsed_ms,
    )


class QualitySession:
    """A held-open quality connection and the **uncommitted** transaction on it.

    The object the Quality SQL Console runs against, and the reason D4b needed
    new surface at all: every other seam in `db/` opens and closes a connection
    within one call, so none of them can let a user *look at* what a statement
    did before deciding whether it becomes durable.

    Lifecycle, and every state is reportable rather than inferred:

    * **cold** -- no connection yet. The connection is opened lazily, on the
      first statement, so merely opening the console tab connects to nothing.
    * **pending** (`has_uncommitted_work`) -- at least one statement has run and
      neither `commit` nor `discard` has happened. This is the state the three
      lifecycle edges are about.
    * **aborted** (`transaction_aborted`) -- a statement failed, so PostgreSQL
      will accept only a rollback. `commit` is refused with `ABORTED_TEXT`.
    * **lost** (`is_lost`) -- the connection died. The handle is already closed,
      nothing was committed, and the session is finished: a new one must be made.

    **Never raises for anything the database did** -- a failed statement comes
    back as a `QueryOutcome.ERROR` `QueryResult`, a failed commit as a
    `TransactionOutcome` carrying the error -- so the console has exactly one
    thing to render. Caller bugs (a negative `max_rows`, a timeout below the
    floor) still raise, exactly as in the sandbox lane: the never-raises
    contract covers the database, not the caller.

    Blocking. Call it through the console's `run_async` seam, never on the GUI
    thread.
    """

    def __init__(
        self,
        params: ConnectionParams,
        *,
        connector: QualityConnector = DEFAULT_QUALITY_CONNECTOR,
    ) -> None:
        self._params = params
        self._connector = connector
        self._connection: QualityConnection | None = None
        self._statements = 0
        self._aborted = False
        self._lost = False
        self._lost_detail = ""

    # --- state --------------------------------------------------------------

    @property
    def params(self) -> ConnectionParams:
        """The quality connection this session runs against. Read by the console
        only to NAME the database in its confirmations -- never to open a second
        connection."""
        return self._params

    @property
    def has_uncommitted_work(self) -> bool:
        """Whether statements have run that are not durable yet. The predicate
        the commit gesture, the tab-close question and the window-close question
        are all gated on -- one reading, so they cannot disagree."""
        return self._statements > 0 and not self._lost

    @property
    def statements_pending(self) -> int:
        """How many statements the open transaction holds."""
        return 0 if self._lost else self._statements

    @property
    def transaction_aborted(self) -> bool:
        """Whether a statement failed and only a rollback is legal now."""
        return self._aborted and not self._lost

    @property
    def is_lost(self) -> bool:
        """Whether the connection died. Terminal -- a lost session runs nothing
        and commits nothing."""
        return self._lost

    @property
    def is_open(self) -> bool:
        """Whether a connection is currently held. False before the first
        statement and after any `close`/loss -- which is what "does this leak?"
        is asserted on."""
        return self._connection is not None

    # --- running ------------------------------------------------------------

    def run(
        self,
        sql: str,
        *,
        max_rows: int = DEFAULT_MAX_ROWS,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
        clock: Callable[[], float] = time.perf_counter,
    ) -> QueryResult:
        """Run one statement on the held transaction and model the answer.
        **Commits nothing** -- that is `commit`'s job and the user's gesture."""
        if max_rows < 0:
            raise ValueError(f"max_rows must not be negative, got {max_rows!r}")
        if statement_timeout_ms < MIN_STATEMENT_TIMEOUT_MS:
            # A caller bug, and therefore loud -- the sandbox lane's rule
            # verbatim. There is deliberately no value meaning "unlimited", and
            # against production that absence matters more, not less: an
            # unbounded statement here holds locks on a live database.
            raise ValueError(
                f"statement_timeout_ms must be at least {MIN_STATEMENT_TIMEOUT_MS} "
                "(§18.5 D4/D4b: the timeout is mandatory and there is "
                f"deliberately no unlimited setting), got {statement_timeout_ms!r}"
            )
        if self._lost:
            return QueryResult.failed(
                sql, QueryError(message=CONNECTION_LOST_TEXT), max_rows=max_rows
            )

        started = clock()
        try:
            connection = self._ensure_connection()
        except QualityConnectionLost as exc:
            return self._on_connection_lost(sql, exc, max_rows)
        except Exception as exc:  # noqa: BLE001 -- the DB's message IS the result
            # Could not connect at all. Not a loss of a held transaction (there
            # was none), so the session stays usable and the next Run retries.
            return QueryResult.failed(
                sql,
                QueryError.from_exception(exc, sql),
                elapsed_ms=(clock() - started) * 1000.0,
                max_rows=max_rows,
            )

        try:
            raw = connection.execute(
                sql, max_rows=max_rows, statement_timeout_ms=statement_timeout_ms
            )
        except QualityConnectionLost as exc:
            return self._on_connection_lost(sql, exc, max_rows)
        except Exception as exc:  # noqa: BLE001 -- the DB's message IS the result
            error = QueryError.from_exception(exc, sql)
            if error.sqlstate == TIMEOUT_SQLSTATE:
                # Reworded HERE, where the timeout actually in force is known,
                # through `sandbox_query.timeout_error` -- the one named helper,
                # called rather than copied, so both consoles say one sentence.
                error = timeout_error(error, statement_timeout_ms)
            # The statement failed inside the transaction, so PostgreSQL has
            # aborted the whole thing. Recorded, not hidden: the console offers
            # only Roll Back from here.
            self._aborted = True
            return QueryResult.failed(
                sql,
                error,
                elapsed_ms=(clock() - started) * 1000.0,
                max_rows=max_rows,
            )

        self._statements += 1
        return result_from_raw(
            sql, raw, max_rows=max_rows, elapsed_ms=(clock() - started) * 1000.0
        )

    # --- the point of no return, and its opposite ---------------------------

    def commit(self) -> TransactionOutcome:
        """Make the open transaction durable. **The point of no return** --
        `DEC-260811025132` rests on this being a separate, deliberate gesture,
        which is why it carries no keyboard shortcut anywhere in the UI."""
        if self._lost:
            return TransactionOutcome(
                REFUSED, error=QueryError(message=CONNECTION_LOST_TEXT)
            )
        if self._aborted:
            return TransactionOutcome(
                REFUSED,
                statements=self._statements,
                error=QueryError(message=ABORTED_TEXT),
            )
        if self._statements == 0 or self._connection is None:
            return TransactionOutcome(
                REFUSED, error=QueryError(message=NOTHING_PENDING_TEXT)
            )
        statements = self._statements
        try:
            self._connection.commit()
        except QualityConnectionLost as exc:
            self._mark_lost(exc)
            return TransactionOutcome(
                REFUSED, statements=statements,
                error=QueryError(message=CONNECTION_LOST_TEXT),
            )
        except Exception as exc:  # noqa: BLE001 -- the DB's message IS the result
            # The commit was rejected. The transaction is aborted now, so the
            # only legal next gesture is a rollback -- said, not guessed at.
            self._aborted = True
            return TransactionOutcome(
                REFUSED,
                statements=statements,
                error=QueryError.from_exception(exc),
            )
        self._statements = 0
        self._aborted = False
        return TransactionOutcome(COMMITTED, statements=statements)

    def discard(self, reason: str = DISCARD_ROLLBACK_GESTURE) -> TransactionOutcome:
        """Roll the open transaction back, **keeping the connection** for the
        next Run. `reason` is mandatory in practice: a discard the user is not
        told about is the one thing `DEC-260811023646` forbids."""
        return self._roll_back(reason, close=False)

    def close(self, reason: str = DISCARD_TAB_CLOSED) -> TransactionOutcome:
        """Roll back anything outstanding and **close the connection**.

        The tab-close, window-close and target-gone edges all land here. The
        connection is closed on every path, including when the rollback itself
        raises: a held session on production is exactly what must not outlive
        the surface that owns it.
        """
        return self._roll_back(reason, close=True)

    # --- internals ----------------------------------------------------------

    def _roll_back(self, reason: str, *, close: bool) -> TransactionOutcome:
        connection = self._connection
        statements = self._statements
        if connection is None:
            self._statements = 0
            self._aborted = False
            if self._lost:
                return TransactionOutcome(
                    DISCARDED, statements=0, reason=DISCARD_CONNECTION_LOST
                )
            return TransactionOutcome(
                REFUSED, error=QueryError(message=NOTHING_PENDING_TEXT)
            )
        error: QueryError | None = None
        try:
            connection.rollback()
        except Exception as exc:  # noqa: BLE001 -- reported, never raised out
            error = QueryError.from_exception(exc)
        finally:
            if close:
                try:
                    connection.close()
                finally:
                    self._connection = None
        self._statements = 0
        self._aborted = False
        return TransactionOutcome(
            DISCARDED, statements=statements, reason=reason, error=error
        )

    def _ensure_connection(self) -> QualityConnection:
        if self._connection is None:
            self._connection = self._connector(self._params)
        return self._connection

    def _mark_lost(self, exc: BaseException) -> None:
        """Terminal state: the transaction is gone (the server rolled it back)
        and the handle is closed so nothing leaks."""
        self._lost = True
        self._lost_detail = str(exc).strip()
        self._statements = 0
        self._aborted = False
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 -- a dead connection may refuse
                pass

    def _on_connection_lost(
        self, sql: str, exc: BaseException, max_rows: int
    ) -> QueryResult:
        self._mark_lost(exc)
        detail = str(exc).strip()
        message = CONNECTION_LOST_TEXT
        if detail:
            message = f"{CONNECTION_LOST_TEXT} The server said: {detail}"
        return QueryResult.failed(
            sql, QueryError(message=message), max_rows=max_rows
        )


def run_quality_query(
    session: QualitySession,
    sql: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    clock: Callable[[], float] = time.perf_counter,
) -> QueryResult:
    """Run one ad-hoc statement against quality, inside `session`'s **open,
    uncommitted** transaction. Never raises for anything the database did.

    **This signature diverges from §18.5 D4b's sketched
    `run_quality_query(params, sql, …)` on purpose, and the spec's own decision
    entry is why**: `DEC-260811023646` requires the connection to be held open
    *between* the run and a later commit gesture, and a function taking bare
    `ConnectionParams` can only open and close one within the call -- the exact
    limitation the decision names in `apply_ddl`. The `ConnectionParams` live on
    the session instead, which is also the only thing that keeps "which database
    can this reach?" answerable by one object.

    It is the panel-facing seam with **`run_sandbox_query`'s call shape**
    (`(session, sql, *, max_rows, statement_timeout_ms)`), which is what lets
    one `SqlConsolePanel` class serve both consoles with an injected executor
    and no `if quality:` anywhere in the UI.
    """
    if not isinstance(session, QualitySession):
        raise TypeError(
            "run_quality_query runs read/write SQL against the quality "
            "database and therefore accepts only a QualitySession, which owns "
            "the held-open transaction the commit gesture later commits, not a "
            f"{type(session).__name__}"
        )
    return session.run(
        sql,
        max_rows=max_rows,
        statement_timeout_ms=statement_timeout_ms,
        clock=clock,
    )
