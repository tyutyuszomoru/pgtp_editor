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

**And an unbounded run is a hung app.** The row cap bounds what comes *back*;
it does nothing about a statement that takes an hour to produce it. So every
run also carries a **mandatory** `statement_timeout_ms` (§18.5 D4's *primary*
control -- `DEFAULT_STATEMENT_TIMEOUT_MS`, floor `MIN_STATEMENT_TIMEOUT_MS`),
applied transaction-locally by the executor. There is no "unlimited" value; that
absence is the design rather than an omission. A statement the server cancels
comes back as an ordinary error result worded by `timeout_error`, never as a
hang and never as a bare driver string.

**Three outcomes, never conflated** (`QueryOutcome`): a statement that returned
rows, a statement that returned none (DML/DDL, carrying the driver's own
`statusmessage` and affected-row count), and an error carrying **the database's
own message**, which is the useful part. Exceptions are never swallowed into an
empty grid: an error is an error.

**It opens no connection of its own -- it goes through the sandbox lane's
seam.** §18.5's invariant 1 names exactly three connection-opening seams:
`db/introspect.py::run_queries` (read), `db/apply.py::apply_ddl` (DDL write) and
`db/sandbox.py::SandboxExecutor` (`execute`/`query`/`fetch`, the sandbox lane,
reachable only through an ownership-gated session). This module's runs are the
`fetch` half of that third seam. An earlier version of this file opened its own
psycopg connection, which was a **fourth** seam and directly contradicted
the argument above: the safety property is that ad-hoc SQL can reach nothing but
an app-owned sandbox, and a private connection put this module's connection
discipline outside the gate that guarantees it. The `runner=` parameter is still
here as the injection point, but it now *defaults to the session's own
executor* rather than to a private psycopg call.

Qt-free, and like the rest of `db/`, opens no connection except through that
seam -- the whole test suite runs with psycopg absent.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol

from .apply import diagnose
from .config import ConnectionParams
from .sandbox import (
    DEFAULT_STATEMENT_TIMEOUT_MS,
    MIN_STATEMENT_TIMEOUT_MS,
    FetchedRows,
    SandboxSession,
)

# `DEFAULT_STATEMENT_TIMEOUT_MS` / `MIN_STATEMENT_TIMEOUT_MS` are **re-exported
# here, not re-declared** (§18.5 D4). They live in `db/sandbox.py` beside the
# seam they parameterise -- this module imports `sandbox` and never the reverse,
# so declaring them here and importing them back into the executor would be an
# import cycle -- but the UI and D4b's quality lane read *policy* from this
# module, exactly as they do `DEFAULT_MAX_ROWS` and `RawResult`. One number, one
# place, reachable from both.

#: How many rows one ad-hoc run may bring back before it is cut off. Chosen to
#: be comfortably renderable in a `QTableWidget` (a grid this size builds in
#: well under a frame) while still being more rows than anyone reads by eye;
#: anyone who needs more should add their own `LIMIT`/`WHERE`, which is also
#: the only honest way to say *which* rows they want.
DEFAULT_MAX_ROWS = 1000

#: PostgreSQL's `query_canceled` sqlstate -- what a statement killed by
#: `statement_timeout` reports. Named once, here, so that recognising a timeout
#: never means regexing English prose out of a driver message.
TIMEOUT_SQLSTATE = "57014"


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


#: This module's historical name for `db/sandbox.py::FetchedRows`, kept because
#: it is what `QueryRunner` returns and what every test constructs. **One type,
#: not two**: it moved to `db/sandbox.py` when `SandboxExecutor.fetch` became
#: the seam that produces it, because a seam owns its own return type -- and two
#: near-identical raw-result records, one per module, is exactly the duplication
#: this project treats as drift.
RawResult = FetchedRows


