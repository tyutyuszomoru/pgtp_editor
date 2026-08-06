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

# pgtp_editor/db/apply.py
"""The validation ladder's **write seam** — one statement list, one
transaction, per-statement attribution (§18.5 D3a's *"Where the run happens"*).

**Why this module exists at all: tier attribution.** D3's ladder must run as
*one* call — `SET plpgsql.extra_*` → the DDL → the
`plpgsql_check_function_tb` SELECT share one session and one transaction, since
the `SET`s are session-scoped and the check must see the object the DDL just
created. Run that way, a naive "it raised" report is actively misleading: a
failure in the *check* statement would be shown to the user as *"your DDL is
broken"*. So the outcome carries **`ApplyOutcome.statement_index`** — which
statement in the list failed — and the caller (`db/ddl_check.py`) maps that
index onto a tier. A failure with no index is a failure that never reached a
statement at all (a connection failure), which is again a different fact.

**One transaction, and the caller chooses whether it commits.** `commit=True`
is Apply-to-Sandbox / Apply-to-Target (`apply_and_check`); `commit=False` is
D3's `probe_check`, which runs the same ladder and rolls it back so nothing is
left behind. That is a parameter rather than two functions because the two
differ in exactly one boolean and must otherwise be *identical* — a probe that
diverged from the real apply would validate something the user is not about to
run.

**Never raises for a database problem, always raises for a programming one.**
Mirroring `db/sandbox_query.py::run_sandbox_query` and `db/sandbox.py::probe`:
the database saying no is a *result* (`ApplyOutcome.ok is False`, carrying the
server's own `sqlstate`/`message`/`detail`/`hint`), while being handed a
non-statement list or a negative index is a bug that must be loud.

**Field names are deliberately `QueryError`'s and `CheckFinding`'s**
(`sqlstate`, `message`, `detail`, `hint`, `position`, `line`) so a failed
query, a failed apply and a validation finding render through **one** formatting
helper (§18.5 D4's alignment rule). `line` is derived from `position` exactly as
D4 specifies — `position` is a 1-based character offset into the statement we
sent, and that statement *is* the buffer, so
`statement.count("\\n", 0, position - 1) + 1` is exact. No `map_lineno` is
involved: there is no `prosrc`/`pg_get_functiondef` offset here (that offset is
tier 3's problem and stays in `db/ddl_check.py`).

**Not a sandbox-only module, and that is deliberate** — unlike
`db/sandbox_query.py`, whose whole safety argument is that ad-hoc SQL can reach
nothing but a disposable database. This is the seam Apply-to-**Target** is wired
to (`ui/ddl_object_editor.py`'s `apply_to_target`), so it accepts a plain
`ConnectionParams` as well as anything carrying `.params` (a `SandboxSession`).
The gating that makes an Apply-to-Target legitimate is §18.5's four
preconditions plus the database-naming confirmation, and it lives in the panel;
this module executes a reviewed statement list and reports what happened.

Qt-free, and like the rest of `db/`, opens no connection except through the
injectable `runner` seam — the whole test suite runs with psycopg absent and
never touches a real database.

**The notice channel is part of the seam, because tier 1 has no other one.**
`SET plpgsql.extra_warnings = 'all'` returns **no rows at all**: PostgreSQL
delivers its findings as asynchronous `WARNING` diagnostics during
`CREATE FUNCTION`. A row-fetching runner therefore yields nothing from tier 1,
forever. So the psycopg runner registers a connection notice handler and
normalizes each diagnostic into a **psycopg-free** frozen `Notice`, collected on
`ApplyOutcome.notices`; nothing downstream of this module ever touches a driver
object. `notices_captured` is carried **separately** from "the list is empty",
because §18.5 D3 requires tier 1 to report `unavailable` — never `passed` —
where the channel is not available, and a runner that cannot capture notices is
indistinguishable from a clean routine unless it says so.

`db/ddl_check.py::apply_and_check`/`probe_check` are this module's callers:
they compose the ladder's statement list and read the tiers back off
`statement_index`, `notices` and the last statement's `rows`.
`ui/ddl_object_editor.py`'s `apply_to_target` seam is still unbound.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import ConnectionParams


@dataclass(frozen=True)
class StatementResult:
    """What one statement in the list did — kept per statement, not merged,
    because the ladder's whole point is knowing *which* statement spoke.

    `columns is None` exactly when the statement produced no result set (the
    driver's `cursor.description`, never guessed from the SQL text) — the same
    signal `db/sandbox_query.py::RawResult` uses. `rows` therefore carries the
    check SELECT's output: the ladder's caller reads it off the last statement
    rather than running the SELECT a second time in its own transaction, which
    would no longer see the uncommitted DDL.
    """

    index: int
    statement: str = ""
    columns: tuple[str, ...] | None = None
    rows: tuple[tuple[Any, ...], ...] = ()
    #: `cursor.rowcount`, or None when the driver does not know.
    affected: int | None = None
    #: `cursor.statusmessage` (e.g. `"CREATE FUNCTION"`), shown verbatim.
    status: str = ""

    @property
    def returns_rows(self) -> bool:
        """Whether this statement produced a result set at all."""
        return self.columns is not None


@dataclass(frozen=True)
class Notice:
    """One asynchronous server diagnostic (`NOTICE`/`WARNING`), normalized
    **away from psycopg** (§18.5 D3's tier-1 channel).

    Field names are the shared failure vocabulary `ApplyOutcome`,
    `db/sandbox_query.py::QueryError` and `db/ddl_check.py::CheckFinding` all
    use, so one formatting helper renders all of them.

    `context` is the load-bearing field, not decoration: tier 1's line numbers
    exist nowhere else. PostgreSQL emits `CONTEXT: compilation of PL/pgSQL
    function "f" near line 3` alongside each extra-warning, and
    `db/ddl_check.py` regexes the line out of it and maps it through
    `map_lineno`. A `Notice` with an empty `context` is therefore reported with
    no line at all rather than a guessed one.
    """

    message: str = ""
    severity: str = ""
    detail: str = ""
    hint: str = ""
    context: str = ""
    sqlstate: str = ""


def normalize_notice(diagnostic: Any) -> Notice:
    """One psycopg `Diagnostic` (or any duck-typed stand-in) as a `Notice`.

    Read entirely by `getattr` so this module still imports no psycopg and a
    test can hand in a plain object. psycopg 3 names the fields
    `severity`/`severity_nonlocalized`/`message_primary`/`message_detail`/
    `message_hint`/`context`/`sqlstate`; `severity_nonlocalized` is preferred
    because a server running under a non-English `lc_messages` localizes
    `severity`, and anything matching on `"WARNING"` would then silently miss.
    """
    return Notice(
        message=_attr(diagnostic, "message_primary"),
        severity=(
            _attr(diagnostic, "severity_nonlocalized") or _attr(diagnostic, "severity")
        ),
        detail=_attr(diagnostic, "message_detail"),
        hint=_attr(diagnostic, "message_hint"),
        context=_attr(diagnostic, "context"),
        sqlstate=_attr(diagnostic, "sqlstate"),
    )


def _attr(obj: Any, name: str) -> str:
    """One attribute of a driver diagnostic as a string, never raising --
    reading a diagnostic must not be able to fail the run that produced it."""
    try:
        return str(getattr(obj, name, "") or "")
    except Exception:  # noqa: BLE001 -- diagnostics must never mask the result
        return ""


@dataclass(frozen=True)
class RunOutcome:
    """What an `ApplyRunner` hands back: the per-statement results **and** the
    notices the connection collected while they ran.

    A runner may instead return a bare sequence of `StatementResult` -- that is
    the "no notice channel" answer, and `apply_ddl` records it as
    `notices_captured=False` so tier 1 reports `unavailable` rather than
    `passed`. `notices_captured` is a field rather than `bool(notices)` for
    exactly that reason: *"there were no warnings"* and *"nobody was listening"*
    are different facts, and conflating them is the never-report-clean-when-
    unchecked violation §18.5 D3 forbids.
    """

    results: tuple[StatementResult, ...] = ()
    notices: tuple[Notice, ...] = ()
    notices_captured: bool = True


class StatementFailure(Exception):
    """Raised by an `ApplyRunner` when a *specific* statement failed.

    The index has to come from the runner: the runner owns the loop (because it
    owns the transaction), so it is the only place that knows how far the list
    got. `apply_ddl` turns this into `ApplyOutcome.statement_index` — which is
    the entire reason this exception type exists instead of letting the driver's
    exception through, where the position in the list would be lost and the
    check call's failure would be blamed on the user's DDL.
    """

    def __init__(
        self,
        statement_index: int,
        statement: str,
        cause: BaseException | None = None,
        *,
        notices: Sequence[Notice] = (),
        notices_captured: bool = False,
        results: Sequence[StatementResult] = (),
    ) -> None:
        super().__init__(
            f"statement {statement_index} failed: {_error_message(cause) if cause else 'unknown'}"
        )
        self.statement_index = statement_index
        self.statement = statement
        self.cause = cause
        #: Notices collected *before* the failure. Carried on the failure path
        #: on purpose: tier 1's warnings are emitted while `CREATE FUNCTION`
        #: compiles, so a DDL statement can produce real lint findings and
        #: *then* fail -- dropping them would hide the warnings that explain
        #: the failure.
        self.notices = tuple(notices)
        self.notices_captured = notices_captured
        #: The statements that did complete, so tier attribution can still say
        #: which tiers ran before the list stopped.
        self.results = tuple(results)


class ApplyRunner(Protocol):
    """The execution seam — sibling of `db/introspect.py::Runner`,
    `db/sandbox.py::SandboxExecutor` and `db/sandbox_query.py::QueryRunner`.

    **One call, one connection, one transaction, N statements**, in order, with
    the result sets kept. Implementations MUST:

    * run every statement on the *same* connection and inside a *single*
      transaction (the ladder's `SET`s are session-scoped and the check must see
      the DDL's uncommitted effect);
    * commit at the end iff `commit`, and roll back otherwise — a `False` here
      is D3's `probe_check` and must leave nothing behind;
    * raise `StatementFailure(index, statement, cause)` when a statement fails,
      after rolling back, so the failure keeps its position in the list.

    Anything else raised (a connection failure, say) is reported by `apply_ddl`
    with `statement_index is None`, which is the honest reading: no statement
    of the caller's was ever judged.

    **Return `RunOutcome` if you can capture notices, a bare list if you
    cannot.** Tier 1 exists only on the notice channel, so a runner that
    returns a plain list of results is recorded as *"no notice channel"* and
    tier 1 reports `unavailable`. Returning `RunOutcome(results, ())` instead
    asserts the opposite -- that the channel was live and the server said
    nothing -- which is what lets tier 1 report `passed`.
    """

    def __call__(
        self,
        params: ConnectionParams,
        statements: Sequence[str],
        *,
        commit: bool,
    ) -> RunOutcome | list[StatementResult]:
        ...


def _psycopg_runner(
    params: ConnectionParams,
    statements: Sequence[str],
    *,
    commit: bool,
) -> RunOutcome:
    """The real `ApplyRunner`. Lazily imports psycopg exactly like
    `db/introspect.py::run_queries` and `db/sandbox.py`'s executors do, so
    importing this module never requires the driver to be installed.

    One connection, one implicit transaction, statements in order, **with the
    notice handler registered before the first statement runs** -- psycopg 3's
    `Connection.add_notice_handler(cb)` calls `cb(Diagnostic)` for every
    asynchronous `NOTICE`/`WARNING` the server sends, which is the only place
    tier 1's findings exist. A failure is rolled back and re-raised as
    `StatementFailure` carrying the index *and the notices collected so far*; a
    `commit=False` run is rolled back on the way out even on success, which is
    what makes `probe_check` a probe.
    """
    import psycopg  # noqa: PLC0415 -- lazy on purpose (see module docstring)

    connection = psycopg.connect(
        host=params.host or None,
        port=params.port or None,
        dbname=params.database or None,
        user=params.user or None,
        password=params.password or None,
    )
    results: list[StatementResult] = []
    notices: list[Notice] = []
    connection.add_notice_handler(lambda diagnostic: notices.append(
        normalize_notice(diagnostic)
    ))
    try:
        try:
            with connection.cursor() as cursor:
                for index, statement in enumerate(statements):
                    try:
                        cursor.execute(statement)
                    except Exception as exc:
                        raise StatementFailure(
                            index,
                            statement,
                            exc,
                            notices=notices,
                            notices_captured=True,
                            results=results,
                        ) from exc
                    description = cursor.description
                    results.append(
                        StatementResult(
                            index=index,
                            statement=statement,
                            columns=(
                                None
                                if description is None
                                else tuple(str(column[0]) for column in description)
                            ),
                            # psycopg 3 RAISES `ProgrammingError` on fetchall()
                            # after a statement that produced no result set, so
                            # the `description is None` guard is a hard
                            # requirement of the mixed statement list, not a
                            # tidy-up (§18.5's write-seam correction).
                            rows=(
                                ()
                                if description is None
                                else tuple(tuple(row) for row in cursor.fetchall())
                            ),
                            affected=cursor.rowcount,
                            status=cursor.statusmessage or "",
                        )
                    )
        except Exception:
            connection.rollback()
            raise
        if commit:
            connection.commit()
        else:
            connection.rollback()
        return RunOutcome(
            results=tuple(results), notices=tuple(notices), notices_captured=True
        )
    finally:
        connection.close()


#: The default, real `ApplyRunner` — module-level so callers can default to it
#: the way `probe`/`open_sandbox`/`run_sandbox_query` default to their seams.
DEFAULT_APPLY_RUNNER: ApplyRunner = _psycopg_runner


@dataclass(frozen=True)
class ApplyOutcome:
    """What one `apply_ddl` call did. **Pure data** — nothing here touches a
    database, so a panel or a ladder can be driven entirely from hand-built
    instances.

    Read duck-typed by `ui/ddl_object_editor.py::_result_lines`, which renders
    `ok is False` as `"failed at statement {statement_index}: {sqlstate}
    {message}"` — hence `ok`, `statement_index`, `sqlstate` and `message` are
    the four names that may never be renamed without changing that panel.

    `statement_index` is `None` in exactly two situations, which must not be
    confused with "statement 0 failed": a successful run, and a failure that
    never reached a statement (e.g. the connection could not be opened).
    """

    ok: bool
    #: Which statement failed, 0-based, or None (see the class docstring). The
    #: tier attribution the ladder depends on: the caller knows which index it
    #: put the DDL at and which index is the check call, so a failure in the
    #: check is never reported as a broken DDL.
    statement_index: int | None = None
    #: The failing statement's text, verbatim, so a report can quote what was
    #: actually sent rather than what the caller believes it sent.
    statement: str = ""
    #: Whether the transaction was committed. False for a `probe_check`-style
    #: run AND for every failure — stated as a fact rather than inferred from
    #: `ok`, because "it worked but was rolled back on purpose" and "it worked
    #: and is now live" are the two things a user most needs told apart.
    committed: bool = False
    #: Per-statement results, in order, for the statements that ran. The
    #: ladder reads its check SELECT's rows from the last entry.
    results: tuple[StatementResult, ...] = ()
    #: --- The tier-1 channel (§18.5 D3) -------------------------------------
    #: Every asynchronous diagnostic the server sent while the statements ran,
    #: in order, normalized away from psycopg. This is tier 1's ONLY output:
    #: `SET plpgsql.extra_warnings = 'all'` returns no rows.
    notices: tuple[Notice, ...] = ()
    #: Whether a notice channel was actually listening. **False means tier 1
    #: reports `unavailable`, never `passed`** -- an empty `notices` on a runner
    #: that cannot capture them says nothing about the routine (§18.5 D3's
    #: "where that channel is not available, tier 1 must report `unavailable`").
    notices_captured: bool = False
    #: --- The shared failure vocabulary (`QueryError`/`CheckFinding`) --------
    sqlstate: str = ""
    #: The database's own message, verbatim — the useful part of a failure.
    message: str = ""
    detail: str = ""
    hint: str = ""
    #: 1-based character offset into `statement`, as the server reported it.
    position: int | None = None
    #: The line within `statement` that `position` falls on, or None when the
    #: server gave no position. Never a guess — an unknown line is rendered
    #: with no line at all (§18.5 D3).
    line: int | None = None
    elapsed_ms: float = 0.0

    @classmethod
    def succeeded(
        cls,
        results: Sequence[StatementResult],
        *,
        committed: bool,
        elapsed_ms: float = 0.0,
        notices: Sequence[Notice] = (),
        notices_captured: bool = False,
    ) -> ApplyOutcome:
        """The success case, spelled out so no caller has to remember that a
        successful outcome must leave `statement_index` None."""
        return cls(
            ok=True,
            committed=committed,
            results=tuple(results),
            notices=tuple(notices),
            notices_captured=notices_captured,
            elapsed_ms=elapsed_ms,
        )

    @classmethod
    def failed(
        cls,
        message: str,
        *,
        statement_index: int | None = None,
        statement: str = "",
        sqlstate: str = "",
        detail: str = "",
        hint: str = "",
        position: int | None = None,
        results: Sequence[StatementResult] = (),
        elapsed_ms: float = 0.0,
        notices: Sequence[Notice] = (),
        notices_captured: bool = False,
    ) -> ApplyOutcome:
        """The failure case, with `line` derived from `position` in the one
        place that derivation is allowed to happen."""
        return cls(
            ok=False,
            statement_index=statement_index,
            statement=statement,
            committed=False,
            results=tuple(results),
            notices=tuple(notices),
            notices_captured=notices_captured,
            sqlstate=sqlstate,
            message=message,
            detail=detail,
            hint=hint,
            position=position,
            line=line_of_position(statement, position),
            elapsed_ms=elapsed_ms,
        )

    @property
    def rows(self) -> tuple[tuple[Any, ...], ...]:
        """The rows of the last statement that returned a result set — the
        ladder's `plpgsql_check_function_tb` output. Empty when no statement
        returned rows, which is never confused with "the check found nothing":
        that distinction is the caller's `ok`/`statement_index` reading, and
        `db/ddl_check.py` refuses to report an unrun check as clean."""
        for result in reversed(self.results):
            if result.returns_rows:
                return result.rows
        return ()

    @property
    def statuses(self) -> tuple[str, ...]:
        """Each executed statement's driver status line, in order, verbatim."""
        return tuple(result.status for result in self.results)

    def result_at(self, index: int | None) -> StatementResult | None:
        """The result of statement `index`, or None when that statement never
        ran. **The tier-attribution primitive**: the ladder knows which index it
        put each tier's statement at, so `result_at(check_index) is None`
        reads as *"the check never ran"* rather than *"the check found
        nothing"*. Matched by position in the list the caller passed, not by
        position in `results`, which is the same thing precisely because the
        runner stops at the first failure."""
        if index is None or index < 0:
            return None
        for result in self.results:
            if result.index == index:
                return result
        return None

    def reached(self, index: int | None) -> bool:
        """Whether statement `index` ran to completion. The honest reading of
        "did this tier happen at all?"."""
        return self.result_at(index) is not None


def line_of_position(statement: str, position: int | None) -> int | None:
    """The 1-based line of a 1-based character `position` within `statement`.

    §18.5 D4's exact rule, in one place so the SQL console, the apply path and
    tier 2 cannot drift apart: `position` indexes the text we sent, which *is*
    the buffer, so this is exact rather than mapped. `None` (and any position
    outside the statement) yields `None` — never a guessed line.
    """
    if position is None or position <= 0 or not statement:
        return None
    if position > len(statement) + 1:
        return None
    return statement.count("\n", 0, position - 1) + 1


@dataclass(frozen=True)
class ErrorDiagnostics:
    """A database failure's fields, in the **shared** vocabulary
    (`ApplyOutcome`, `db/sandbox_query.py::QueryError`,
    `db/ddl_check.py::CheckFinding`) -- so a failed apply, a failed ad-hoc query
    and a validation finding render through one helper (§18.5 D4's alignment
    rule)."""

    message: str = ""
    sqlstate: str = ""
    detail: str = ""
    hint: str = ""
    position: int | None = None
    line: int | None = None


def diagnose(exc: BaseException | None, statement: str = "") -> ErrorDiagnostics:
    """Pull the shared failure fields off a driver exception, **once**.

    The single place psycopg's `sqlstate`/`diag.*` layout is read (by `getattr`,
    so this module still imports no psycopg and a plain `RuntimeError` or a test
    double works). `line` comes from `line_of_position`, so the
    `position` → line rule has exactly one implementation for the write seam,
    the SQL console and tier 2 alike.
    """
    if exc is None:
        return ErrorDiagnostics()
    position = _position(exc)
    return ErrorDiagnostics(
        message=_error_message(exc),
        sqlstate=_sqlstate(exc),
        detail=_diag(exc, "message_detail"),
        hint=_diag(exc, "message_hint"),
        position=position,
        line=line_of_position(statement, position),
    )


def apply_ddl(
    target: Any,
    statements: Sequence[str],
    *,
    commit: bool = True,
    runner: ApplyRunner = DEFAULT_APPLY_RUNNER,
    clock: Callable[[], float] = time.perf_counter,
) -> ApplyOutcome:
    """Run `statements` as **one transaction** against `target` and report what
    happened, per statement (§18.5 D3a).

    `target` is a `ConnectionParams`, or anything carrying one as `.params` (a
    `db/sandbox.py::SandboxSession`) — the ladder hands its session straight in,
    Apply-to-Target hands in the target's params.

    `commit=False` runs the identical ladder and rolls it back (D3's
    `probe_check`); `committed` on the outcome states which happened rather than
    leaving the caller to infer it.

    **Never raises for a database problem.** Every database failure becomes
    `ok is False` with the server's own words and, when the runner could say so,
    the `statement_index` that failed. An empty statement list is a no-op
    success that opens no connection — refusing to connect in order to do
    nothing.

    Blocking — call it through `ui/sandbox_controller.py`'s off-GUI-thread seam,
    never on the GUI thread.
    """
    params = _target_params(target)
    prepared = _prepared_statements(statements)
    if not prepared:
        return ApplyOutcome.succeeded((), committed=False)

    started = clock()
    try:
        raw = runner(params, prepared, commit=commit)
    except StatementFailure as failure:
        cause = failure.cause
        statement = failure.statement or _at(prepared, failure.statement_index)
        fields = diagnose(cause if cause is not None else failure, statement)
        return ApplyOutcome.failed(
            fields.message,
            statement_index=failure.statement_index,
            statement=statement,
            sqlstate=fields.sqlstate,
            detail=fields.detail,
            hint=fields.hint,
            position=fields.position,
            results=failure.results,
            notices=failure.notices,
            notices_captured=failure.notices_captured,
            elapsed_ms=(clock() - started) * 1000.0,
        )
    except Exception as exc:  # noqa: BLE001 -- the DB's message IS the result
        # No index: nothing of the caller's was judged (a connection failure,
        # typically). Reported with statement_index None so no tier is blamed.
        fields = diagnose(exc)
        return ApplyOutcome.failed(
            fields.message,
            sqlstate=fields.sqlstate,
            detail=fields.detail,
            hint=fields.hint,
            elapsed_ms=(clock() - started) * 1000.0,
        )

    outcome = _run_outcome(raw)
    return ApplyOutcome.succeeded(
        outcome.results,
        committed=commit,
        notices=outcome.notices,
        notices_captured=outcome.notices_captured,
        elapsed_ms=(clock() - started) * 1000.0,
    )


def _run_outcome(raw: Any) -> RunOutcome:
    """A runner's return value as a `RunOutcome`.

    A bare sequence of `StatementResult` is accepted and recorded as
    `notices_captured=False` -- the honest reading of a runner with no notice
    channel, which makes tier 1 `unavailable` instead of falsely `passed`.
    """
    if isinstance(raw, RunOutcome):
        return raw
    return RunOutcome(results=tuple(raw or ()), notices=(), notices_captured=False)


def _prepared_statements(statements: Sequence[str]) -> list[str]:
    """`statements` as a list of non-blank strings, loudly rejecting anything
    that is not text. A non-string here (a tuple of params, a `None`) is a
    programming error: laundering it into an "error result" would read as *the
    server said no*, which is exactly the misattribution this module exists to
    prevent."""
    if isinstance(statements, str):
        raise TypeError(
            "apply_ddl takes a SEQUENCE of statements (the ladder is a list: "
            "the SET, the DDL, the check SELECT), not a single string -- pass "
            "[sql] if you really mean one statement"
        )
    prepared = []
    for index, statement in enumerate(statements):
        if not isinstance(statement, str):
            raise TypeError(
                f"statement {index} is a {type(statement).__name__}, not str"
            )
        if statement.strip():
            prepared.append(statement)
    return prepared


def _target_params(target: Any) -> ConnectionParams:
    """`target` itself when it is a `ConnectionParams`, else its `.params`.

    Deliberately permissive about *which* database, and deliberately strict
    about the type: this is the seam Apply-to-Target uses, so a sandbox-only
    check like `run_sandbox_query`'s would be wrong here — but silently
    accepting an object with no connection params would produce a
    "database failure" for what is a caller bug.
    """
    if isinstance(target, ConnectionParams):
        return target
    params = getattr(target, "params", None)
    if isinstance(params, ConnectionParams):
        return params
    raise TypeError(
        "apply_ddl needs a ConnectionParams, or an object carrying one as "
        f".params (e.g. a SandboxSession), not a {type(target).__name__}"
    )


def _at(statements: Sequence[str], index: int | None) -> str:
    """`statements[index]`, or `""` — used only to recover the failing text
    when a runner reported an index without the statement."""
    if index is None:
        return ""
    try:
        return statements[index]
    except (IndexError, TypeError):
        return ""


def _error_message(exc: BaseException) -> str:
    """The database's own words where there are any — psycopg's exception
    `str()` is the server's `ERROR: …` line, which is the whole reason to show
    an error at all. Falls back to the class name so an exception with an empty
    message never renders as a blank "error". Identical to
    `db/sandbox_query.py::_error_message`; kept as its own two lines rather than
    importing, so this module has no dependency on the ad-hoc-SQL feature."""
    return str(exc).strip() or exc.__class__.__name__


def _sqlstate(exc: BaseException | None) -> str:
    """psycopg's `Error.sqlstate` when present. Read by `getattr` so a
    hand-rolled test double, a non-psycopg driver and a plain `RuntimeError`
    all work — this module never imports psycopg."""
    return str(getattr(exc, "sqlstate", "") or "")


def _diag(exc: BaseException | None, attribute: str) -> str:
    """One field of psycopg's `Error.diag`, or `""`. `diag` access can itself
    raise for a non-server error, so it is guarded."""
    try:
        diag = getattr(exc, "diag", None)
        return str(getattr(diag, attribute, "") or "")
    except Exception:  # noqa: BLE001 -- diagnostics must never mask the error
        return ""


def _position(exc: BaseException | None) -> int | None:
    """psycopg's `diag.statement_position` as an int, or None. A non-numeric
    or absent value yields None, which renders as *no* line rather than line 1
    — a guessed line points at the wrong statement (§18.5 D3)."""
    raw = _diag(exc, "statement_position")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


__all__ = [
    "DEFAULT_APPLY_RUNNER",
    "ApplyOutcome",
    "ApplyRunner",
    "ErrorDiagnostics",
    "Notice",
    "RunOutcome",
    "StatementFailure",
    "StatementResult",
    "apply_ddl",
    "diagnose",
    "line_of_position",
    "normalize_notice",
]
