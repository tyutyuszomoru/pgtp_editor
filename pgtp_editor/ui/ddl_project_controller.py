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
"""The **local DDL-versioning project** lane (spec §18.2): New / Open / Close
Project, Project Settings, the `.pgtp` link and its deploy, the top-of-§18
capability probe and BUG-030's target-reachability probe.

A "project" here is a plain chosen FOLDER carrying a `.ddlproject/settings.json`
marker — deliberately a different concept from the open `.pgtp` document
(``PgtpDocumentController``). One can exist without the other, and the
relationship between them is exactly the three methods described below.

What it owns
------------
* :attr:`folder` / :attr:`settings` — the active project, or ``None``/``None``;
* :attr:`capability_status` — the top-of-§18 tier/capability probe's last
  result, re-run on every project open/create and on demand from §18.8;
* :attr:`target_probe_error` — BUG-030's last target-connection reachability
  result: ``None`` means "the last probe succeeded (or there was nothing to
  probe)", a string is the failure text ``test_connection`` reported.
  Deliberately optimistic before the first result lands so a healthy target
  never flashes red;
* :attr:`probe_sandbox_capabilities` — the ``db/sandbox.py::probe`` seam, an
  ATTRIBUTE so the suite can hand back canned ``SandboxCapabilities`` and never
  open a connection. The host's ``SandboxController`` is pointed at this very
  attribute, so the whole window probes through exactly one seam.

``MainWindow`` keeps ``_ddl_project_folder`` and ``_ddl_project_settings`` as
two of its six permanent delegating properties (a **closed** list), because the
sandbox / DDL-object / Project-Status lanes read and write them from ~40 places
and they move out in later waves.

The `.pgtp`-link triangle
-------------------------
Three methods make a `.pgtp` and a project into one artifact, and they are why
this lane and the document lane were extracted together:

1. :meth:`resolve_pgtp_path` — **before** any load, an open of the linked
   sshfs source is redirected to the local working copy;
2. :meth:`link_pgtp_if_needed` — the first open of a `.pgtp` while a project is
   active *creates* that working copy and repoints the document's path at it;
3. :meth:`auto_open_linked_pgtp` — opening a project loads its linked `.pgtp`
   back into the editor (BUG-021).

The copy itself lives in exactly one place, :func:`check_out_pgtp`, because a
`.pgtp` can also be attached in the New Project dialog (FQ-035) and §18.2
requires **one definition of linking** for both routes. (2) is the open-time
entry point onto it; :meth:`create_project` is the creation-time one.

All three read the link through one predicate, :meth:`_linked_working_copy`
(BUG-260810173246): a recorded ``working_copy_path`` with no file behind it is
**not a link**, so it is honoured by nobody — (1) passes the source through
untouched instead of redirecting an open at a missing file, (3) says so and falls
back to its folder scan, and (2) treats the project as unlinked so the next open
of the *same* source repairs it. Repointing at a *different* source stays
forbidden.

(1) and (2) are called by the document lane through injected callables; (3)
calls the document lane back through ``open_pgtp_file``. Because every provider
is a callable resolved at CALL time, that cycle needs no two-phase construction
dance — the host simply hands each lane a lambda over the other.

`dataclasses.replace`, never a field-by-field rebuild
-----------------------------------------------------
:meth:`link_pgtp_if_needed` and :meth:`deploy_pgtp` both persist a changed
``ProjectSettings``. They *must* use ``replace``: the hand-listed
``ProjectSettings(...)`` form they once used silently dropped ``sandbox_mode``
back to its default, so linking a `.pgtp` (or deploying it) could quietly turn a
"with data" project into a schema-only one. Copy-with-changes cannot forget a
field. Do not regress this.

Shape
-----
A ``QObject`` following ``ui/coherence_controller.py``: it takes a
:class:`~pgtp_editor.ui.ui_shell.UiShell`, constructs headless, and never
dereferences ``shell.window`` (it appears only as a dialog parent). What the
shell cannot reach is injected as callables, never by importing another
collaborator:

* ``open_pgtp_file`` / ``document_path`` / ``set_document_path`` — the document
  lane's side of the triangle.
* ``bind_sandbox`` / ``provision_sandbox`` — the sandbox lane. A project
  transition rebinds the one ``SandboxController`` (dropping any session that
  belonged to the previous project), and FQ-007 provisions a brand-new
  project's sandbox database at creation time.
* ``target_params`` / ``refresh_status_window`` — the target-connection cluster
  and the §18.8 window, both still host-side.
* ``explorer_schema`` — the DDL Explorer's last-fetched schema, read at close
  time to *remind* about `*`-flagged objects. A reminder at a natural
  checkpoint, never a forced fresh fetch (§18.3).
* ``update_title`` is NOT injected: the title refresh rides the
  ``project_changed`` signal instead, so anything else that must follow a
  project transition can subscribe without this lane learning about it.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QListWidgetItem

from pgtp_editor.db.ddl_project import (
    PgtpLink,
    ProjectSettings,
    compute_drift_markers,
    content_hash,
    is_project_dir,
    load_settings,
    save_settings,
)
from pgtp_editor.db.introspect import test_connection as db_test_connection
from pgtp_editor.db.sandbox import (
    ProjectCapabilityStatus,
    SandboxCapabilities,
    determine_project_tier,
    probe as sandbox_probe,
)
from pgtp_editor.ui import modals
from pgtp_editor.ui.audit_router import SANDBOX_PREFIX
from pgtp_editor.ui.new_project_dialog import NewProjectDialog
from pgtp_editor.ui.project_settings_dialog import ProjectSettingsDialog
from pgtp_editor.ui.ui_shell import UiShell

_log = logging.getLogger(__name__)

#: BUG-260810174919's provisioning narration, all three lines built off ONE
#: stem. The prefix is imported from `audit_router` rather than re-typed: it is
#: the token `classify` routes on, so a second spelling of it would silently
#: mis-route (the reported wording `[sandbox]` lowercase is deliberately NOT
#: adopted -- see the bug's own note; that would be a prefix rename touching
#: classification, not a progress feature).
_PROVISION_NARRATION_STEM = f"{SANDBOX_PREFIX} provision: "
#: The row appended the moment provisioning is dispatched, so the Messages tab
#: says something before the (slow) worker has anything to report.
PROVISION_STARTED_LINE = f"{_PROVISION_NARRATION_STEM}started"
#: How often the heartbeat row is rewritten, in milliseconds. The report asks
#: for one dot per second.
PROVISION_HEARTBEAT_MS = 1000
#: Dots cycle rather than grow without bound: a provision that runs for three
#: minutes would otherwise render a 180-character line. The report asks for an
#: increasing count, which this gives -- it just restarts after ten.
PROVISION_HEARTBEAT_DOT_CAP = 10
#: `SandboxOperation.PROVISION`'s value, as a plain string. NOT imported: this
#: lane may not import another collaborator (`tests/ui/test_collaborator_
#: boundaries.py` enforces it), and cross-lane traffic here is exactly what that
#: rule is about -- the result object arrives on a Qt signal, and reading its tag
#: needs no type from the other lane. `SandboxOperation` is a `str` Enum, so the
#: comparison holds against the enum member itself.
PROVISION_OPERATION = "provision"


def provision_heartbeat_line(ticks: int) -> str:
    """The heartbeat row's text after `ticks` ticks (1-based), dots cycling at
    `PROVISION_HEARTBEAT_DOT_CAP`."""
    dots = (max(int(ticks), 1) - 1) % PROVISION_HEARTBEAT_DOT_CAP + 1
    return _PROVISION_NARRATION_STEM + ("." * dots)


def check_out_pgtp(folder: Path, source_path: Path) -> PgtpLink:
    """**The one copier** (§18.2, `DEC-260810134914`): copy `source_path` into
    `folder` as that project's working copy and return the full three-field
    `PgtpLink`.

    Both ways of linking a `.pgtp` to a project go through here -- the open-time
    one (`DdlProjectController.link_pgtp_if_needed`, a `.pgtp` opened while a
    project is active) and the creation-time one
    (`DdlProjectController.create_project`, a `.pgtp` attached in the New Project
    dialog) -- because §18.2 requires **one definition of linking**, "or the two
    ways of linking would age apart". A second copy routine is exactly what
    `DEC-260810134914` rejected.

    Two deliberate properties, inherited from the open-time path unchanged:

    * **An unreadable source RAISES `OSError`** rather than deciding what to do
      about it. The two callers want opposite things -- the open-time one
      swallows it (nothing to link yet, and a modal at someone who merely opened
      a file is wrong), the creation-time one must NOT (a silent no-op there
      would record an identity pointing at nothing, which is the state the ruling
      forbids). Raising is what lets both keep their own behaviour off one copy.
    * **An existing destination is left alone**, never overwritten. It is already
      a real file at the path being recorded, so the link it produces is whole:
      three fields, all of them true. `last_known_source_checksum` is the
      SOURCE's hash either way, so a destination whose content differs shows up
      as unpushed changes at close -- surfaced, not silently resolved (§18.2).
    """
    working_copy_path = folder / source_path.name
    source_text = source_path.read_text(encoding="utf-8")
    if not working_copy_path.exists():
        working_copy_path.write_text(source_text, encoding="utf-8", newline="")
    return PgtpLink(
        source_path=str(source_path),
        working_copy_path=str(working_copy_path),
        last_known_source_checksum=content_hash(source_text),
    )


class DdlProjectController(QObject):
    """Owns the active §18.2 local project: its folder, settings, capability
    tier and target reachability, plus the `.pgtp` link that ties it to a
    document."""

    #: A project transition: ``(folder, settings)``, both ``None`` after a
    #: close. What the window title (and anything else that must follow the
    #: active project) hangs off.
    project_changed = Signal(object, object)

    #: The top-of-§18 capability probe landed (or was cleared to ``None``
    #: because no project is open). Deliberately NOT wired to a §18.8 re-render
    #: by the host: the status window re-probes on its own triggers, and making
    #: this drive a repaint would be a behavior change, not a move.
    capability_status_changed = Signal(object)

    def __init__(
        self,
        shell: UiShell,
        parent: QObject | None = None,
        *,
        open_pgtp_file: Callable[[str], None],
        document_path: Callable[[], "str | None"],
        set_document_path: Callable[[str], None],
        bind_sandbox: Callable[[], None],
        provision_sandbox: Callable[[object], None],
        target_params: Callable[[], object],
        refresh_status_window: Callable[[], None],
        explorer_schema: Callable[[], object],
        sandbox_controller: object | None = None,
    ):
        super().__init__(parent)
        self._shell = shell
        self._run_async = shell.run_async
        self._open_pgtp_file = open_pgtp_file
        self._document_path = document_path
        self._set_document_path = set_document_path
        self._bind_sandbox = bind_sandbox
        self._provision_sandbox = provision_sandbox
        self._target_params = target_params
        self._refresh_status_window = refresh_status_window
        self._explorer_schema = explorer_schema
        #: The app's one `SandboxController`, handed to Project Settings so its
        #: provisioning group (Provision / Reset / "create a database for me",
        #: which `Database ▸ Sandbox Setup…` used to host) can act. Optional: a
        #: controller built without one still opens the dialog, which then
        #: states why provisioning is unavailable instead of showing dead
        #: buttons.
        self._sandbox_controller = sandbox_controller
        #: BUG-260810174919's provisioning heartbeat: the live `QTimer` while a
        #: New-Project provision is being narrated, None otherwise. "Non-None"
        #: IS the "a heartbeat is running" predicate -- there is exactly one, and
        #: the tick slot no-ops without it.
        self._provision_timer: QTimer | None = None
        #: The single Messages row the heartbeat rewrites in place, and how many
        #: times it has been rewritten. Held as the item itself because
        #: `AuditRouter` hands the very object it was given to the panel, so
        #: `setText` on it animates one row instead of appending a new one per
        #: second (the Messages tab is append-only and refuses removal).
        self._provision_heartbeat_item: QListWidgetItem | None = None
        self._provision_ticks = 0
        # The heartbeat stops when the operation lands. The terminal
        # `[Sandbox] provision: done.` / `... failed: ...` row stays the HOST's to
        # author (`MainWindow._on_sandbox_operation_finished`, connected to this
        # same signal first, so it appends after the dots row) -- one author for
        # the terminal line, no double row.
        finished = getattr(sandbox_controller, "operation_finished", None)
        if finished is not None:
            finished.connect(self._on_sandbox_operation_finished)

        #: Local DDL-versioning project state (spec §18.2) -- deliberately
        #: separate from the open `.pgtp`: a project here is a plain chosen
        #: FOLDER, not necessarily related to any `.pgtp` at all.
        self._folder: Path | None = None
        self._settings: ProjectSettings | None = None
        #: Top-of-§18 tier/capability probe result -- refreshed automatically
        #: whenever a project is opened/created, and on demand by the §18.8
        #: Project Status screen via `refresh_capability_status`. None until the
        #: first probe completes for the currently-open project.
        self._capability_status: ProjectCapabilityStatus | None = None
        #: BUG-030: last target-connection reachability probe result. See the
        #: module docstring for why None is the optimistic default.
        self._target_probe_error: str | None = None

        #: Injectable seam (mirrors `CoherenceController.fetch_schema`) -- an
        #: ATTRIBUTE, because tests replace it with a canned
        #: `SandboxCapabilities` so no real connection is ever opened.
        self.probe_sandbox_capabilities = sandbox_probe

        #: The two project-dependent menu actions, handed over once the menus
        #: are built (see `set_close_project_action` / the BUG-024 note on
        #: `set_connection_setup_action`). None until then.
        self._close_project_action = None
        self._connection_setup_action = None

        #: Non-modal dialogs held so they are not GC'd while shown.
        self._new_project_dialog = None
        self._project_settings_dialog = None

    # -- read-only surface ---------------------------------------------------

    @property
    def folder(self):
        """The active project's folder as a `Path`, or None."""
        return self._folder

    @folder.setter
    def folder(self, value) -> None:
        self._folder = value

    @property
    def settings(self):
        """The active project's `ProjectSettings`, or None."""
        return self._settings

    @settings.setter
    def settings(self, value) -> None:
        self._settings = value

    @property
    def capability_status(self):
        """The last top-of-§18 tier/capability probe result, or None."""
        return self._capability_status

    @capability_status.setter
    def capability_status(self, value) -> None:
        self._capability_status = value

    @property
    def target_probe_error(self):
        """BUG-030's last target reachability failure text, or None."""
        return self._target_probe_error

    @target_probe_error.setter
    def target_probe_error(self, value) -> None:
        self._target_probe_error = value

    @property
    def close_project_action(self):
        """File ▸ Close Project, or None before the File menu is built."""
        return self._close_project_action

    @property
    def connection_setup_action(self):
        """Database ▸ Connection Setup…, or None before that menu is built."""
        return self._connection_setup_action

    @property
    def new_project_dialog(self):
        """The live New Project dialog, or None. Held so the non-modal dialog
        outlives the handler's stack frame."""
        return self._new_project_dialog

    @property
    def project_settings_dialog(self):
        """The live Project Settings dialog, or None. Same keep-alive reason."""
        return self._project_settings_dialog

    @property
    def is_open(self) -> bool:
        """Whether a §18.2 project is currently active."""
        return self._folder is not None

    def pgtp_working_copy_path(self) -> "str | None":
        """The active project's `.pgtp` working-copy path, or None when there is
        no project or nothing is linked yet. The document lane's no-`.bak` rule
        reads the link through here rather than duplicating it."""
        if self._settings is None:
            return None
        return self._settings.pgtp.working_copy_path

    # -- construction --------------------------------------------------------

    def set_close_project_action(self, action) -> None:
        """Adopt File ▸ Close Project (starts disabled -- nothing is open yet)."""
        self._close_project_action = action
        action.triggered.connect(self.close_project)
        action.setEnabled(self._folder is not None)

    def set_connection_setup_action(self, action) -> None:
        """Adopt Database ▸ Connection Setup…, whose enabled state is
        projectless-mode-only (BUG-024: once a §18.2 project is open, its own
        `ProjectSettings` is the connection store and this app-level profile
        would be a redundant shadow of it)."""
        self._connection_setup_action = action
        self.refresh_project_dependent_actions()

    # -- New / Open / Close --------------------------------------------------

    def new_project(self, on_ready=None) -> None:
        dialog = NewProjectDialog(parent=self._shell.window)

        def handle() -> None:
            self.create_project(dialog)
            if callable(on_ready):
                on_ready()
            elif self._folder is not None and self._settings is not None:
                # BUG-260810174459: creation checked the attached `.pgtp` out and
                # recorded the link (FQ-035/DEC-260810134914) but never loaded it,
                # so the user attached a file and got an empty editor. Reuse
                # `auto_open_linked_pgtp` -- the SAME loader Open Project uses
                # (BUG-021) -- rather than adding a second load path, and under the
                # same `on_ready` guard: when the caller supplied a continuation
                # (e.g. `require_project`'s "Create..." choice) it has its own
                # `.pgtp` to load next, and auto-opening here too would be the
                # silent double-load BUG-021 guards against.
                #
                # It runs HERE rather than inside `create_project` for the journal
                # ordering `create_project` documents: the project is already
                # active, so the `[Project]` rows this may file (missing working
                # copy, multiple candidates) survive the transition that would
                # have wiped them (FQ-019/BUG-042).
                self.auto_open_linked_pgtp(self._folder, self._settings)

        dialog.accepted.connect(handle)
        self._new_project_dialog = dialog
        dialog.show()

    def create_project(self, dialog) -> None:
        folder = Path(dialog.folder())
        folder.mkdir(parents=True, exist_ok=True)
        # DEC-260810134914: the attached `.pgtp` is checked out HERE, BEFORE
        # `ProjectSettings` exists -- so the link is recorded only if the copy
        # succeeded, and the "attached but not linked" state (a recorded identity
        # pointing at nothing) is unreachable rather than tolerated. Same
        # ordering rule the sandbox step below follows for the same reason.
        pgtp_link, pgtp_failure = self._check_out_attached_pgtp(dialog, folder)
        settings = ProjectSettings(
            name=dialog.name(),
            description=dialog.description(),
            # FQ-035: creation now records the `.pgtp` link and the quality
            # (target) connection the dialog collected, instead of leaving both
            # at their empty defaults until first open or Project Settings. Both
            # are empty when the user ignored the optional `.pgtp` field, so a
            # sandbox-only project is created byte for byte as before.
            pgtp=pgtp_link,
            target=dialog.target_params(),
            sandbox=dialog.sandbox_params(),
            sandbox_mode=dialog.sandbox_mode(),
            git=dialog.git_config(),
        )
        # ONE settings write, as before: the sandbox-provisioning callback below
        # re-saves with the created database name, and a third writer to
        # `settings.json` in one flow is how those come to disagree.
        save_settings(folder, settings)
        self.set_active_project(folder, settings)
        self._shell.status(f"Created project: {folder}", 5000)
        # Both notices are filed AFTER `set_active_project`, never before: a
        # `[Project]` row is journalled, and the project transition REPLACES the
        # journal's display buffer (FQ-019/BUG-042) -- so a row emitted earlier in
        # this method would be wiped off screen by the very creation it describes.
        if pgtp_failure:
            self._shell.audit.addItem(QListWidgetItem(pgtp_failure))
        self._report_quality_advisory(dialog)
        # FQ-007: the sandbox step CREATES and provisions the sandbox database
        # now, rather than recording a name the user typed. Last, so a failed
        # sandbox never costs the user the project (§18's tier-2 degrade).
        #
        # BUG-260810174919: the narration starts BEFORE the dispatch, and on the
        # same condition the host's provisioning step uses to decide whether it
        # dispatches at all -- a sandbox-less project (blank sandbox group) is a
        # perfectly good tier-2 project and must not be narrated as if a database
        # were being built. Starting before the call also matters for the
        # synchronous `_run_async` tests inject: with it, the whole operation
        # completes inside `_provision_sandbox`, so a heartbeat started afterwards
        # would have nothing left to stop it.
        if settings.sandbox.host:
            self.begin_provision_narration()
        self._provision_sandbox(dialog)

    def _check_out_attached_pgtp(self, dialog, folder: Path) -> "tuple[PgtpLink, str]":
        """The `PgtpLink` a New Project accept records, plus the Audit line to
        file if the copy failed (FQ-035, §18.2, `DEC-260810134914`): the attached
        `.pgtp` is copied into `folder` through the ONE copier
        (`check_out_pgtp`), so creation produces exactly the same three fields the
        open-time path produces.

        No attachment -> an empty `PgtpLink`, i.e. today's sandbox-only project
        byte for byte.

        The failure line is RETURNED rather than filed here because this runs
        before the project is active, and a `[Project]` row filed before that
        transition is wiped from the journal by it -- `create_project` files it
        once the project exists.

        **A copy that fails costs the link, never the project.** The creation path
        deliberately does NOT inherit the open-time copier's silent-no-op on an
        unreadable source: it reports through the Audit panel and creates the
        project with **no `pgtp` link at all** -- *a recorded identity that points
        at nothing is worse than no record at all* (`DEC-260810134914`, with
        DEC-007/DEC-008). The user can still attach the file afterwards by opening
        it, which is the path that ships today, and the `working_copy_path` guard
        in `link_pgtp_if_needed` is left clear so that open really does link it.
        """
        source_path = dialog.pgtp_path()
        if not source_path:
            return PgtpLink(), ""
        try:
            return check_out_pgtp(folder, Path(source_path)), ""
        except OSError as exc:
            return PgtpLink(), (
                f"[Project] Could not copy the attached .pgtp into the project "
                f"({source_path}: {exc}) -- the project was created with NO .pgtp "
                "link. Open that file while this project is active to link it."
            )

    def _report_quality_advisory(self, dialog) -> None:
        """DEC-260810134915: creation is **never gated** on the quality (target)
        connection -- but where the app declines to gate something it still owes
        the user a statement of what it noticed, so a blank or never-tested
        quality section is said **once**, here, at creation.

        It lands in the Audit panel (FQ-019's `[Project]` journal), not at the
        caret and not in a modal: DEC-013's at-the-caret rule is about a REFUSAL
        answering a keystroke, and this is the opposite -- a notice about an
        action that succeeded. Project creation's own narration already lives in
        this journal (drift on open, the multiple-`.pgtp` report, the pending-
        deploy reminder), and that is also where it stays readable after the
        transient status line has gone.
        """
        advisory = dialog.quality_advisory()
        if advisory:
            self._shell.audit.addItem(QListWidgetItem(f"[Project] {advisory}"))

    # -- provisioning narration (BUG-260810174919) ---------------------------

    def begin_provision_narration(self) -> None:
        """Say that sandbox provisioning has started, and start the once-a-second
        heartbeat that keeps saying it is still going.

        **Why here, and why the Messages tab.** Provisioning creates a database,
        snapshots a baseline, provisions, probes and installs `plpgsql_check` --
        seconds to minutes against a real server -- and until now the run said
        nothing at all until its single terminal line. That terminal line is a
        `[Sandbox]` row, and `audit_router.py` routes `[Sandbox]` to the **bottom
        Messages tab** (accumulated, and specifically NOT the journal, because
        these rows are emitted across a project transition that replaces the
        journal's display buffer). Progress about the same operation goes to the
        same place, through the same prefix: no second destination, no new prefix.

        **The rows are journalled only in the sense Messages is** -- accumulated
        on the tab, not written into the Activity Log -- which is the honest
        lifetime for a heartbeat: a burst of durable journal rows saying "." is
        noise, while one Messages row that keeps its final state as history is
        readable. That is achieved by rewriting **one** row in place rather than
        appending per tick: the Messages tab is append-only and `takeItem`
        refuses removal, so the animation has to be a `setText` on a held item.

        **The rows carry NO item roles, i.e. they are unclickable** (§18.5
        carve-out 6): narrative lines get the same treatment as `[SQL]` refusals
        and the `[Find]` summary line. There is nothing to navigate to -- a
        heartbeat has no source location -- and leaving roles unset by accident
        is exactly what this sentence exists to prevent.

        **Not worker progress.** `ui/async_task.py` has no progress channel and
        `work()` runs on a thread pool that must not touch widgets, so the
        heartbeat is a GUI-thread `QTimer` parented to this controller, started at
        dispatch and stopped when `operation_finished` lands.
        """
        self.end_provision_narration()
        self._shell.audit.addItem(QListWidgetItem(PROVISION_STARTED_LINE))
        self._provision_heartbeat_item = None
        self._provision_ticks = 0
        timer = QTimer(self)
        timer.setInterval(PROVISION_HEARTBEAT_MS)
        # A named slot, never a lambda: under the offscreen test platform a real
        # one-second clock is not something a test can wait on, so the tick has
        # to be directly invokable.
        timer.timeout.connect(self.tick_provision_narration)
        self._provision_timer = timer
        timer.start()

    def tick_provision_narration(self) -> None:
        """One heartbeat: rewrite the single progress row with one more dot.

        No-ops when no heartbeat is running, which is what makes a late tick
        harmless. The `setText` is wrapped for `RuntimeError` for BUG-043's
        reason: the panel (or the item's C++ side) can be gone while a timer that
        outlived its window is still firing, and raising out of a queued slot has
        no caller to hand the exception to.
        """
        if self._provision_timer is None:
            return
        self._provision_ticks += 1
        text = provision_heartbeat_line(self._provision_ticks)
        try:
            if self._provision_heartbeat_item is None:
                item = QListWidgetItem(text)
                self._shell.audit.addItem(item)
                self._provision_heartbeat_item = item
            else:
                self._provision_heartbeat_item.setText(text)
        except RuntimeError as exc:  # the panel/item went with its window
            _log.debug("provision heartbeat: surface is gone (%s)", exc)
            self.end_provision_narration()

    def end_provision_narration(self) -> None:
        """Stop the heartbeat and forget its row. Idempotent.

        Deliberately writes **no** terminal line: `[Sandbox] provision: done.` /
        `... failed: ...` already has exactly one author in the host's
        `operation_finished` receiver, and adding a second here would double the
        row. The dots row is left where it is and becomes history.
        """
        timer = self._provision_timer
        self._provision_timer = None
        self._provision_heartbeat_item = None
        self._provision_ticks = 0
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except RuntimeError as exc:  # already torn down with the window
                _log.debug("provision heartbeat: timer is gone (%s)", exc)

    def _on_sandbox_operation_finished(self, result) -> None:
        """Stop the heartbeat when the provision it was narrating lands.

        Gated on both "a heartbeat is running" and "this is a PROVISION": this
        receiver sees every sandbox operation of every project, and a Check or an
        Apply finishing mid-provision must not silence the run in progress.
        Success and failure both arrive here -- the error path goes through the
        same `_finish`/`operation_finished` -- so one stop point covers both.
        """
        if self._provision_timer is None:
            return
        if getattr(result, "operation", None) != PROVISION_OPERATION:
            return
        self.end_provision_narration()

    def open_project(self, on_ready=None) -> None:
        folder = modals.QFileDialog.getExistingDirectory(
            self._shell.window, "Open Project Folder", "",
            modals.QFileDialog.Option.ShowDirsOnly,
        )
        if not folder:
            return
        folder_path = Path(folder)
        # BUG-022: Open requires a REAL project folder -- one already
        # carrying the `.ddlproject/settings.json` marker. Loading
        # `load_settings` unconditionally on any folder silently returns a
        # default ProjectSettings() for a folder that was never a project;
        # reject that instead of guessing.
        if not is_project_dir(folder_path):
            modals.QMessageBox.warning(
                self._shell.window,
                "Not a Project Folder",
                f"{folder_path} is not a PGTP DDL project folder "
                "(no .ddlproject/settings.json marker found).",
            )
            return
        settings = load_settings(folder_path)
        self.set_active_project(folder_path, settings)
        self.report_project_drift(folder_path, settings)
        self._shell.status(f"Opened project: {folder_path}", 5000)
        if callable(on_ready):
            on_ready()
        else:
            # BUG-021: opening a project should auto-open its linked .pgtp
            # into the editor -- but only on a plain Open Project (on_ready
            # is None). When on_ready IS set, the caller (e.g. the document
            # lane's "Open Project…" choice, or `require_project`) already has
            # its own specific .pgtp to load; auto-opening the linked working
            # copy here too would be a silent double-load racing against that
            # caller's own load.
            self.auto_open_linked_pgtp(folder_path, settings)

    def auto_open_linked_pgtp(self, folder_path: Path, settings) -> None:
        """BUG-021: a project's linked `.pgtp` should populate the editor the
        moment the project is opened, not require a separate manual File >
        Open. Reuses the document lane's existing loader -- never reinvents
        loading.

        Scope, exactly as triaged: **zero** candidates -> silent no-op (no
        error, nothing to open yet); **one** -> auto-open it; **multiple**
        unlinked candidates -> report via the Audit panel rather than
        guessing which one the user means.

        **BUG-260810173246:** the `return` used to sit OUTSIDE the `exists()`
        branch, so a recorded-but-missing working copy silently suppressed the
        candidate scan below -- the project opened with nothing loaded and no
        explanation, even though the scan would very often have found the copy
        the user still has. A missing working copy now files one Audit line and
        **falls through** to the scan. If the scan opens a single candidate,
        `link_pgtp_if_needed` re-creates the link from it: the two steps are one
        self-healing behaviour, not two coincidences."""
        working_copy_path = settings.pgtp.working_copy_path
        if working_copy_path:
            if self._linked_working_copy(settings.pgtp) is not None:
                self._open_pgtp_file(working_copy_path)
                return
            self._shell.audit.addItem(
                QListWidgetItem(
                    f"[Project] The linked .pgtp working copy is missing "
                    f"({working_copy_path}) -- the link will be re-created the "
                    "next time you open the source."
                )
            )
        # Not yet linked (or the recorded copy is gone) -- fall back to scanning
        # the project folder itself for a `.pgtp` the user may have dropped in
        # directly.
        candidates = sorted(folder_path.glob("*.pgtp"))
        if not candidates:
            return  # zero -- nothing to do
        if len(candidates) == 1:
            self._open_pgtp_file(str(candidates[0]))
            return
        # Multiple unlinked candidates: never guess -- surface via Audit.
        names = ", ".join(path.name for path in candidates)
        self._shell.audit.addItem(
            QListWidgetItem(
                f"[Project] Multiple .pgtp files found in {folder_path} "
                f"({names}) -- open one explicitly via File > Open."
            )
        )

    def require_project(self, on_ready) -> None:
        """§18.2: no project-scoped action proceeds silently with none open.
        Offers **Create… / Open… / Cancel**; on Create/Open, `on_ready` runs
        against the newly-active project once it exists. On Cancel, nothing
        happens."""
        if self._folder is not None:
            on_ready()
            return
        box = modals.QMessageBox(self._shell.window)
        box.setWindowTitle("Project Required")
        box.setText("This action needs an open project.")
        create_button = box.addButton("Create…", modals.QMessageBox.ButtonRole.ActionRole)
        open_button = box.addButton("Open…", modals.QMessageBox.ButtonRole.ActionRole)
        box.addButton("Cancel", modals.QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is create_button:
            self.new_project(on_ready=on_ready)
        elif clicked is open_button:
            self.open_project(on_ready=on_ready)

    def set_active_project(self, folder: Path, settings) -> None:
        self._folder = folder
        self._settings = settings
        if self._close_project_action is not None:
            self._close_project_action.setEnabled(True)
        # §18.5 D2: the sandbox controller follows the project. Its
        # `set_project` drops any session that belonged to the previous project;
        # the HOST then opens a fresh one for this project (BUG-040), so a
        # connection is very much a consequence of getting here.
        self._bind_sandbox()
        self.refresh_project_dependent_actions()
        self.project_changed.emit(folder, settings)
        self.refresh_capability_status()

    def refresh_project_dependent_actions(self) -> None:
        """Single place for menu-action enablement that depends on whether a
        §18.2 project is open. Currently just the standalone Connection
        Setup… action (BUG-024: projectless-mode only, since a project's own
        connection lives in Project Settings), called from both
        `set_active_project` and `close_project` so the two transitions can
        never drift apart."""
        if self._connection_setup_action is not None:
            self._connection_setup_action.setEnabled(self._folder is None)

    def close_project(self) -> None:
        """Closing is a reminder point, never a forcing point (§18.3) --
        offers "Deploy .pgtp" if the working copy has unpushed changes, but
        never forces it; closing itself always succeeds."""
        if self._folder is None:
            return
        # BUG-260810174919: a provisioning heartbeat belongs to the project being
        # provisioned. Nothing cancels the in-flight operation, but the ticking
        # must not outlive the project -- a 1 s timer left rewriting a row on a
        # panel that has been cleared (or a window that has gone) is BUG-043's
        # defect class with a clock attached.
        self.end_provision_narration()
        # BUG-042: everything narrated in here is emitted BEFORE
        # `project_changed` (it needs the `_folder`/`_settings` the lines below
        # clear), and FQ-019's journal replaces its display buffer on that
        # transition -- so a `[Project]` line filed only in the journal was
        # wiped off screen by the very close it described. The flag tells
        # `AuditRouter` that these rows are close-time narration: it keeps
        # journalling them into the CLOSING project's file exactly as before and
        # additionally renders them on the Messages tab, which the transition
        # does not clear. Restored in `finally` so a modal that raises cannot
        # leave every later `[Project]` line mis-routed.
        audit = self._shell.audit
        previous = getattr(audit, "project_closing", False)
        try:
            audit.project_closing = True
            self.offer_pgtp_deploy_on_close()
            self.remind_pending_deploys_on_close()
        finally:
            audit.project_closing = previous
        self._folder = None
        self._settings = None
        self._capability_status = None
        self.capability_status_changed.emit(None)
        # BUG-030: the target changes with the project (BUG-024's selection),
        # so the project's probe result must not outlive it as a stale error
        # against the app-level connection.
        self._target_probe_error = None
        # §18.5 D2: no stale session may outlive the project it belonged to --
        # `clear_project` releases it and announces the release, and the
        # refresh inside takes the console and every tab affordance with it.
        self._bind_sandbox()
        if self._close_project_action is not None:
            self._close_project_action.setEnabled(False)
        self.refresh_project_dependent_actions()
        self.project_changed.emit(None, None)
        self._shell.status("Project closed.", 5000)

    def remind_pending_deploys_on_close(self) -> None:
        """Reminds about `*`-flagged DDL objects (locally edited, candidates
        for a batch deploy) -- never opens the deploy-bundle flow
        automatically and never forces a decision (§18.3). Only checks
        objects from the currently-loaded DDL Explorer schema, if any --
        this is a reminder at a natural checkpoint, not a forced fresh
        fetch."""
        schema = self._explorer_schema()
        if schema is None or self._settings is None:
            return
        markers = compute_drift_markers(self._folder, self._settings, schema)
        pending = sum(1 for marker in markers.values() if marker.locally_edited)
        if pending:
            self._shell.audit.addItem(
                QListWidgetItem(
                    f"[Project] {pending} DDL object(s) have local edits pending a batch deploy."
                )
            )

    def offer_pgtp_deploy_on_close(self) -> None:
        link = self._settings.pgtp if self._settings else None
        if link is None or not link.working_copy_path or not link.source_path:
            return
        try:
            working_text = Path(link.working_copy_path).read_text(encoding="utf-8")
        except OSError:
            return
        if content_hash(working_text) == link.last_known_source_checksum:
            return  # nothing pending
        choice = modals.QMessageBox.question(
            self._shell.window,
            "Unpushed .pgtp Changes",
            "This project's .pgtp working copy has changes not yet deployed "
            "to the source. Deploy them now?",
            modals.QMessageBox.StandardButton.Yes | modals.QMessageBox.StandardButton.No,
        )
        if choice == modals.QMessageBox.StandardButton.Yes:
            self.deploy_pgtp()

    # -- probes --------------------------------------------------------------

    def refresh_capability_status(self) -> None:
        """Re-run the top-of-§18 tier/capability probe for the current
        project (reachable local Postgres via `db/sandbox.py::probe`, plus
        -- for a "with data" sandbox -- `pg_dump`/`pg_restore` on `PATH`) and
        store the result on :attr:`capability_status`.

        **Probe timing, settled 2026-08-05:** runs automatically whenever a
        project is opened/created (called from `set_active_project`) and is
        also the entry point the §18.8 "Project Status" screen calls on
        demand -- it is never probed once and cached from creation time, so a
        sandbox that died between sessions is correctly detected and degrades
        the project from tier 3 to tier 2 for this session. No-op (and clears
        the stored status) when no project is open. Runs off the GUI thread so
        an unreachable sandbox host can't freeze the window.

        **BUG-030:** this is the single "re-probe everything the Project
        Status window shows" entry point, so it also probes the *target*
        connection's reachability (below) -- which happens with or without a
        project open, since projectless mode still has an app-level target.
        """
        self.refresh_target_connection_status()
        if self._folder is None or self._settings is None:
            self._capability_status = None
            self.capability_status_changed.emit(None)
            return
        settings = self._settings
        sandbox_params = settings.sandbox
        sandbox_mode = settings.sandbox_mode
        sandbox_configured = bool(sandbox_params.host)

        def do_probe() -> ProjectCapabilityStatus:
            if not sandbox_configured:
                return determine_project_tier(
                    SandboxCapabilities(), sandbox_mode, sandbox_configured=False
                )
            caps = self.probe_sandbox_capabilities(sandbox_params)
            return determine_project_tier(caps, sandbox_mode, sandbox_configured=True)

        def on_result(status: ProjectCapabilityStatus) -> None:
            self._capability_status = status
            self.capability_status_changed.emit(status)

        def on_error(exc: BaseException) -> None:
            # The probe itself never raises (db/sandbox.py::probe's
            # never-raises contract) -- this only guards against a broken
            # injected seam in tests/future callers, never silently swallowed.
            self._shell.audit.addItem(
                QListWidgetItem(f"[Project] Capability probe failed unexpectedly: {exc}")
            )

        self._run_async(do_probe, on_result=on_result, on_error=on_error)

    def refresh_target_connection_status(self) -> None:
        """Re-probe the *target* connection's reachability (BUG-030).

        §18.8's Quality node means "the target is reachable", not merely "a
        target profile exists", so it needs a real `SELECT 1` -- the same
        check the DDL Explorer / coherence path opens -- against the very
        `ConnectionParams` the summary line uses (BUG-024's selection). Runs
        off the GUI thread for the same reason the sandbox probe does: a dead
        host can hang on TCP connect and must never freeze the window. The
        stored result is only *corrected* when the answer lands, and an
        already-open Project Status window is re-rendered then, so nothing
        ever flashes red while the probe is still in flight.
        """
        target = self._target_params()
        if target is None or not target.host:
            # Nothing to reach: `quality_state`'s not-configured branch owns
            # that case, and a host-less profile has not failed -- it has
            # not been tried. Never let a stale error outlive the profile.
            self._target_probe_error = None
            return

        def do_probe() -> "str | None":
            ok, message = db_test_connection(target)
            return None if ok else message

        def on_result(probe_error: "str | None") -> None:
            self._target_probe_error = probe_error
            self._refresh_status_window()

        def on_error(exc: BaseException) -> None:
            # `test_connection` never raises (it returns `(False, msg)`), so
            # this only guards a broken injected seam -- surfaced, never
            # silently swallowed.
            self._shell.audit.addItem(
                QListWidgetItem(f"[Project] Target connection probe failed unexpectedly: {exc}")
            )

        self._run_async(do_probe, on_result=on_result, on_error=on_error)

    def report_project_drift(self, folder: Path, settings) -> None:
        """Opening a project compares the `.pgtp` working copy's checksum
        against the sshfs-mounted source, surfaced (never auto-resolved) via
        the Audit panel -- recomputed fresh on every load, never cached
        (§18.2). The per-object DDL `*`/`!` drift comparison runs alongside
        the DDL Explorer tree it renders onto (§18.2/§18.8, see BrowserPanel).

        BUG-260810173246, two corrections. **A drift verdict needs a WHOLE
        link**: this compares the working copy's world against the source, so a
        project whose `working_copy_path` is empty or points at a deleted file
        has nothing to compare and gets no verdict -- the missing-working-copy
        line filed by `auto_open_linked_pgtp` is the honest report for that
        state. And the *"checksum recorded"* line was **false every time it
        appeared**: nothing in this method ever calls `save_settings`, so it
        claimed a write that did not happen. It now says what is actually true
        -- no checksum is recorded yet. Rewording, not persisting, is the
        deliberate half of that choice: `open_project` writes nothing, and a
        third writer of `settings.json` in the open flow is exactly how these
        records come to disagree (see `create_project`'s single-write note).
        `deploy_pgtp` remains the gesture that records a checksum."""
        link = settings.pgtp
        if not link.source_path:
            return  # no .pgtp linked to this project yet -- nothing to compare
        if self._linked_working_copy(link) is None:
            return  # a half-link: no working copy, so no drift to speak of
        try:
            source_text = Path(link.source_path).read_text(encoding="utf-8")
        except OSError as exc:
            item = QListWidgetItem(f"[Project] Could not read source .pgtp: {exc}")
            self._shell.audit.addItem(item)
            return
        current_checksum = content_hash(source_text)
        if link.last_known_source_checksum is None:
            message = (
                f"[Project] No .pgtp checksum recorded yet for this project "
                f"({link.source_path}) -- recorded by the next Deploy .pgtp."
            )
        elif current_checksum != link.last_known_source_checksum:
            message = (
                f"[Project] Source .pgtp has changed since this project last saw it "
                f"({link.source_path}) -- surfaced, not auto-resolved."
            )
        else:
            message = f"[Project] Source .pgtp unchanged since last opened ({link.source_path})."
        self._shell.audit.addItem(QListWidgetItem(message))

    # -- the `.pgtp` link (§18.2) --------------------------------------------

    def _linked_working_copy(self, link=None) -> "Path | None":
        """BUG-260810173246: the **one** definition of "this project has a
        working copy" — the recorded path AND a real file behind it.

        `check_out_pgtp` is the one copier for the same reason this is the one
        predicate: three separate `.exists()` checks in the three readers
        (`resolve_pgtp_path`, `auto_open_linked_pgtp`, `report_project_drift`)
        would age apart. A `working_copy_path` with no file behind it is **not a
        link** — every reader must treat it as unlinked rather than trusting the
        string, which is what turned an open of a healthy source into a
        parse-error dialog for a file the user never asked for.

        Returns the `Path` when the working copy is really there, else `None`.
        Pass `link` to test a link that is not (yet) the active project's.
        """
        if link is None:
            if self._settings is None:
                return None
            link = self._settings.pgtp
        if not link.working_copy_path:
            return None
        working_copy = Path(link.working_copy_path)
        return working_copy if working_copy.exists() else None

    def resolve_pgtp_path(self, path) -> str:
        """If `path` is the sshfs-mounted source of an ALREADY-linked §18.2
        project, resolve to the local working copy instead -- **every**
        open of the linked source redirects there, not just the first
        (the working copy is the editable truth once linked, §18.2; without
        this, re-opening the source a second time would silently repoint
        saves back at the source, defeating the whole no-`.bak` model).
        Unlinked / no-project cases pass `path` through unchanged -- this is
        also what makes first-time linking possible at all, since
        `link_pgtp_if_needed` needs the ORIGINAL source path.

        **BUG-260810173246: the redirect requires the working copy to EXIST.**
        A recorded path with no file behind it is not a link, so redirecting
        there sent an open of the real, healthy source at a missing file, and
        `load_project`'s `OSError` came back to the user as a `PgtpParseError`
        dialog naming a file they never asked to open -- a missing file
        misdiagnosed as malformed XML. When the working copy is gone we fall
        through and return the source unchanged: the open loads the real file,
        and `link_pgtp_if_needed` then repairs the link. No raise and no prompt
        here -- this runs before EVERY load, including the projectless path."""
        if self._settings is None:
            return str(path)
        link = self._settings.pgtp
        if link.source_path and str(path) == link.source_path:
            working_copy = self._linked_working_copy(link)
            if working_copy is not None:
                return link.working_copy_path
        return str(path)

    def link_pgtp_if_needed(self) -> None:
        """When a `.pgtp` is opened while a project is active and not yet
        linked, this `.pgtp` becomes that project's first-class checked-out
        artifact (§18.2): a local working copy inside the project folder,
        distinct from the sshfs-mounted source, tracked in the project's own
        settings. Subsequent saves redirect to the working copy (this method
        repoints the document's path there). No-op if no project is open or one
        is already linked -- never silently relinked. (Every FUTURE open of the
        linked source is redirected before this method even runs -- see
        `resolve_pgtp_path`.)

        This is the ENTRY POINT for the open-time half of the link; the copy
        itself is `check_out_pgtp`, shared with creation (`DEC-260810134914`).
        The guard belongs to this entry point and must not be relaxed -- it is
        what makes "never silently relinked" true, and `resolve_pgtp_path`
        depends on the two fields being written together.

        **BUG-260810173246 -- what "already linked" means.** The guard now asks
        for a working copy that EXISTS (`_linked_working_copy`), not merely for a
        recorded string. This is *not* a relaxation of `DEC-260810134914`'s "do
        not relax the guard" / §18.2 "The copy at accept -- ONE copier, and the
        broken state is made UNREACHABLE": the ruling forbids relinking a link
        that is **whole**, and a `working_copy_path` with no file behind it is
        not a link at all -- re-creating it is repair, not a silent overwrite.
        Every genuinely linked project still returns early here, untouched.

        Two things the repair deliberately does NOT do:

        * It never repoints a project at a **different** source. When the
          recorded `source_path` names some other file than the `.pgtp` being
          opened, we still return early -- that IS the relink the comment
          forbids, whole link or not. Repair only ever re-copies the *same*
          source the project already claims.
        * It does not prompt. Recording a path was precisely what disabled the
          copier, so a half-link written by a pre-`caed134` build has no UI
          gesture that can repair it; healing on the next open of the source is
          the recovery §18.2 already promises ("the user can still attach the
          file later by opening it")."""
        if self._folder is None or self._settings is None:
            return
        link = self._settings.pgtp
        if self._linked_working_copy(link) is not None:
            return  # a whole link -- never silently relinked
        opened = str(self._document_path())
        if link.source_path and link.source_path != opened:
            # Half-link, but pointing at a different source: repairing it would
            # mean repointing the project, which is the forbidden relink.
            return
        try:
            link = check_out_pgtp(self._folder, Path(self._document_path()))
        except OSError:
            return  # nothing to link yet -- leave the .pgtp unlinked
        settings = self._settings
        # `replace`, not a field-by-field `ProjectSettings(...)` rebuild: the
        # hand-listed form silently dropped `sandbox_mode` back to its default,
        # i.e. linking a `.pgtp` could quietly turn a "with data" project into
        # a schema-only one. Copy-with-changes cannot forget a field.
        updated = replace(settings, pgtp=link)
        save_settings(self._folder, updated)
        self._settings = updated
        self._set_document_path(link.working_copy_path)

    def deploy_pgtp(self) -> None:
        """Push the local `.pgtp` working copy back to the sshfs-mounted
        source -- the explicit gesture that reverses working-copy drift
        (§18.2). Never implied by Save; reachable on-demand (File menu)
        and offered as a close-time convenience prompt."""
        if self._settings is None:
            self._shell.status("No project open.", 5000)
            return
        link = self._settings.pgtp
        if not link.working_copy_path or not link.source_path:
            self._shell.status("No .pgtp linked to this project yet.", 5000)
            return
        try:
            working_text = Path(link.working_copy_path).read_text(encoding="utf-8")
            Path(link.source_path).write_text(working_text, encoding="utf-8", newline="")
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window, "Deploy Failed", f"Could not deploy .pgtp:\n\n{exc}"
            )
            return
        settings = self._settings
        # `replace` for the same reason `link_pgtp_if_needed` uses it: the
        # hand-listed rebuild dropped `sandbox_mode`.
        updated = replace(
            settings,
            pgtp=PgtpLink(
                source_path=link.source_path,
                working_copy_path=link.working_copy_path,
                last_known_source_checksum=content_hash(working_text),
            ),
        )
        save_settings(self._folder, updated)
        self._settings = updated
        self._shell.status(f"Deployed .pgtp to {link.source_path}", 5000)

    # -- Project Settings ----------------------------------------------------

    def open_settings(self) -> None:
        self.require_project(self._show_settings_dialog)

    def _show_settings_dialog(self) -> None:
        # `confirm=None` on purpose: the CONTROLLER owns the single destructive
        # prompt (a controller built without `confirm_destructive` refuses every
        # destructive operation anyway), so passing one here too would ask the
        # user twice for one Provision/Reset.
        dialog = ProjectSettingsDialog(
            self._settings,
            parent=self._shell.window,
            sandbox_controller=self._sandbox_controller,
            project_dir=self._folder,
            confirm=None,
        )
        dialog.accepted.connect(lambda: self._save_settings(dialog))
        self._project_settings_dialog = dialog
        dialog.show()

    def _save_settings(self, dialog) -> None:
        settings = dialog.settings()
        save_settings(self._folder, settings)
        self._settings = settings
        # The sandbox/target profiles may have just changed under a live
        # session: rebind (which drops it) rather than keep a session pointed at
        # a database this project no longer calls its sandbox.
        self._bind_sandbox()
        self._shell.status("Project settings saved.", 5000)
