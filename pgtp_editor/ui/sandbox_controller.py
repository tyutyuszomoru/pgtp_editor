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

# pgtp_editor/ui/sandbox_controller.py
"""The sandbox lane's lifecycle host (§18.5 D2/D2a/D3a) -- who owns the one live
`SandboxSession` for the open project, and who runs the sandbox layer's
blocking calls off the GUI thread.

`db/sandbox.py` is complete and Qt-free: `open_sandbox` (the single ownership
gate), `create_sandbox_database`, `provision_sandbox`, `clone_data`,
`install_plpgsql_check(session)`, `SandboxSession.apply`/`applied`/`reset`,
`probe`/`SandboxCapabilities`, `install_gate`, `determine_project_tier`. What it
never had is a **holder**: nothing in `ui/` called `open_sandbox`, so no session
existed for **Apply to Sandbox** to apply to and §18.8's Sandbox1/Sandbox2
action buttons ("run data clone", "install plpgsql_check") had nothing to fire
at. This module is exactly that holder and nothing more -- **it duplicates none
of `db/sandbox.py`'s logic**; every decision (ownership, tier degradation, the
install gate's reason strings, which provisioning strategy a mode implies) is
delegated to the function in `db/` that already owns it.

**Off the GUI thread, through the established seam.** Every DB-touching
operation goes through `self._run_async`, a plain attribute set to
`ui/async_task.py::run_async` in `__init__` -- the same convention
`ConnectionSetupDialog`/`NewProjectDialog`/`ProjectSettingsDialog` use, and the
same one tests replace with a synchronous stand-in. Nothing here blocks the
event loop, and results come back on the GUI thread where the caller may touch
widgets.

**Never silently destroys data.** Provisioning, `reset()` and re-cloning all
drop and recreate schemas, and §18's whole posture is surface-don't-auto-resolve:
so the destructive operations are *named* (`DESTRUCTIVE_OPERATIONS`,
`destructive_warning`) and refuse to run unless the injected
`confirm_destructive(warning) -> bool` says yes. **This module pops no dialog**
-- the caller supplies that callable, and a controller constructed without one
simply refuses every destructive operation with a stated reason. Opening a
project never provisions, clones or resets as a side effect; each is an explicit
call.

**Failures are reported, never swallowed,** and in the vocabulary the `db/`
layer already established rather than a second set of strings:
`ProjectCapabilityStatus.degraded_reason` ("sandbox unreachable: …", "sandbox
unavailable: pg_dump not found on PATH", "no local sandbox configured for this
project"), `SandboxCapabilities.probe_error`, `install_gate`'s four exact reason
strings, and `ForeignDatabaseError`'s own message. Every operation ends in one
`SandboxOperationResult` carrying `ok` plus a human-readable `reason`.

**It is also the Check gesture's host (§18.5 D3a),** for the same reason: the
ladder needs the live session and a thread, and both live here. `run_check`
supplies them to `db/ddl_check.py::recheck` (an injected seam like every other
`db/` call) and reports the `CheckReport` on the ordinary
`SandboxOperationResult`/`operation_finished` path. `CHECK` is **not**
destructive and never reaches `confirm_destructive`; with no live session the
host should not offer the gesture at all (`can_check`), and a call that arrives
anyway is a stated refusal -- never an empty report, which would read as clean.

Qt-light on purpose: a `QObject` so wiring can connect to `session_changed` /
`operation_finished`, but it constructs headless, touches no widget, opens no
dialog, and needs no `QApplication` interaction beyond `QObject.__init__`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, Signal

from ..db.config import ConnectionParams
from ..db.ddl_check import recheck
from ..db.introspect import BaselineSnapshot, DatabaseSchema, snapshot_for_baseline
from ..db.sandbox import (
    SandboxCapabilities,
    SandboxMode,
    SandboxSession,
    clone_data,
    create_sandbox_database,
    determine_project_tier,
    install_gate,
    install_plpgsql_check,
    open_sandbox,
    probe,
    provision_sandbox,
)
from ..db.sandbox import (
    # The exact "CREATE EXTENSION requires superuser" sentence `install_gate`
    # returns. Imported rather than re-typed so there is ONE wording of this
    # reason in the app: `install_gate` only hands it out when the extension is
    # `installable`, but a non-superuser sandbox is a distinguishable failure at
    # *open* time too, and inventing a second sentence for it is exactly the
    # drift this reuse avoids.
    REASON_REQUIRES_SUPERUSER as REQUIRES_SUPERUSER_REASON,
)
from .async_task import run_async


class SandboxOperation(str, Enum):
    """Every operation this controller performs, as the tag on its result --
    so a caller can route one `operation_finished` signal by what finished."""

    OPEN = "open"
    PROVISION = "provision"
    CLONE_DATA = "clone_data"
    INSTALL_PLPGSQL_CHECK = "install_plpgsql_check"
    RESET = "reset"
    #: §18.5 D3a's Check gesture -- runs the validation ladder against the
    #: sandbox as it currently stands. **Read-only and deliberately absent from
    #: `DESTRUCTIVE_OPERATIONS`:** it applies nothing, drops nothing and must
    #: never reach `confirm_destructive` (D3a, "the ladder gestures join
    #: `SandboxOperation` as `CHECK` (non-destructive -- no
    #: `confirm_destructive` prompt)").
    CHECK = "check"


#: The operations that drop and recreate schemas (or overwrite the sandbox's
#: contents wholesale). Each is refused unless `confirm_destructive` approves it
#: -- §18.5 D2a's "refreshing means destroying and recreating the sandbox" is a
#: deliberate user act, never a side effect.
DESTRUCTIVE_OPERATIONS = frozenset(
    {SandboxOperation.PROVISION, SandboxOperation.CLONE_DATA, SandboxOperation.RESET}
)

#: What the caller's confirmation prompt should say, per destructive operation.
#: Text only -- this module never shows it.
_DESTRUCTIVE_WARNINGS = {
    SandboxOperation.PROVISION: (
        "Provisioning rebuilds the sandbox database's schemas from the target "
        "database. Anything already applied to the sandbox is lost."
    ),
    SandboxOperation.CLONE_DATA: (
        "Cloning drops and recreates the sandbox database's contents from the "
        "target database. Anything already applied to the sandbox is lost."
    ),
    SandboxOperation.RESET: (
        "Resetting drops every application schema in the sandbox database "
        "(DROP SCHEMA … CASCADE) and re-provisions it. Anything already applied "
        "to the sandbox is lost."
    ),
}

#: Used when the controller has never probed -- `determine_project_tier` reads
#: `probe_error` as "unreachable", which is the honest answer to "what are the
#: sandbox's capabilities?" before anyone has looked.
_NOT_PROBED = SandboxCapabilities(probe_error="the sandbox has not been probed yet")

#: One wording for "there is no sandbox session", used by every operation that
#: needs one.
_NO_SESSION_REASON = (
    "no sandbox session is open -- open or provision the project's sandbox first"
)

#: A `CHECK` was asked for with nothing to check. Cannot happen through the
#: intended wiring (the gesture starts from an open object tab), so it is
#: reported as a stated refusal rather than defended against with an assert --
#: the controller's rule is that no operation ever raises at its caller.
_NO_CHECK_REQUEST_REASON = (
    "nothing to check -- the Check gesture needs the object whose tab it was "
    "invoked from"
)


@dataclass(frozen=True)
class SandboxOperationResult:
    """The outcome of exactly one controller operation -- success or a stated,
    human-readable reason, never a swallowed exception.

    `reason` is empty only on a bare success; a successful operation may still
    carry an explanatory line (e.g. `install_gate`'s *"already installed."*).

    `report` is set **only** by `SandboxOperation.CHECK`, and carries the
    `db/ddl_check.py::CheckReport` the ladder produced (typed `object` for the
    same reason `operation_finished` is: this module reads it duck-typed and
    never widens `ddl_check`'s types). It is None whenever no report was
    produced -- a refused or crashed check -- so *"no report"* and *"a clean
    report"* stay different facts (D3a: a missing sandbox is never reported as
    a clean check).
    """

    operation: SandboxOperation
    ok: bool
    reason: str = ""
    capabilities: SandboxCapabilities | None = None
    report: object | None = None


class SandboxController(QObject):
    """Owns at most one `SandboxSession` for the currently-open project.

    Constructor kwargs (every `db/sandbox.py` entry point is an injected seam,
    matching that module's own `runner`/`which`/`run`/`executor` style, so tests
    never touch a real PostgreSQL):

    ``confirm_destructive``
        ``(warning: str) -> bool``. Asked before every operation in
        `DESTRUCTIVE_OPERATIONS`. **None (the default) means "refuse them all"**
        -- a controller nobody gave a confirmation seam to can never destroy
        anything. Wire it to the main window's confirmation dialog.
    ``require_superuser``
        Whether opening a session insists on a superuser connection (the
        default, True: provisioning needs `CREATE DATABASE` and installing
        `plpgsql_check` needs `CREATE EXTENSION`, §18.2's New Project Test
        button verifies exactly this). Set False to hold a read/apply-only
        session on a non-superuser sandbox.
    ``prober`` / ``opener`` / ``provisioner`` / ``database_creator`` /
    ``cloner`` / ``installer`` / ``snapshotter``
        `probe`, `open_sandbox`, `provision_sandbox`, `create_sandbox_database`,
        `clone_data`, `install_plpgsql_check` and
        `db/introspect.py::snapshot_for_baseline` respectively.
    ``checker``
        `db/ddl_check.py::recheck` -- §18.5 D3a's ladder entry point,
        `(session, request, caps) -> CheckReport`. Injected like every other
        `db/` seam; **the ladder is not re-composed here and no SQL is built
        here**, this module only supplies the session, the capabilities and the
        thread.

    Wiring surface for the main session: `set_project`/`clear_project`,
    `open_session`/`close_session`/`reset_session`, `provision`,
    `run_data_clone`, `install_plpgsql_check`, `run_check`,
    `refresh_capabilities`, the zero-argument §18.8 adapters
    `on_run_data_clone`/`on_install_plpgsql_check`, the read-only
    `has_session`/`session`/`capabilities`/`can_check`/`capability_status`, and
    the two signals below.
    """

    #: True when a live session exists, False when it is gone -- the signal the
    #: "Apply to Sandbox"/§18.7 sandbox DDL Explorer affordances gate on.
    session_changed = Signal(bool)
    #: Emitted with one `SandboxOperationResult` as each operation finishes,
    #: successfully or not. `object`, so the dataclass rides across as-is.
    operation_finished = Signal(object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        confirm_destructive: Callable[[str], bool] | None = None,
        require_superuser: bool = True,
        prober: Callable[..., SandboxCapabilities] = probe,
        opener: Callable[..., SandboxSession] = open_sandbox,
        provisioner: Callable[..., SandboxSession] = provision_sandbox,
        database_creator: Callable[..., None] = create_sandbox_database,
        cloner: Callable[..., None] = clone_data,
        installer: Callable[[SandboxSession], None] = install_plpgsql_check,
        snapshotter: Callable[..., BaselineSnapshot] = snapshot_for_baseline,
        checker: Callable[..., object] = recheck,
    ) -> None:
        super().__init__(parent)
        # Plain attribute, replaced wholesale by a synchronous stub in tests --
        # the ConnectionSetupDialog/NewProjectDialog convention.
        self._run_async = run_async

        self._confirm_destructive = confirm_destructive
        self._require_superuser = require_superuser
        self._prober = prober
        self._opener = opener
        self._provisioner = provisioner
        self._database_creator = database_creator
        self._cloner = cloner
        self._installer = installer
        self._snapshotter = snapshotter
        self._checker = checker

        self._session: SandboxSession | None = None
        self._capabilities: SandboxCapabilities | None = None
        self._sandbox_params: ConnectionParams | None = None
        self._target_params: ConnectionParams | None = None
        self._mode = SandboxMode.SCHEMA_ONLY
        self._configured = False
        self._baseline: DatabaseSchema | BaselineSnapshot | None = None
        self._schema_names: frozenset[str] = frozenset()

    # -- project binding ----------------------------------------------------

    def set_project(
        self,
        *,
        sandbox_params: ConnectionParams | None,
        target_params: ConnectionParams | None = None,
        mode: SandboxMode = SandboxMode.SCHEMA_ONLY,
        configured: bool | None = None,
    ) -> None:
        """Point the controller at the open project's sandbox.

        Takes `ProjectSettings.sandbox`/`.target`/`.sandbox_mode` verbatim
        (§18.2) -- the mode is **recorded, never re-derived** (§18.5 D2a), which
        is also what a later `reset()` re-runs. Drops any live session, since it
        belonged to the previous project.

        **Opens nothing and provisions nothing** -- no destructive operation and
        no connection attempt happens as a side effect of a project opening.
        `configured` defaults to "sandbox_params were supplied at all", which is
        `determine_project_tier`'s `sandbox_configured` input.
        """
        self.close_session()
        self._sandbox_params = sandbox_params
        self._target_params = target_params
        self._mode = mode
        self._configured = bool(sandbox_params) if configured is None else configured
        self._capabilities = None
        self._baseline = None
        self._schema_names = frozenset()

    def clear_project(self) -> None:
        """Forget the project entirely (project closed) -- session released,
        capabilities dropped, back to "no sandbox configured"."""
        self.set_project(sandbox_params=None, configured=False)

    # -- read-only state ----------------------------------------------------

    @property
    def has_session(self) -> bool:
        """Whether a live, ownership-gated `SandboxSession` is held."""
        return self._session is not None

    @property
    def session(self) -> SandboxSession | None:
        """The live session, or None. The single object every sandbox write
        (`apply`, `install_plpgsql_check`, `reset`) must go through."""
        return self._session

    @property
    def can_check(self) -> bool:
        """Whether the §18.5 D3a **Check** gesture should exist at all.

        The host binds the Check control's *visibility* to this (carve-out 2's
        "no dead controls": with no live `SandboxSession` there is no button and
        no enabled menu item, the same posture as the absent apply row) -- not
        its enabled state. It is deliberately a separate name from
        `has_session` even though it currently returns the same fact, so the
        host expresses the intent it means and this predicate can grow a second
        precondition without every caller being revisited.

        **The extension's absence is not a precondition here.** Tier 3 being
        `unavailable` is a *reported outcome* of a run (D3a's four
        `plpgsql_check_state` rows), so the gesture stays present and states
        what it could not check; hiding it would be the silent no-op D3a
        forbids.
        """
        return self._session is not None

    @property
    def capabilities(self) -> SandboxCapabilities | None:
        """The most recent probe result, or None if never probed."""
        return self._capabilities

    @property
    def mode(self) -> SandboxMode:
        """The recorded provisioning mode (§18.5 D2a)."""
        return self._mode

    @property
    def sandbox_params(self) -> ConnectionParams | None:
        return self._sandbox_params

    @property
    def target_params(self) -> ConnectionParams | None:
        return self._target_params

    def capability_status(self):
        """`ProjectCapabilityStatus` for the last probe -- tier 2 vs. tier 3 and,
        when degraded, exactly why. Delegates wholly to
        `determine_project_tier`; this controller derives no tier itself and
        invents no reason string. Before any probe, reports the honest
        "not probed yet" degradation."""
        return determine_project_tier(
            self._capabilities or _NOT_PROBED, self._mode, self._configured
        )

    @staticmethod
    def is_destructive(operation: SandboxOperation) -> bool:
        """Whether `operation` drops/recreates sandbox contents -- what a caller
        checks to decide it must confirm first."""
        return operation in DESTRUCTIVE_OPERATIONS

    @staticmethod
    def destructive_warning(operation: SandboxOperation) -> str:
        """The sentence a caller's confirmation prompt should show for
        `operation`; empty for a non-destructive one. Text only -- this module
        shows nothing."""
        return _DESTRUCTIVE_WARNINGS.get(operation, "")

    # -- operations ---------------------------------------------------------

    def refresh_capabilities(
        self, on_done: Callable[[SandboxOperationResult], None] | None = None
    ) -> None:
        """Re-probe the sandbox off the GUI thread and cache the result --
        §18.8's Project Status re-check, which must be a *fresh* probe rather
        than a read of a cached one. Reported as an `OPEN` result whose `ok`
        mirrors whether the capabilities are good enough to open a session; the
        session itself is untouched.
        """
        params = self._sandbox_params
        if params is None:
            self._finish(
                SandboxOperation.OPEN,
                False,
                "no local sandbox configured for this project",
                on_done,
            )
            return

        def work() -> SandboxCapabilities:
            return self._prober(params)

        def on_result(caps: SandboxCapabilities) -> None:
            self._capabilities = caps
            reason = self._blocking_reason(caps)
            self._finish(
                SandboxOperation.OPEN, reason is None, reason or "", on_done, caps
            )

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.OPEN, on_done
        ))

    def open_session(
        self, on_done: Callable[[SandboxOperationResult], None] | None = None
    ) -> None:
        """Probe, then open the one session through `open_sandbox` -- the single
        ownership gate (§18.5 D2). Never re-implements that check.

        Fails, without opening anything, when the probe reports a blocking
        condition, each with its own distinguishable reason: *unreachable*
        (`probe_error`, via `determine_project_tier`), *not a superuser*
        (`install_gate`'s exact sentence), *`pg_dump`/`pg_restore` missing*
        (only under `SandboxMode.WITH_DATA`, per D2a), or *no sandbox
        configured*. A database PGTP Editor did not create fails with
        `ForeignDatabaseError`'s own message.
        """
        params = self._sandbox_params
        if params is None:
            self._finish(
                SandboxOperation.OPEN,
                False,
                "no local sandbox configured for this project",
                on_done,
            )
            return

        mode = self._mode
        target_params = self._target_params
        baseline = self._baseline
        schema_names = self._schema_names

        def work() -> tuple[SandboxSession | None, SandboxCapabilities, str | None]:
            caps = self._prober(params)
            reason = self._blocking_reason(caps)
            if reason is not None:
                return None, caps, reason
            session = self._opener(
                params,
                mode=mode,
                schema_names=schema_names,
                baseline=baseline,
                target_params=target_params,
            )
            return session, caps, None

        def on_result(
            outcome: tuple[SandboxSession | None, SandboxCapabilities, str | None]
        ) -> None:
            session, caps, reason = outcome
            self._capabilities = caps
            if session is None:
                self._finish(SandboxOperation.OPEN, False, reason or "", on_done, caps)
                return
            self._set_session(session)
            self._finish(SandboxOperation.OPEN, True, "", on_done, caps)

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.OPEN, on_done
        ))

    def close_session(self) -> None:
        """Release the session (project closed, sandbox reconfigured). Nothing
        to close on the wire -- `db/sandbox.py`'s executors open one connection
        per call and close it themselves -- so this only drops the reference and
        announces it. Safe to call when none is held."""
        if self._session is None:
            return
        self._session = None
        self.session_changed.emit(False)

    def provision(
        self,
        on_done: Callable[[SandboxOperationResult], None] | None = None,
        *,
        admin_params: ConnectionParams | None = None,
        database_name: str | None = None,
    ) -> None:
        """**Destructive.** Provision the sandbox from the target database and
        hold the resulting session (`provision_sandbox`, which itself composes
        `open_sandbox` + `build_baseline_sql` or, under `WITH_DATA`,
        `clone_data`).

        With both `admin_params` and `database_name`, first runs
        `create_sandbox_database` -- D2's mandatory *"create a sandbox database
        for me"* mitigation for the `ForeignDatabaseError` refusal. The baseline
        snapshot comes from the **target** profile via
        `db/introspect.py::snapshot_for_baseline`; a `WITH_DATA` sandbox needs
        the target params too, to clone from.
        """
        params = self._sandbox_params
        if params is None:
            self._finish(
                SandboxOperation.PROVISION,
                False,
                "no local sandbox configured for this project",
                on_done,
            )
            return
        target_params = self._target_params
        if target_params is None:
            self._finish(
                SandboxOperation.PROVISION,
                False,
                "provisioning needs the project's target connection to build the "
                "sandbox baseline from, but none is configured",
                on_done,
            )
            return
        if not self._confirmed(SandboxOperation.PROVISION, on_done):
            return

        mode = self._mode

        def work() -> tuple[SandboxSession, BaselineSnapshot | DatabaseSchema]:
            if admin_params is not None and database_name is not None:
                self._database_creator(admin_params, database_name)
            snapshot = self._snapshotter(target_params)
            session = self._provisioner(
                snapshot, params, mode, target_params=target_params
            )
            return session, snapshot

        def on_result(
            outcome: tuple[SandboxSession, BaselineSnapshot | DatabaseSchema]
        ) -> None:
            session, snapshot = outcome
            self._baseline = snapshot
            self._schema_names = session.schema_names
            self._set_session(session)
            self._finish(SandboxOperation.PROVISION, True, "", on_done)

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.PROVISION, on_done
        ))

    def run_data_clone(
        self, on_done: Callable[[SandboxOperationResult], None] | None = None
    ) -> None:
        """**Destructive.** Re-run D2a's `pg_dump`/`pg_restore` clone from the
        target into the sandbox -- §18.8's Sandbox1 action button.

        Only ever attempted for a `SandboxMode.WITH_DATA` sandbox: cloning into
        a schema-only sandbox would silently change what kind of sandbox it is,
        and the mode is chosen once at creation time and never toggled (D2a).
        A missing binary surfaces as `MissingCloneToolError`'s own message
        (which binary, which `PATH`), never a silent fall-back to schema-only.
        """
        if self._session is None:
            self._finish(
                SandboxOperation.CLONE_DATA, False, _NO_SESSION_REASON, on_done
            )
            return
        if self._mode is not SandboxMode.WITH_DATA:
            self._finish(
                SandboxOperation.CLONE_DATA,
                False,
                "this sandbox was created 'without data' (schema-only); data "
                "cloning is chosen once at sandbox-creation time and is not "
                "available for it",
                on_done,
            )
            return
        target_params = self._target_params
        if target_params is None:
            self._finish(
                SandboxOperation.CLONE_DATA,
                False,
                "data cloning needs the project's target connection to clone "
                "from, but none is configured",
                on_done,
            )
            return
        if not self._confirmed(SandboxOperation.CLONE_DATA, on_done):
            return

        sandbox_params = self._session.params

        def work() -> None:
            self._cloner(target_params, sandbox_params)

        def on_result(_ignored) -> None:
            self._finish(SandboxOperation.CLONE_DATA, True, "", on_done)

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.CLONE_DATA, on_done
        ))

    def install_plpgsql_check(
        self, on_done: Callable[[SandboxOperationResult], None] | None = None
    ) -> None:
        """Run `CREATE EXTENSION IF NOT EXISTS plpgsql_check` through the live
        session -- §18.8's Sandbox2 action button, and the same one-click
        install the Sandbox Setup dialog offers (§18.5 D2).

        Whether it is worth attempting is decided by the pure `install_gate`,
        not re-litigated here: an already-installed extension succeeds as a
        no-op carrying the gate's *"already installed."* line, and a refused
        gate fails with the gate's exact reason (`absent` / not-superuser /
        could-not-probe). Non-destructive -- `IF NOT EXISTS` drops nothing.
        """
        session = self._session
        if session is None:
            self._finish(
                SandboxOperation.INSTALL_PLPGSQL_CHECK,
                False,
                _NO_SESSION_REASON,
                on_done,
            )
            return
        caps = self._capabilities
        if caps is not None:
            offered, reason = install_gate(caps)
            if not offered:
                already = caps.plpgsql_check_state == "installed"
                self._finish(
                    SandboxOperation.INSTALL_PLPGSQL_CHECK,
                    already,
                    reason,
                    on_done,
                    caps,
                )
                return

        def work() -> None:
            self._installer(session)

        def on_result(_ignored) -> None:
            self._finish(SandboxOperation.INSTALL_PLPGSQL_CHECK, True, "", on_done)

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.INSTALL_PLPGSQL_CHECK, on_done
        ))

    def run_check(
        self,
        request: object,
        on_done: Callable[[SandboxOperationResult], None] | None = None,
    ) -> None:
        """**Non-destructive.** Run §18.5 D3a's validation ladder against one
        object in the live sandbox and report the `CheckReport` it produced.

        `request` is a `db/ddl_check.py::CheckRequest` -- built by the host from
        the invoking tab's `DdlObjectRef` (`CheckRequest.from_ref(ref, text)`),
        because a trigger's referenced function is knowledge the ref alone does
        not carry and this controller must not guess it. It is passed through
        untouched: **the ladder's composition, its SQL and its outcome
        vocabulary all live in `db/ddl_check.py`** and none of it is duplicated
        or re-decided here. Exactly one object per run (D3a) -- there is no
        multi-object entry point, and `check_working_set` is deliberately not
        wired in this pass.

        Confirmation is never asked for: `CHECK` is not in
        `DESTRUCTIVE_OPERATIONS`, applies nothing and writes nothing, so
        `confirm_destructive` is not consulted even when one is wired.

        Capabilities gate tier 3, and they come from the
        `PostgresBackend.capabilities()` contract, never from a bare
        `try/except` (D3a): the cached probe is reused when there is one, and a
        controller that has never probed probes *inside the worker* rather than
        passing "unknown" off as a fact. The gate itself is
        `db/ddl_check.py`'s -- this method reads no `plpgsql_check_state`.

        `ok` means **the ladder ran and reported nothing**:

        | Situation | `ok` | `reason` | `report` |
        |---|---|---|---|
        | tier 3 ran, no findings | True | empty | the report |
        | tier 3 ran, findings | False | how many findings | the report |
        | tier 3 `unavailable`/`errored` | False | that tier's own reason, verbatim | the report |
        | no live session | False | `_NO_SESSION_REASON` | None |
        | the worker raised | False | the exception's message | None |

        A findings-bearing or unavailable report is still a *delivered* report:
        the host renders it (narrative lines plus the clickable
        `check_findings` channel) from `result.report` and does not re-derive
        any of it from `reason`.
        """
        session = self._session
        if session is None:
            # Carve-out 2 means the host should not have offered the gesture at
            # all (see `can_check`); if it did, the answer is a stated reason --
            # never a crash, and never an empty report that would read as clean.
            self._finish(SandboxOperation.CHECK, False, _NO_SESSION_REASON, on_done)
            return
        if request is None:
            self._finish(
                SandboxOperation.CHECK, False, _NO_CHECK_REQUEST_REASON, on_done
            )
            return

        cached_caps = self._capabilities
        params = session.params

        def work() -> tuple[object, SandboxCapabilities]:
            caps = cached_caps if cached_caps is not None else self._prober(params)
            return self._checker(session, request, caps), caps

        def on_result(outcome: tuple[object, SandboxCapabilities]) -> None:
            report, caps = outcome
            self._capabilities = caps
            ok, reason = self._check_outcome(report)
            result = SandboxOperationResult(
                operation=SandboxOperation.CHECK,
                ok=ok,
                reason=reason,
                capabilities=caps,
                report=report,
            )
            if on_done is not None:
                on_done(result)
            self.operation_finished.emit(result)

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.CHECK, on_done
        ))

    def reset_session(
        self, on_done: Callable[[SandboxOperationResult], None] | None = None
    ) -> None:
        """**Destructive.** `SandboxSession.reset()` -- `DROP SCHEMA … CASCADE`
        for every recorded app schema (never the reserved
        `pgtp_editor_sandbox` bookkeeping schema, which the session itself
        excludes) followed by a re-run of whichever mode the sandbox was created
        with. The session object is kept: reset re-provisions it, it does not
        invalidate it."""
        session = self._session
        if session is None:
            self._finish(SandboxOperation.RESET, False, _NO_SESSION_REASON, on_done)
            return
        if not self._confirmed(SandboxOperation.RESET, on_done):
            return

        def work() -> None:
            session.reset()

        def on_result(_ignored) -> None:
            self._finish(SandboxOperation.RESET, True, "", on_done)

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.RESET, on_done
        ))

    # -- §18.8 zero-argument adapters ---------------------------------------

    def on_run_data_clone(self) -> None:
        """`ProjectStatusPanel(on_run_data_clone=…)` -- Sandbox1's button."""
        self.run_data_clone()

    def on_install_plpgsql_check(self) -> None:
        """`ProjectStatusPanel(on_install_plpgsql_check=…)` -- Sandbox2's."""
        self.install_plpgsql_check()

    # -- internals ----------------------------------------------------------

    def _set_session(self, session: SandboxSession) -> None:
        self._session = session
        self.session_changed.emit(True)

    def _blocking_reason(self, caps: SandboxCapabilities) -> str | None:
        """Why a session cannot be opened against `caps`, or None.

        Reuses `determine_project_tier`'s reasons verbatim (unreachable, tools
        missing, not configured) and `install_gate`'s exact superuser sentence
        -- no reason string is authored here. Superuser is checked *between*
        those two because it is a property of the connection, while the tools
        check is about the machine, and the more specific cause reads better
        first.
        """
        status = determine_project_tier(caps, self._mode, self._configured)
        if not self._configured or caps.probe_error is not None:
            return status.degraded_reason
        if self._require_superuser and not caps.is_superuser:
            return f"sandbox unavailable: {REQUIRES_SUPERUSER_REASON}"
        return status.degraded_reason

    def _confirmed(
        self,
        operation: SandboxOperation,
        on_done: Callable[[SandboxOperationResult], None] | None,
    ) -> bool:
        """Ask the injected confirmation seam; report a refusal as a stated
        failure. No dialog is opened here, ever."""
        warning = self.destructive_warning(operation)
        if self._confirm_destructive is None or not self._confirm_destructive(warning):
            self._finish(
                operation,
                False,
                f"cancelled -- this operation was not confirmed. {warning}".strip(),
                on_done,
            )
            return False
        return True

    @staticmethod
    def _check_outcome(report: object) -> tuple[bool, str]:
        """`(ok, reason)` for one `CheckReport`, read **duck-typed** (`ran`,
        `tier3`, `findings`) exactly as `ui/ddl_object_editor.py` reads it, so a
        test stub with those three attributes is a valid report and this module
        never imports `ddl_check`'s types for anything but the default seam.

        Nothing is re-worded: an unavailable/errored tier's reason is D3's own
        sentence, passed through. A report object that carries none of these
        attributes is reported as not-run rather than as clean -- the one
        direction this must never fail in.
        """
        findings = tuple(getattr(report, "findings", ()) or ())
        tier3 = getattr(report, "tier3", None)
        if not getattr(report, "ran", False):
            reason = str(getattr(tier3, "reason", "") or "").strip()
            status = str(getattr(tier3, "status", "") or "").strip()
            if not reason:
                reason = (
                    f"the check did not run ({status})."
                    if status
                    else "the check did not run, and reported no reason -- nothing "
                    "about this object was verified."
                )
            return False, reason
        if findings:
            count = len(findings)
            plural = "" if count == 1 else "s"
            return False, f"plpgsql_check reported {count} finding{plural}."
        return True, ""

    def _error_handler(
        self,
        operation: SandboxOperation,
        on_done: Callable[[SandboxOperationResult], None] | None,
    ) -> Callable[[BaseException], None]:
        """Turn any exception the worker raised into a reported failure carrying
        its message -- `ForeignDatabaseError`, `MissingCloneToolError` and
        `CloneDataError` all already read as finished sentences."""

        def handle(exc: BaseException) -> None:
            self._finish(operation, False, str(exc) or exc.__class__.__name__, on_done)

        return handle

    def _finish(
        self,
        operation: SandboxOperation,
        ok: bool,
        reason: str,
        on_done: Callable[[SandboxOperationResult], None] | None,
        capabilities: SandboxCapabilities | None = None,
    ) -> None:
        result = SandboxOperationResult(
            operation=operation, ok=ok, reason=reason, capabilities=capabilities
        )
        if on_done is not None:
            on_done(result)
        self.operation_finished.emit(result)
