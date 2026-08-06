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

**Unwired in this pass.** Nothing imports this module yet:
`db/ddl_check.py`'s tiers 0-2 still report `TIER_NOT_BUILT` and
`ui/ddl_object_editor.py`'s `apply_to_target` seam is still unbound. Rewiring
those callers is a separate, serial step.
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
    ) -> None:
        super().__init__(
            f"statement {statement_index} failed: {_error_message(cause) if cause else 'unknown'}"
        )
        self.statement_index = statement_index
        self.statement = statement
        self.cause = cause


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
    """

    def __call__(
        self,
        params: ConnectionParams,
        statements: Sequence[str],
        *,
        commit: bool,
    ) -> list[StatementResult]:
        ...


def _psycopg_runner(
    params: ConnectionParams,
    statements: Sequence[str],
    *,
    commit: bool,
) -> list[StatementResult]:
    """The real `ApplyRunner`. Lazily imports psycopg exactly like
    `db/introspect.py::run_queries` and `db/sandbox.py`'s executors do, so
    importing this module never requires the driver to be installed.

    One connection, one implicit transaction, statements in order. A failure is
    rolled back and re-raised as `StatementFailure` carrying the index; a
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
    try:
        try:
            with connection.cursor() as cursor:
                for index, statement in enumerate(statements):
                    try:
                        cursor.execute(statement)
                    except Exception as exc:
                        raise StatementFailure(index, statement, exc) from exc
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
        return results
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
    ) -> ApplyOutcome:
        """The success case, spelled out so no caller has to remember that a
        successful outcome must leave `statement_index` None."""
        return cls(
            ok=True,
            committed=committed,
            results=tuple(results),
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
    ) -> ApplyOutcome:
        """The failure case, with `line` derived from `position` in the one
        place that derivation is allowed to happen."""
        return cls(
            ok=False,
            statement_index=statement_index,
            statement=statement,
            committed=False,
            results=tuple(results),
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
        results = runner(params, prepared, commit=commit)
    except StatementFailure as failure:
        cause = failure.cause
        statement = failure.statement or _at(prepared, failure.statement_index)
        return ApplyOutcome.failed(
            _error_message(cause if cause is not None else failure),
            statement_index=failure.statement_index,
            statement=statement,
            sqlstate=_sqlstate(cause),
            detail=_diag(cause, "message_detail"),
            hint=_diag(cause, "message_hint"),
            position=_position(cause),
            elapsed_ms=(clock() - started) * 1000.0,
        )
    except Exception as exc:  # noqa: BLE001 -- the DB's message IS the result
        # No index: nothing of the caller's was judged (a connection failure,
        # typically). Reported with statement_index None so no tier is blamed.
        return ApplyOutcome.failed(
            _error_message(exc),
            sqlstate=_sqlstate(exc),
            detail=_diag(exc, "message_detail"),
            hint=_diag(exc, "message_hint"),
            elapsed_ms=(clock() - started) * 1000.0,
        )

    return ApplyOutcome.succeeded(
        list(results or ()),
        committed=commit,
        elapsed_ms=(clock() - started) * 1000.0,
    )


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
    "StatementFailure",
    "StatementResult",
    "apply_ddl",
    "line_of_position",
]