class QueryRunner(Protocol):
    """The execution seam -- **`db/sandbox.py::SandboxExecutor.fetch`'s
    signature**, named here for the injection point.

    One call, one connection, one statement. `max_rows` is passed down rather
    than applied afterwards so a real implementation can `fetchmany` instead of
    dragging a million rows across the wire first and discarding them.

    **This is the third declaration of the same signature, and the one that is
    easy to forget** (the others are `SandboxExecutor.fetch`'s protocol and
    `_RealSandboxExecutor.fetch`). It is separate because it names the `runner=`
    injection point; leaving it narrower than the real executor breaks every
    injected path **at call time, not at import** -- the worst shape for a seam
    whose whole purpose is that tests never reach a server. When one of the
    three changes, all three change.

    There is deliberately **no module-level default implementation** any more:
    the default is the *session's* executor, read off the session inside
    `run_sandbox_query`. That is not a style change -- a module-level default
    would be a connection-opening function reachable without a session, which is
    the one thing this module's safety argument forbids.
    """

    def __call__(
        self,
        params: ConnectionParams,
        sql: str,
        *,
        max_rows: int,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> RawResult:
        ...


@dataclass(frozen=True)
class QueryError:
    """One failed statement's error, **structured** (§18.5 D4).

    **The field names are `db/apply.py::ApplyOutcome`'s and
    `db/ddl_check.py::CheckFinding`'s, deliberately** -- `sqlstate`, `message`,
    `detail`, `hint`, `position`, `line` -- so a failed query, a failed apply and
    a validation finding render identically through one formatting helper, the
    same pattern-extension discipline §18.4 set with `xsd_verify.Issue`. An
    unstructured `str` could not do that: `position`/`line` are what make an
    error *clickable*, and `sqlstate` is what lets a caller recognise a specific
    failure (D4's statement-timeout `57014`) without regexing English prose.

    `line` is derived from `position` by `db/apply.py::line_of_position` -- the
    one implementation of that rule. `position` is a character offset into the
    statement we sent, which **is** the buffer, so no `map_lineno` is involved:
    there is no `prosrc`/`pg_get_functiondef` offset here (§18.5 D4).

    **It also still behaves like the string it replaced** (`str()`, `in`, `len`,
    truthiness all read `message`), so every existing surface that treated
    `QueryResult.error` as the database's words keeps working and keeps showing
    the same sentence. That is compatibility with the *rendered* value, not a
    second representation: `message` is the single source of it.
    """

    message: str = ""
    sqlstate: str = ""
    detail: str = ""
    hint: str = ""
    #: 1-based character offset into the statement, as the server reported it.
    position: int | None = None
    #: The line of `position` within the statement, or None when the server gave
    #: no position -- never a guess (§18.5 D3's "render with no line at all").
    line: int | None = None

    @classmethod
    def from_exception(cls, exc: BaseException, statement: str = "") -> QueryError:
        """The database's own words plus its diagnostics, read through
        `db/apply.py::diagnose` so psycopg's `sqlstate`/`diag.*` layout has
        exactly one reader in the codebase."""
        fields = diagnose(exc, statement)
        return cls(
            message=fields.message,
            sqlstate=fields.sqlstate,
            detail=fields.detail,
            hint=fields.hint,
            position=fields.position,
            line=fields.line,
        )

    @classmethod
    def of(cls, error: QueryError | str) -> QueryError:
        """`error` as a `QueryError` -- itself, or a bare message promoted to
        one with no diagnostics. The promotion path exists for the failures that
        genuinely have none (a thread pool that died before the statement was
        ever sent), not as a way to keep passing strings around."""
        if isinstance(error, QueryError):
            return error
        return cls(message=str(error))

    # -- string compatibility (see the class docstring) ----------------------

    def __str__(self) -> str:
        return self.message

    def __contains__(self, needle: object) -> bool:
        return str(needle) in self.message

    def __len__(self) -> int:
        return len(self.message)

    def __bool__(self) -> bool:
        # An error object always IS an error, even with an empty message -- the
        # alternative would make a message-less failure read as "no error".
        return True


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
    #: The structured failure -- the database's own message plus its
    #: `sqlstate`/`detail`/`hint`/`position`/`line`. Set iff `outcome is ERROR`.
    error: QueryError | None = None
    elapsed_ms: float = 0.0

    @classmethod
    def failed(
        cls,
        sql: str,
        error: QueryError | str,
        *,
        elapsed_ms: float = 0.0,
        max_rows: int = DEFAULT_MAX_ROWS,
    ) -> QueryResult:
        """The error case, spelled out so no caller has to remember to set
        both `outcome` and `error` consistently. A bare message is promoted to a
        `QueryError` (see `QueryError.of`) so a caller with nothing but a
        sentence -- a seam that died before the statement was sent -- still
        produces the one shape every surface renders."""
        return cls(
            outcome=QueryOutcome.ERROR,
            sql=sql,
            error=QueryError.of(error),
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


def timeout_error(error: QueryError, statement_timeout_ms: int) -> QueryError:
    """`error` with §18.5 D4's timeout sentence in place of the driver's own
    words -- **`message` and nothing else**.

    `sqlstate`, `detail`, `hint`, `position` and `line` are preserved, because
    `error_text` already prefixes the sqlstate and a surface that lost
    `position` would lose the clickable line: a cancelled statement must stay as
    navigable as any other failure.

    **One named helper, at module level, deliberately** -- not inlined at the
    call site -- so §18.5 D4b's `run_quality_query` produces the identical
    sentence by calling this rather than by copying the wording.

    Honest caveat, worth knowing before trusting the sentence: `57014` is
    `query_canceled` generally, so a user-issued `pg_cancel_backend()` reports it
    too. This wording is therefore the app's best interpretation rather than a
    certainty. D4 asks for exactly this mapping, and a timeout is overwhelmingly
    the likelier cause in a console that sets one on every statement.
    """
    seconds = statement_timeout_ms / 1000
    return replace(
        error,
        message=(
            f"statement cancelled: exceeded the console's statement timeout of "
            f"{seconds:g} s — raise the timeout or narrow the query"
        ),
    )


def run_sandbox_query(
    session: SandboxSession,
    sql: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    runner: QueryRunner | None = None,
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

    **Every run is time-bounded, and there is no way to ask for one that is
    not.** `statement_timeout_ms` (§18.5 D4's *primary* control) is applied in
    the statement's own transaction by the executor; below
    `MIN_STATEMENT_TIMEOUT_MS` it raises `ValueError`, and no value means
    "unlimited". A statement the server cancels comes back as an ordinary
    `QueryOutcome.ERROR` result whose message is `timeout_error`'s sentence,
    with `sqlstate`/`position`/`line` intact -- never a hang, never a bare
    driver string.

    **The run goes through `session.executor.fetch`** -- the sandbox lane's
    seam -- unless a `runner` is injected. This module opens no connection
    itself: the executor is reached only through the ownership-gated session, so
    "which database can this reach?" is answered by the same object that proves
    the database is disposable.

    Blocking -- call it through `ui/sandbox_controller.py`'s `_run_async` seam
    (or any other off-GUI-thread runner), never on the GUI thread.
    """
    if max_rows < 0:
        raise ValueError(f"max_rows must not be negative, got {max_rows!r}")
    if statement_timeout_ms < MIN_STATEMENT_TIMEOUT_MS:
        # A caller bug, and therefore loud -- exactly like `max_rows` above and
        # the `_sandbox_params` TypeError below. The never-raises contract
        # covers *the database*, not the caller. There is deliberately no value
        # (0, -1, None) that means "unlimited": the absence of that option is
        # the half of D4's design that carries the safety.
        raise ValueError(
            f"statement_timeout_ms must be at least {MIN_STATEMENT_TIMEOUT_MS} "
            f"(§18.5 D4: the timeout is mandatory and there is deliberately no "
            f"unlimited setting), got {statement_timeout_ms!r}"
        )
    # Read *outside* the never-raises block on purpose: the never-raises
    # contract covers the database, not the caller. Handing this function
    # something that is not a `SandboxSession` (a bare `ConnectionParams`, say)
    # is a programming error that must be loud, never a tidy "error result"
    # that reads as "the server said no".
    params = _sandbox_params(session)
    fetch: QueryRunner = runner if runner is not None else session.executor.fetch

    started = clock()
    try:
        raw = fetch(
            params, sql, max_rows=max_rows, statement_timeout_ms=statement_timeout_ms
        )
    except Exception as exc:  # noqa: BLE001 -- the DB's message IS the result
        error = QueryError.from_exception(exc, sql)
        if error.sqlstate == TIMEOUT_SQLSTATE:
            # Reworded HERE, above the seam, because this is where the timeout
            # that was actually in force is known -- not in the executor (which
            # would put UI wording in the driver layer) and not in the panel
            # (which D4b would then have to copy).
            error = timeout_error(error, statement_timeout_ms)
        return QueryResult.failed(
            sql,
            error,
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


def error_text(error: QueryError | None) -> str:
    """One `QueryError` as one line: the server's message, then whichever of
    `sqlstate`/`line`/`hint` it actually has.

    **The shared renderer §18.5 D4 asks for**, living where the shared field
    names do. It reads its input duck-typed (`getattr`), so a
    `db/apply.py::ApplyOutcome` and a `db/ddl_check.py::CheckFinding` -- which
    carry the same names on purpose -- render through it verbatim rather than
    through a second, drifting copy of these sentences.
    """
    if error is None:
        return ""
    message = str(getattr(error, "message", "") or "").strip()
    sqlstate = str(getattr(error, "sqlstate", "") or "").strip()
    line = getattr(error, "line", None)
    hint = str(getattr(error, "hint", "") or "").strip()
    parts = [f"{sqlstate} {message}".strip() if sqlstate else message]
    if line:
        parts.append(f"line {line}")
    if hint:
        parts.append(f"hint: {hint}")
    return " — ".join(part for part in parts if part)


def status_line(result: QueryResult) -> str:
    """The one-line human summary of `result` -- **pure**, so the exact
    sentences are testable without a widget and any other surface (a status
    bar, a log) can reuse them verbatim instead of inventing a second wording.

    Three shapes, one per outcome: the error message; the driver's status plus
    affected count for a no-result-set statement; the row count plus, when it
    applies, an explicit truncation notice naming the cap.
    """
    if result.outcome is QueryOutcome.ERROR:
        return f"Error: {error_text(result.error)}"

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
