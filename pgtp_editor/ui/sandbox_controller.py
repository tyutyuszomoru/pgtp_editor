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
existed for **Check and commit to sandbox** to apply to and §18.8's Sandbox1/Sandbox2
action buttons ("run data clone", "install plpgsql_check") had nothing to fire
at. This module is exactly that holder and nothing more -- **it duplicates none
of `db/sandbox.py`'s logic**; every decision (ownership, tier degradation, the
install gate's reason strings, which provisioning strategy a mode implies) is
delegated to the function in `db/` that already owns it.

**Off the GUI thread, through the established seam.** Every DB-touching
operation goes through `self._run_async`, a plain attribute defaulting to
`ui/async_task.py::run_async` -- the same convention
`ConnectionSetupDialog`/`NewProjectDialog`/`ProjectSettingsDialog` use, and the
same one tests replace with a synchronous stand-in. Nothing here blocks the
event loop, and results come back on the GUI thread where the caller may touch
widgets.

`MainWindow` **repoints that attribute at its `_shell_run_async` trampoline**
right after constructing the controller, so `window._run_async = sync_run` --
the one documented, window-wide injection point every other lane already
honours -- reaches this lane too. It did not, before BUG-043: this attribute
captured the module-level `run_async` at construction time, so a test that
injected at the window silently left the sandbox lane on the real threadpool,
and its worker outlived the window it was started from. Do NOT "simplify" this
back to a constructor kwarg captured at build time; the trampoline's value is
that it re-reads `window._run_async` at CALL time.

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
unavailable: pg_dump not found …" -- which names the configured binaries folder
when there is one and only says "on PATH" when there is not (FQ-260812025353);
do NOT quote one branch here as though it were the whole sentence, which is how
this docstring became the FOURTH prose statement of a resolution order nothing
enforces -- "no local sandbox configured for this project"), `SandboxCapabilities.probe_error`, `install_gate`'s four exact reason
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

import logging
import re
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from PySide6.QtCore import QObject, Signal

from ..db.config import ConnectionParams
from ..db.ddl_check import apply_and_check, probe_check, recheck
from ..db.introspect import BaselineSnapshot, DatabaseSchema, snapshot_for_baseline
from ..db.sandbox import (
    SANDBOX_DB_PREFIX,
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
    purge_orphaned_alter_rows,
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

_log = logging.getLogger(__name__)


#: The maintenance database `create_sandbox_database`'s admin connection targets,
#: since PostgreSQL forbids `CREATE DATABASE` inside the database being created.
#: Defined here, once, because three surfaces need the same answer (§18.2's New
#: Project step, Project Settings' provisioning group, and this module's own
#: `provision_new_database` callers); `DEFAULT_MAINTENANCE_DATABASE` in
#: `ui/project_settings_dialog.py` is an alias of this name, never a second
#: literal.
MAINTENANCE_DATABASE = "postgres"

#: `db/sandbox.py::_SANDBOX_DB_NAME_RE` is `^pgtp_sandbox_[a-z0-9_]{1,40}$`, so
#: everything after `SANDBOX_DB_PREFIX` must fit in 40 characters of
#: `[a-z0-9_]`. The generated name spends that budget as
#: `<stem>_<suffix>`: a readable, slugified project stem plus a random suffix
#: that makes collisions vanishingly unlikely in the first place.
_NAME_BUDGET = 40
#: Random suffix length, in hex characters (4 bytes -> 8 chars, ~4e9 values).
_SUFFIX_LENGTH = 8
_STEM_BUDGET = _NAME_BUDGET - _SUFFIX_LENGTH - 1
#: How many distinct names the New Project flow generates before giving up.
#: Collisions are already improbable; this bounds the pathological case rather
#: than expecting to be used (§18.2/FQ-007: on collision, generate a *different*
#: random name -- never reuse and never drop an existing database).
DEFAULT_NAME_ATTEMPTS = 6

_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")

#: PostgreSQL's `duplicate_database` SQLSTATE -- the one error
#: `create_sandbox_database` may raise that means "pick another name" rather
#: than "this failed".
DUPLICATE_DATABASE_SQLSTATE = "42P04"


def sandbox_name_stem(project_name: str = "") -> str:
    """The readable half of a generated sandbox database name: `project_name`
    slugified into `[a-z0-9_]`, collapsed, trimmed and truncated to the budget
    the name regex leaves. Pure. Falls back to `"project"` for a nameless
    project, so the result is always a legal stem."""
    slug = _NON_SLUG_RE.sub("_", (project_name or "").strip().casefold()).strip("_")
    return slug[:_STEM_BUDGET].strip("_") or "project"


def generate_sandbox_database_name(project_name: str = "", *, suffix: str | None = None) -> str:
    """One auto-generated, convention-satisfying sandbox database name (§18.2,
    FQ-007: **the user never types a sandbox database name**).

    `SANDBOX_DB_PREFIX` + a slugified project stem + a random suffix, built so it
    matches `db/sandbox.py`'s `^pgtp_sandbox_[a-z0-9_]{1,40}$` by construction --
    the *validation* stays `create_sandbox_database`'s (it validates rather than
    sanitizes, and nothing here weakens that). Pure apart from the random
    suffix, which `suffix=` pins for tests.
    """
    token = (suffix or secrets.token_hex(_SUFFIX_LENGTH // 2))[:_SUFFIX_LENGTH]
    return f"{SANDBOX_DB_PREFIX}{sandbox_name_stem(project_name)}_{token}"


def generate_sandbox_database_names(
    project_name: str = "", *, count: int = DEFAULT_NAME_ATTEMPTS
) -> list[str]:
    """`count` *distinct* candidate names for one provisioning attempt -- the
    retry list `provision_new_database` walks, taking the first free one."""
    names: list[str] = []
    while len(names) < max(1, count):
        name = generate_sandbox_database_name(project_name)
        if name not in names:
            names.append(name)
    return names


def is_duplicate_database_error(exc: BaseException) -> bool:
    """Whether `exc` means *"a database with that name already exists"* -- the
    one failure of `create_sandbox_database` that is answered by trying the next
    generated name instead of reporting it.

    Read duck-typed (psycopg's `sqlstate`) with a message fallback, so this
    module needs no psycopg import and a test's fake creator can raise a plain
    exception carrying either signal.
    """
    if getattr(exc, "sqlstate", None) == DUPLICATE_DATABASE_SQLSTATE:
        return True
    if getattr(getattr(exc, "diag", None), "sqlstate", None) == DUPLICATE_DATABASE_SQLSTATE:
        return True
    text = str(exc).casefold()
    return "already exists" in text and "database" in text


class SandboxNameCollisionError(RuntimeError):
    """Every generated `pgtp_sandbox_*` name was already taken on the server.

    A stated, actionable failure -- **and the point at which the flow stops**:
    an existing database is never dropped and never provisioned into, so no data
    can be lost to a name collision (FQ-007 rejects both the reuse-if-app-owned
    and the drop-and-recreate branches).
    """

    def __init__(self, names: Sequence[str]) -> None:
        self.names = tuple(names)
        listed = ", ".join(self.names) or "(none generated)"
        super().__init__(
            "could not create a sandbox database: every name PGTP Editor "
            f"generated already exists on this server ({listed}). Nothing was "
            "created and no existing database was touched -- retry, or remove "
            "the leftover sandbox databases first."
        )


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
    #: §18.5 D3's **Check and commit to sandbox** -- `db/ddl_check.py::apply_and_check`:
    #: the ladder, committing, with the working-set row written in the same
    #: transaction.
    #:
    #: **Also deliberately absent from `DESTRUCTIVE_OPERATIONS`, and that needs
    #: saying out loud because an apply DOES change the sandbox.**
    #: `DESTRUCTIVE_OPERATIONS` means one specific thing here -- an operation
    #: that *drops and recreates schemas or overwrites the sandbox wholesale*
    #: (`PROVISION`, `CLONE_DATA`, `RESET`, each of which loses everything
    #: already applied). An apply is the opposite: `CREATE OR REPLACE` is
    #: idempotent, it destroys no schema, and §18.5 D2 is explicit that **the
    #: sandbox is STATEFUL and accumulates applied edits -- that is its
    #: purpose**. Putting an apply behind `confirm_destructive` would demand a
    #: confirmation on every iteration of the edit/validate loop, which is both
    #: the wrong claim (nothing is being destroyed) and actively harmful: it
    #: trains the user to click through the one prompt that protects the three
    #: operations that really do wipe the sandbox. The confirmation an apply
    #: *does* need is the panel's own (`ui/ddl_object_editor.py`'s injected
    #: `confirm` seam), which names the object -- a different question from
    #: "may I destroy this sandbox?".
    APPLY = "apply"


#: The operations that drop and recreate schemas (or overwrite the sandbox's
#: contents wholesale). Each is refused unless `confirm_destructive` approves it
#: -- §18.5 D2a's "refreshing means destroying and recreating the sandbox" is a
#: deliberate user act, never a side effect.
#:
#: **`APPLY` and `CHECK` are not here on purpose** -- see `SandboxOperation.APPLY`
#: for why "it changes the sandbox" is not the same as "it destroys the sandbox",
#: and why widening this set would weaken the prompt rather than strengthen it.
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

#: The same stated refusal for `run_apply`. Separate wording because the two
#: gestures are separate sentences to the user, not because the situation
#: differs.
_NO_APPLY_REQUEST_REASON = (
    "nothing to apply -- Check and commit to sandbox needs the object whose tab it was "
    "invoked from"
)

#: `provision_new_database` was called with nothing to name the database. Stated
#: rather than silently generating one here, because the *caller* owns the
#: project name the stem comes from.
_NO_NAME_CANDIDATES_REASON = (
    "no sandbox database name was generated, so nothing was created -- the "
    "caller must supply the auto-generated candidate names"
)

#: Provisioned with no target connection to build a baseline from. The sandbox is
#: real, app-owned and usable (bookkeeping table included), it just starts empty
#: -- said out loud rather than passed off as a full baseline.
_NO_TARGET_BASELINE_NOTE = (
    "The sandbox was created EMPTY: the project has no target connection yet, "
    "so there was no database to build a baseline from. Set the target in "
    "Project Settings, then re-provision from the Sandbox provisioning group "
    "on the same tab."
)

#: A "with data" sandbox with no target to clone from cannot be cloned *yet*.
#: Said out loud instead of failing (or pretending rows arrived); the project's
#: recorded mode is left alone, since D2a's mode is the user's choice.
_WITH_DATA_NEEDS_TARGET_NOTE = (
    "'With data' was requested but the project has no target connection to "
    "clone from, so no data was cloned. Set the target in Project Settings, "
    "then run the data clone from the Project Status window's sandbox "
    "data node."
)

#: A green probe is still not an apply. Stated rather than reported as success,
#: so *"it would have worked"* and *"it is now in the sandbox"* stay apart.
_PROBE_NOT_APPLIED_REASON = (
    "checked without applying: the ladder ran green inside a transaction that "
    "was then rolled back, so the sandbox is unchanged."
)

#: The ladder was green but the transaction did not commit -- the one direction
#: this must never be silent in, because the user pressed Apply.
_NOT_COMMITTED_REASON = (
    "NOTHING WAS APPLIED: the ladder ran green but the transaction did not "
    "commit, so the sandbox is unchanged."
)

#: The four tier attribute names on a `db/ddl_check.py::CheckReport`, in ladder
#: order -- the same four `ui/ddl_object_editor.py` reads. Both take the
#: vocabulary from `db/ddl_check.py`; see `_tier_rows` for why this module does
#: not import the panel's copy.
_TIER_ATTRS = ("tier0", "tier1", "tier2", "tier3")


def _tier_rows(report: object) -> list[tuple[str, str, str]]:
    """`[(name, status, reason), …]` for the tiers a report carries, read
    duck-typed exactly as `ui/ddl_object_editor.py::tier_outcomes` does.

    Kept here rather than imported from the panel because this module must not
    depend on a widget module to interpret a `db/` dataclass; the *vocabulary*
    is `db/ddl_check.py`'s and both readers take it from there.
    """
    rows: list[tuple[str, str, str]] = []
    for name in _TIER_ATTRS:
        outcome = getattr(report, name, None)
        if outcome is None:
            continue
        rows.append(
            (
                name,
                str(getattr(outcome, "status", "") or ""),
                str(getattr(outcome, "reason", "") or "no reason given"),
            )
        )
    return rows


@dataclass(frozen=True)
class SandboxOperationResult:
    """The outcome of exactly one controller operation -- success or a stated,
    human-readable reason, never a swallowed exception.

    `reason` is empty only on a bare success; a successful operation may still
    carry an explanatory line (e.g. `install_gate`'s *"already installed."*).

    `report` is set **only** by `SandboxOperation.CHECK`/`APPLY`, and carries the
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
    #: The sandbox database `provision_new_database` actually created, so the
    #: host can record THAT name in `ProjectSettings.sandbox` -- empty for every
    #: other operation, and empty on failure precisely so a project can never end
    #: up claiming a sandbox database that was not created.
    database_name: str = ""


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
    ``checker`` / ``applier`` / ``probe_checker``
        §18.5 D3's three ladder entry points -- `db/ddl_check.py::recheck`
        (`(session, request, caps) -> CheckReport`), `apply_and_check` (commits)
        and `probe_check` (rolled back). Injected like every other `db/` seam;
        **the ladder is not re-composed here and no SQL is built here**, this
        module only supplies the session, the capabilities and the thread.

    Wiring surface for the main session: `set_project`/`clear_project`,
    `open_session`/`close_session`/`reset_session`, `provision`,
    `provision_new_database` (§18.2's New Project step: create an auto-named
    database, then provision it),
    `run_data_clone`, `install_plpgsql_check`, `run_check`, `run_apply`,
    `refresh_capabilities`, the zero-argument §18.8 adapters
    `on_run_data_clone`/`on_install_plpgsql_check`, the read-only
    `has_session`/`session`/`capabilities`/`can_check`/`capability_status`, and
    the two signals below.
    """

    #: True when a live session exists, False when it is gone -- the signal the
    #: "Check and commit to sandbox"/§18.7 sandbox DDL Explorer affordances gate on.
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
        applier: Callable[..., object] = apply_and_check,
        probe_checker: Callable[..., object] = probe_check,
        orphan_purger: Callable[[SandboxSession], None] = purge_orphaned_alter_rows,
    ) -> None:
        super().__init__(parent)
        # Plain attribute, replaced wholesale in tests -- the
        # ConnectionSetupDialog/NewProjectDialog convention. This module-level
        # default is only the standalone fallback: `MainWindow` overwrites it
        # with `self._shell_run_async` immediately after construction, so the
        # window-wide `window._run_async` injection point covers this lane too
        # (BUG-043 -- it did not, and workers outlived their window).
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
        self._applier = applier
        self._probe_checker = probe_checker
        self._purge_orphans = orphan_purger

        self._session: SandboxSession | None = None
        self._capabilities: SandboxCapabilities | None = None
        self._sandbox_params: ConnectionParams | None = None
        self._target_params: ConnectionParams | None = None
        self._mode = SandboxMode.SCHEMA_ONLY
        self._configured = False
        #: §18.2's per-project *Locate postgres binaries* folder
        #: (FQ-260812025353), recorded by `set_project` and handed to EVERY
        #: `db/sandbox.py` seam this controller drives. `""` is PATH-only,
        #: which is what the whole chain did before the setting existed.
        self._postgres_bin_dir = ""
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
        postgres_bin_dir: str = "",
    ) -> None:
        """Point the controller at the open project's sandbox.

        Takes `ProjectSettings.sandbox`/`.target`/`.sandbox_mode` verbatim
        (§18.2) -- the mode is **recorded, never re-derived** (§18.5 D2a), which
        is also what a later `reset()` re-runs. Drops any live session, since it
        belonged to the previous project.

        **THIS METHOD opens nothing and provisions nothing** -- it records
        params and drops the old session, and no destructive operation happens
        inside it. That is a statement about this method, not about project
        opening: since BUG-040 the host DOES open the session right after
        calling this (`MainWindow._bind_sandbox_controller_to_project`), and
        `DdlProjectController.refresh_capability_status` had been connecting at
        project-open time long before that. The line this docstring used to
        carry -- *"no connection attempt happens as a side effect of a project
        opening"* -- was policy stated in the wrong layer, and it had already
        stopped being true.

        The D2 single-ownership rule is unaffected and is what makes the split
        clean: `open_session`/`open_sandbox` remains the ONE way a session is
        acquired. Who calls it, and when, is the host's policy to set.

        `configured` defaults to "sandbox_params were supplied at all", which is
        `determine_project_tier`'s `sandbox_configured` input.

        `postgres_bin_dir` is `ProjectSettings.postgres_bin_dir`, taken verbatim
        like the other three (FQ-260812025353). It rides on the project binding
        rather than on each operation because it is a property of the PROJECT,
        and passing it per-call is how one lane ends up resolving `pg_dump`
        differently from another.
        """
        self.close_session()
        self._sandbox_params = sandbox_params
        self._target_params = target_params
        self._mode = mode
        self._postgres_bin_dir = postgres_bin_dir or ""
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
        """Whether the §18.5 D3a **Check** gesture can RUN.

        The host binds the Check *button*'s presence to this (carve-out 2's "no
        dead controls": with no live `SandboxSession` there is no button, the
        same posture as the absent apply row) and never its enabled state. Since
        FQ-023 it is no longer the host's *menu* gate: a Check menu entry is
        present whenever a sandbox is configured and refuses with a stated reason
        when this is False, because a menu entry can say why and a button
        cannot. It is deliberately a separate name from
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
    def postgres_bin_dir(self) -> str:
        """The project's recorded *Locate postgres binaries* folder, `""` for
        PATH-only (FQ-260812025353)."""
        return self._postgres_bin_dir

    def _bin_dir(self) -> str | None:
        """`self._postgres_bin_dir` in the spelling `db/sandbox.py` takes:
        `None` for "PATH only", never `""`.

        Read on the GUI thread and captured into each worker's closure, never
        read from inside one -- a project transition while an operation is in
        flight must not change which binaries that operation resolves
        halfway through."""
        return self._postgres_bin_dir or None

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
            self._capabilities or _NOT_PROBED,
            self._mode,
            self._configured,
            bin_dir=self._bin_dir() or "",
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

        bin_dir = self._bin_dir()

        def work() -> SandboxCapabilities:
            return self._prober(params, bin_dir=bin_dir)

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

        Once a session is open it also runs `purge_orphaned_alter_rows`
        (DEC-008) on the same worker thread -- the one-time sweep of
        bookkeeping rows written before BUG-044, which no request can key onto
        any more. Best-effort: see the call site for why a failed sweep must
        not fail the open.
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

        bin_dir = self._bin_dir()

        def work() -> tuple[SandboxSession | None, SandboxCapabilities, str | None]:
            caps = self._prober(params, bin_dir=bin_dir)
            reason = self._blocking_reason(caps)
            if reason is not None:
                return None, caps, reason
            session = self._opener(
                params,
                mode=mode,
                schema_names=schema_names,
                baseline=baseline,
                target_params=target_params,
                postgres_bin_dir=bin_dir or "",
            )
            # DEC-008: drop the pre-BUG-044 alter bookkeeping rows, once per
            # session open, on this worker thread (never on the GUI one).
            # **Best-effort on purpose** -- those rows are inert since BUG-044
            # (no request can key onto them any more), so failing to sweep
            # them is hygiene lost, not correctness lost, and refusing to open
            # the sandbox over it would trade a real capability for a tidy
            # table.
            try:
                self._purge_orphans(session)
            except Exception:  # noqa: BLE001, S110 -- see above; never blocks the open
                pass
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
        self._announce_session(False)

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

        bin_dir = self._bin_dir()

        def work() -> tuple[SandboxSession, BaselineSnapshot | DatabaseSchema]:
            if admin_params is not None and database_name is not None:
                self._database_creator(admin_params, database_name)
            snapshot = self._snapshotter(target_params)
            session = self._provisioner(
                snapshot,
                params,
                mode,
                target_params=target_params,
                postgres_bin_dir=bin_dir or "",
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

    def provision_new_database(
        self,
        on_done: Callable[[SandboxOperationResult], None] | None = None,
        *,
        admin_params: ConnectionParams,
        name_candidates: Sequence[str],
    ) -> None:
        """§18.2's New Project sandbox step (FQ-007): **create** a brand-new
        app-owned sandbox database, provision it, install `plpgsql_check`, and
        hold the resulting session -- one operation, off the GUI thread, reported
        as `PROVISION` with the created name on `SandboxOperationResult`.

        The one piece of behavior that is new here rather than in `db/sandbox.py`
        is *which* name gets created: `name_candidates` is walked in order and the
        **first free one wins**. A name already taken on the server raises
        `duplicate_database` from `create_sandbox_database`, which is caught (see
        `is_duplicate_database_error`) and answered with the next candidate;
        anything else is a real failure and propagates. Exhausting the list is
        `SandboxNameCollisionError`.

        **Nothing is ever destroyed, so nothing needs confirming.** Unlike
        `provision`, this does not go through `confirm_destructive`: it writes
        only into a database it created microseconds earlier, an existing
        database is *skipped* rather than reused or dropped (FQ-007 rejects both
        of those branches), and the exhausted-candidates case fails without
        touching anything. `provision`/`run_data_clone`/`reset_session` -- the
        operations that really do overwrite a sandbox -- keep their gate exactly
        as it was.

        The baseline comes from the project's **target** profile via
        `snapshot_for_baseline`, as D2 specifies. A brand-new project may not have
        a target yet; rather than fail (or connect to nothing), the sandbox is
        provisioned from an **empty** `BaselineSnapshot` -- still a real,
        app-owned, bookkeeping-equipped sandbox -- and the result says so
        (`_NO_TARGET_BASELINE_NOTE`). For the same reason a `WITH_DATA` request
        with no target is provisioned schema-only and **recorded** as
        schema-only, because the recorded mode is what a later `reset()` re-runs.

        `plpgsql_check` is installed in the same operation, gated by the pure
        `install_gate` and never re-litigated here. A refused or failed install
        does **not** fail the operation: the sandbox exists and works, tier 3
        merely cannot lint, so the gate's own reason string rides along on the
        successful result -- §18's graceful-degradation posture, not an error.
        """
        candidates = [name for name in (name_candidates or ()) if name]
        if not candidates:
            self._finish(
                SandboxOperation.PROVISION, False, _NO_NAME_CANDIDATES_REASON, on_done
            )
            return
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
        has_target = target_params is not None and bool(target_params.host)
        # The RECORDED mode (D2a) is the user's choice and is not rewritten here;
        # what can change is only what this one run was able to do. A "with data"
        # sandbox with no target to clone from is provisioned schema-only for
        # now, and the result says so -- the recorded intent survives, so a later
        # data clone (once a target exists) is still the mode the project asks
        # for, and the honest tier keeps reflecting that recorded choice.
        mode = self._mode
        notes: list[str] = []
        if mode is SandboxMode.WITH_DATA and not has_target:
            mode = SandboxMode.SCHEMA_ONLY
            notes.append(_WITH_DATA_NEEDS_TARGET_NOTE)

        bin_dir = self._bin_dir()

        def work():
            created = self._create_first_free_database(admin_params, candidates)
            sandbox_params = replace(params, database=created)
            local_notes = list(notes)
            if has_target:
                snapshot = self._snapshotter(target_params)
            else:
                snapshot = BaselineSnapshot()
                local_notes.append(_NO_TARGET_BASELINE_NOTE)
            session = self._provisioner(
                snapshot,
                sandbox_params,
                mode,
                target_params=target_params if has_target else None,
                postgres_bin_dir=bin_dir or "",
            )
            caps = self._prober(sandbox_params, bin_dir=bin_dir)
            offered, reason = install_gate(caps)
            if offered:
                try:
                    self._installer(session)
                except Exception as exc:  # noqa: BLE001 -- degrade, never abort
                    local_notes.append(
                        "plpgsql_check was not installed: "
                        f"{str(exc) or exc.__class__.__name__}"
                    )
                else:
                    caps = self._prober(sandbox_params, bin_dir=bin_dir)
            elif caps.plpgsql_check_state != "installed":
                local_notes.append(f"plpgsql_check was not installed: {reason}")
            return created, sandbox_params, session, snapshot, caps, local_notes

        def on_result(outcome) -> None:
            created, sandbox_params, session, snapshot, caps, local_notes = outcome
            # Adopt what was actually created, so `capability_status()` and the
            # recorded settings can never describe a different database than the
            # one this controller now holds a session on.
            self._sandbox_params = sandbox_params
            self._configured = True
            self._capabilities = caps
            self._baseline = snapshot
            self._schema_names = getattr(session, "schema_names", frozenset())
            self._set_session(session)
            self._finish(
                SandboxOperation.PROVISION,
                True,
                " ".join(note for note in local_notes if note),
                on_done,
                caps,
                database_name=created,
            )

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.PROVISION, on_done
        ))

    def _create_first_free_database(
        self, admin_params: ConnectionParams, candidates: Sequence[str]
    ) -> str:
        """`create_sandbox_database` the first candidate name that is free, and
        return it. Runs on the worker thread; raises
        `SandboxNameCollisionError` when every candidate is taken and re-raises
        anything that is not a name collision."""
        taken: list[str] = []
        for name in candidates:
            try:
                self._database_creator(admin_params, name)
            except Exception as exc:  # noqa: BLE001 -- only collisions are retried
                if not is_duplicate_database_error(exc):
                    raise
                taken.append(name)
                continue
            return name
        raise SandboxNameCollisionError(taken)

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

        bin_dir = self._bin_dir()

        def work() -> None:
            self._cloner(target_params, sandbox_params, bin_dir=bin_dir)

        def on_result(_ignored) -> None:
            self._finish(SandboxOperation.CLONE_DATA, True, "", on_done)

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.CLONE_DATA, on_done
        ))

    def install_plpgsql_check(
        self, on_done: Callable[[SandboxOperationResult], None] | None = None
    ) -> None:
        """Run `CREATE EXTENSION IF NOT EXISTS plpgsql_check` through the live
        session -- §18.8's Sandbox2 action button, which is the app's one
        one-click install since `Sandbox Setup…` was deleted (§18.5 D2).

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

        bin_dir = self._bin_dir()

        def work() -> tuple[object, SandboxCapabilities]:
            caps = (
                cached_caps
                if cached_caps is not None
                else self._prober(params, bin_dir=bin_dir)
            )
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
            self._report(result, on_done)

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.CHECK, on_done
        ))

    def run_apply(
        self,
        request: object,
        on_done: Callable[[SandboxOperationResult], None] | None = None,
        *,
        ddl_text: str | None = None,
        probe: bool = False,
    ) -> None:
        """**Check and commit to sandbox** (§18.5 D3): apply one object's DDL to the live
        sandbox and run the whole ladder over it, in one transaction.

        Mirrors `run_check` exactly -- same session precondition, same
        `_run_async` seam, same `SandboxOperationResult`/`operation_finished`
        path, same duck-typed reading of the report -- and differs only in which
        `db/ddl_check.py` entry point it calls. **No SQL and no ladder logic live
        here**: `apply_and_check` composes the statement list and `db/apply.py`
        runs it.

        `probe=True` switches to D3's *"Check without applying"* probe
        (`probe_check`), which runs the identical ladder rolled back. It is a
        flag rather than a second method because the two differ in exactly one
        boolean, and the difference is reported as data (`CheckReport.committed`
        plus the probe caveat) rather than inferred by the caller from which
        method it happened to call.

        `ddl_text` defaults to the request's own `buffer_text`.

        **`confirm_destructive` is never consulted** -- `APPLY` is not in
        `DESTRUCTIVE_OPERATIONS` (see `SandboxOperation.APPLY` for the full
        argument). The confirmation an apply needs names the *object* and belongs
        to the panel that invoked it.

        `ok` means **the whole ladder ran green and the transaction committed**:

        | Situation | `ok` | `reason` | `report` |
        |---|---|---|---|
        | every tier passed, committed | True | empty | the report |
        | a tier found something | False | that tier's own reason | the report |
        | a tier could not run | False | that tier's own reason, verbatim | the report |
        | it applied but was rolled back (or `probe=True`) | False | the rollback/probe caveat | the report |
        | no live session | False | `_NO_SESSION_REASON` | None |
        | the worker raised | False | the exception's message | None |
        """
        session = self._session
        if session is None:
            self._finish(SandboxOperation.APPLY, False, _NO_SESSION_REASON, on_done)
            return
        if request is None:
            self._finish(
                SandboxOperation.APPLY, False, _NO_APPLY_REQUEST_REASON, on_done
            )
            return

        cached_caps = self._capabilities
        params = session.params
        run_ladder = self._probe_checker if probe else self._applier

        bin_dir = self._bin_dir()

        def work() -> tuple[object, SandboxCapabilities]:
            caps = (
                cached_caps
                if cached_caps is not None
                else self._prober(params, bin_dir=bin_dir)
            )
            return run_ladder(session, request, caps, ddl_text=ddl_text), caps

        def on_result(outcome: tuple[object, SandboxCapabilities]) -> None:
            report, caps = outcome
            self._capabilities = caps
            ok, reason = self._apply_outcome(report, probe=probe)
            result = SandboxOperationResult(
                operation=SandboxOperation.APPLY,
                ok=ok,
                reason=reason,
                capabilities=caps,
                report=report,
            )
            self._report(result, on_done)

        self._run_async(work, on_result=on_result, on_error=self._error_handler(
            SandboxOperation.APPLY, on_done
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
        self._announce_session(True)

    def _blocking_reason(self, caps: SandboxCapabilities) -> str | None:
        """Why a session cannot be opened against `caps`, or None.

        Reuses `determine_project_tier`'s reasons verbatim (unreachable, tools
        missing, not configured) and `install_gate`'s exact superuser sentence
        -- no reason string is authored here. Superuser is checked *between*
        those two because it is a property of the connection, while the tools
        check is about the machine, and the more specific cause reads better
        first.
        """
        status = determine_project_tier(
            caps, self._mode, self._configured, bin_dir=self._bin_dir() or ""
        )
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
    def _apply_outcome(report: object, *, probe: bool) -> tuple[bool, str]:
        """`(ok, reason)` for one `CheckReport` produced by an **apply**, read
        duck-typed like `_check_outcome`.

        Stricter than `_check_outcome` in the two ways an apply is stricter: it
        requires **every** tier to have passed (`green`, §18.5 D3's hard rule --
        an unavailable tier is never folded into the OK state), and it requires
        the transaction to have **committed**, because "it compiled and was rolled
        back" must never be reported as a successful apply. A probe is expected
        not to commit, so it is reported as `ok=False` with the reason saying so
        rather than as a failure of the DDL.
        """
        green = bool(getattr(report, "green", False))
        committed = bool(getattr(report, "committed", False))
        if not green:
            unverified = [
                f"{name}: {status} ({reason})"
                for name, status, reason in _tier_rows(report)
                if status != "passed"
            ]
            return False, "; ".join(unverified) or (
                "the ladder reported nothing about this object -- nothing was "
                "verified."
            )
        if probe:
            return False, _PROBE_NOT_APPLIED_REASON
        if not committed:
            return False, _NOT_COMMITTED_REASON
        return True, ""

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
        database_name: str = "",
    ) -> None:
        result = SandboxOperationResult(
            operation=operation,
            ok=ok,
            reason=reason,
            capabilities=capabilities,
            database_name=database_name,
        )
        # BUG-043: a worker can land after its receivers are gone. Nothing in
        # the app cancels an in-flight sandbox operation when a project closes
        # or the window is destroyed, so `on_done` may be a bound method of a
        # dead panel and `self` may be a QObject whose C++ side went with its
        # parent window -- both raise `RuntimeError` ("Internal C++ object
        # already deleted" / "Signal source has been deleted"). There is no
        # one left to report the outcome TO at that point, so dropping it is
        # the correct answer; what is not correct is raising out of a queued
        # slot, where Qt has no caller to hand the exception to (under pytest
        # it surfaces as a teardown error charged to an unrelated test).
        # `on_done` runs BEFORE the emit, so both need the guard, separately:
        # a dead panel must not cost the still-live window its signal.
        self._report(result, on_done)

    def _report(
        self,
        result: SandboxOperationResult,
        on_done: Callable[[SandboxOperationResult], None] | None,
    ) -> None:
        """Announce one finished operation to whoever is still there to hear it.

        The single delivery point for `on_done` + `operation_finished`, because
        BUG-043 showed the pair had been open-coded in three places (`_finish`
        and the `run_check`/`run_apply` result callbacks) and a guard added to
        one of them would have left the other two raising.
        """
        if on_done is not None:
            try:
                on_done(result)
            except RuntimeError as exc:
                _log.debug(
                    "sandbox %s: on_done receiver is gone (%s)", result.operation, exc
                )
        try:
            self.operation_finished.emit(result)
        except RuntimeError as exc:
            _log.debug("sandbox %s: signal source is gone (%s)", result.operation, exc)

    def _announce_session(self, present: bool) -> None:
        """`session_changed`, guarded the same way and for the same reason.

        Not a duplicate of `_report`'s guard but the other half of it: a
        SUCCESSFUL open landing after teardown never reaches `_report` -- it
        raises here first, at `_set_session`. The filed bug only ever saw the
        failure path (a refused connection), so guarding `_finish` alone would
        have left the success path raising exactly as before.
        """
        try:
            self.session_changed.emit(present)
        except RuntimeError as exc:
            _log.debug("sandbox: session_changed source is gone (%s)", exc)
