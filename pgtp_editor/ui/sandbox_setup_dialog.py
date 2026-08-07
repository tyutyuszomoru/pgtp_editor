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

# pgtp_editor/ui/sandbox_setup_dialog.py
"""**Sandbox Setup…** -- §18.5 D2/D2a's provisioning surface.

The sandbox lane had a complete Qt-free backend (`db/sandbox.py`) and a
complete lifecycle host (`ui/sandbox_controller.py`), and **no way for a user
to reach either**: nothing in `ui/` ever created a sandbox database, built a
baseline, cloned data, installed `plpgsql_check` or looked at the `applied`
working set. This dialog is exactly that missing surface.

**It is a VIEW over `SandboxController` and nothing else.** No SQL, no
connection, no `open_sandbox`/`provision_sandbox`/`clone_data`/`reset` call of
its own, no re-derived tier, no re-typed reason string:

- state comes from `controller.capability_status()` (i.e.
  `determine_project_tier`) plus `controller.capabilities`, and the degradation
  is always shown as `ProjectCapabilityStatus.degraded_reason` -- never a bare
  "sandbox unavailable";
- ownership is rendered through `db/sandbox.py::is_app_owned`, and the refusal
  wording is `ForeignDatabaseError`'s own sentence;
- the `plpgsql_check` story is `install_gate`'s verbatim reason (so the
  *"CREATE EXTENSION requires superuser; ask your DBA, …"* sentence is the one
  in `db/sandbox.py`, never retyped here) plus `db/ddl_check.py`'s
  `not_installed_reason` for what tier 3 will consequently report;
- every operation is a controller call, run through the controller's own
  off-GUI-thread path, and its outcome is reported from the returned
  `SandboxOperationResult` -- including its stated `reason` on failure, which is
  never swallowed.

**"With data" / "without data" (D2a) is chosen here and recorded, not
re-derived.** The single store is `ProjectSettings.sandbox_mode`
(`db/ddl_project.py`), written through the injected `settings_saver`
(`save_settings` by default) before the operation starts, and handed to the
controller with `set_project(mode=…)` -- which is what a later `reset()`
re-runs. There is deliberately no second store. Provisioning therefore requires
an open project (`settings=` + `project_dir=`); without one the provisioning
controls are **absent**, with the reason stated where the absence is.

**Nothing destructive happens without a confirmation.** Provision, re-clone and
reset each show `SandboxController.destructive_warning(op)` -- that exact text,
not one composed here -- through the injected `confirm` seam and **abort without
reaching the controller** when it declines. The dialog opens no `QMessageBox`
itself, so no test can reach a modal (§30). Note the controller keeps its own
independent `confirm_destructive` gate: see "Wiring" below for how to have the
user asked exactly once.

**No dead controls (§18.5 carve-out 2).** Controls for operations that cannot
currently run are not created at all; a label states why in the place the
control would have been. That is why the action rows are rebuilt on every
`refresh_state()` rather than enabled/disabled.

**UNWIRED, deliberately.** Nothing constructs this dialog: there is no menu
entry and `ui/main_window.py` is untouched by this module. Wiring:

    # once, at app startup -- the controller is long-lived
    self._sandbox = SandboxController(self, confirm_destructive=self._confirm_wipe)

    # the menu handler (Database ▸ Sandbox Setup…), non-modal like every
    # other dialog in this codebase -- show(), never exec()
    dlg = SandboxSetupDialog(
        self._sandbox,                      # the ONE SandboxController instance
        parent=self,
        settings=self._project_settings,    # ProjectSettings, or None
        project_dir=self._project_dir,      # where save_settings writes
        confirm=None,                       # see below
    )
    dlg.show()

`confirm=None` (the default) means the dialog pre-confirms nothing and the
controller's own `confirm_destructive` is the single prompt -- the user is asked
once, and a decline still surfaces here as the controller's stated
*"cancelled -- this operation was not confirmed. …"* result. Pass `confirm=` when
this dialog should be the prompting surface (a controller built without a
confirmation seam refuses every destructive operation); passing the same
callable to both asks twice.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_check import not_installed_reason
from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.sandbox import (
    SANDBOX_DB_PREFIX,
    AppliedObject,
    ForeignDatabaseError,
    SandboxMode,
    install_gate,
    is_app_owned,
)
from pgtp_editor.ui.async_task import run_async
from pgtp_editor.ui.sandbox_controller import (
    MAINTENANCE_DATABASE,
    SandboxController,
    SandboxOperation,
    sandbox_name_stem,
)

#: The maintenance database `create_sandbox_database` connects to, since
#: PostgreSQL forbids `CREATE DATABASE` inside a transaction block against the
#: database being created. Overridable per-instance. An **alias** of
#: `ui/sandbox_controller.py::MAINTENANCE_DATABASE`, not a second literal --
#: §18.2's New Project step derives its admin connection from the same name.
DEFAULT_MAINTENANCE_DATABASE = MAINTENANCE_DATABASE

_WORKING_SET_COLUMNS = ("Kind", "Schema", "Object", "Table", "Applied at")

_MODE_LABELS = {
    SandboxMode.SCHEMA_ONLY: "without data (schema only)",
    SandboxMode.WITH_DATA: "with data (pg_dump/pg_restore clone)",
}

#: Stated wherever the provisioning controls are absent because there is no open
#: project to record `sandbox_mode` in (§18.5 D2a: the mode is recorded, never
#: re-derived, so there is nowhere to put the choice).
NO_PROJECT_REASON = (
    "No project is open. The sandbox's with-data/without-data mode is recorded "
    "in the project's settings, so provisioning is only offered for an open "
    "project."
)

#: Stated where the "re-run data clone" control would be for a schema-only
#: sandbox. The mode is chosen once at creation time and never toggled (D2a).
SCHEMA_ONLY_CLONE_REASON = (
    "This sandbox was created 'without data' (schema-only). Data cloning is "
    "chosen once at sandbox-creation time, so there is nothing to re-clone."
)

#: Stated where the session-dependent controls would be.
NO_SESSION_REASON = (
    "No sandbox session is open, so the sandbox's contents cannot be read or "
    "changed. Open or provision the sandbox first."
)

#: The incompleteness of the schema-only baseline, stated in the UI rather than
#: buried (§18.5 D2).
BASELINE_CAVEAT = (
    "The schema-only baseline reproduces schemas, types, tables (columns only), "
    "views, routines and triggers. Extensions, sequences, constraints, defaults "
    "and data are NOT reproduced, so findings that reference them are "
    "unreliable."
)


class SandboxSetupDialog(QDialog):
    """See the module docstring. Constructed with the app's one
    `SandboxController`; every external effect is an injected seam.

    ``controller``
        The live `SandboxController`. Its `session_changed` signal is connected
        so the dialog re-renders when a session appears or goes away.
    ``settings`` / ``project_dir``
        The open project's `ProjectSettings` and its directory. Needed to record
        D2a's mode (and a newly created sandbox database's name) through
        ``settings_saver``; when either is None the provisioning controls are
        absent, with `NO_PROJECT_REASON` stated in their place.
    ``confirm``
        ``(warning: str) -> bool``, asked with
        `SandboxController.destructive_warning(op)`'s exact text before a
        destructive gesture; a decline aborts before the controller is called.
        None (the default) leaves confirmation to the controller's own gate.
    ``settings_saver``
        `db/ddl_project.py::save_settings` -- the one store for
        `sandbox_mode`. Replaced in tests; never a second persistence path.
    ``maintenance_database``
        Which database `create_sandbox_database`'s admin connection targets.
    """

    def __init__(
        self,
        controller: SandboxController,
        parent: QWidget | None = None,
        *,
        settings: ProjectSettings | None = None,
        project_dir: str | Path | None = None,
        confirm: Callable[[str], bool] | None = None,
        settings_saver: Callable[..., None] = save_settings,
        maintenance_database: str = DEFAULT_MAINTENANCE_DATABASE,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sandbox Setup")
        self._controller = controller
        self._settings = settings
        self._project_dir = project_dir
        self._confirm = confirm
        self._settings_saver = settings_saver
        self._maintenance_database = maintenance_database
        # Off-thread executor seam for the one call this dialog makes itself --
        # `SandboxSession.applied()`, a SELECT. Same plain-attribute convention
        # as ConnectionSetupDialog/NewProjectDialog/ProjectSettingsDialog.
        self._run_async = run_async

        # The mode the user currently has selected. Seeded from the recorded
        # `ProjectSettings.sandbox_mode` (never re-derived from the database's
        # contents), falling back to the controller's recorded mode.
        self._chosen_mode: SandboxMode = (
            settings.sandbox_mode if settings is not None else controller.mode
        )

        # -- state group ----------------------------------------------------
        state_group = QGroupBox("Sandbox state")
        state_layout = QVBoxLayout(state_group)
        self._connection_label = self._add_state_label(state_layout)
        self._tier_label = self._add_state_label(state_layout)
        self._degraded_label = self._add_state_label(state_layout)
        self._ownership_label = self._add_state_label(state_layout)
        self._mode_label = self._add_state_label(state_layout)
        self._extension_label = self._add_state_label(state_layout)
        self._extension_reason_label = self._add_state_label(state_layout)
        self._caveat_label = self._add_state_label(state_layout)
        self._caveat_label.setText(BASELINE_CAVEAT)

        self._refresh_button = QPushButton("Re-check sandbox")
        self._refresh_button.clicked.connect(self.refresh_capabilities)
        refresh_row = QHBoxLayout()
        refresh_row.addWidget(self._refresh_button)
        refresh_row.addStretch(1)
        state_layout.addLayout(refresh_row)

        # -- actions group (rebuilt wholesale on every render) ---------------
        actions_group = QGroupBox("Sandbox actions")
        self._actions_layout = QVBoxLayout(actions_group)

        # Every action control: None means ABSENT, not disabled (carve-out 2).
        self._open_button: QPushButton | None = None
        self._provision_button: QPushButton | None = None
        self._create_button: QPushButton | None = None
        self._database_name_edit: QLineEdit | None = None
        self._with_data_radio: QRadioButton | None = None
        self._without_data_radio: QRadioButton | None = None
        self._clone_button: QPushButton | None = None
        self._reset_button: QPushButton | None = None
        self._install_button: QPushButton | None = None

        # -- working set ----------------------------------------------------
        working_set_group = QGroupBox("Working set (applied to this sandbox)")
        self._working_set_layout = QVBoxLayout(working_set_group)
        self._working_set_table: QTableWidget | None = None
        self._working_set_label = QLabel()
        self._working_set_label.setWordWrap(True)
        self._working_set_layout.addWidget(self._working_set_label)

        self._result_label = QLabel()
        self._result_label.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(state_group)
        layout.addWidget(actions_group)
        layout.addWidget(working_set_group)
        layout.addWidget(self._result_label)
        layout.addWidget(buttons)

        controller.session_changed.connect(self._on_session_changed)
        self.refresh_state()

        # Opening size only (BUG-036), set after the layout is fully built so it
        # wins over the layout's size hints. `resize()` -- not `setFixedSize` and
        # not a `setMinimumSize` at these values -- because the dialog must stay
        # freely resizable (and shrinkable) afterwards. This is the densest
        # dialog in the app; 1000px is what its stacked groups need.
        self.resize(660, 1000)

    # -- rendering ----------------------------------------------------------

    @staticmethod
    def _add_state_label(layout: QVBoxLayout) -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        layout.addWidget(label)
        return label

    def refresh_state(self) -> None:
        """Re-render everything from the controller's current, already-known
        state. Touches no database: `capability_status()` reads the last probe
        (and honestly reports "not probed yet" when there was none)."""
        controller = self._controller
        status = controller.capability_status()
        caps = controller.capabilities

        params = controller.sandbox_params
        if params is None or not (params.host or params.database):
            self._connection_label.setText("Sandbox connection: none configured.")
        else:
            self._connection_label.setText(
                f"Sandbox connection: {params.user or '?'}@{params.host or '?'}"
                f":{params.port or '?'}/{params.database or '?'}"
            )

        self._tier_label.setText(f"Project tier: {status.tier.value}.")
        self._degraded_label.setText(
            "" if status.degraded_reason is None else f"Degraded: {status.degraded_reason}"
        )
        self._ownership_label.setText(self._ownership_text())
        self._mode_label.setText(
            f"Provisioning mode (recorded): {_MODE_LABELS[controller.mode]}."
            + ("" if controller.has_session else " No session is open.")
        )

        if caps is None:
            self._extension_label.setText(
                "plpgsql_check: unknown -- the sandbox has not been probed yet."
            )
            self._extension_reason_label.setText("")
        else:
            state = caps.plpgsql_check_state
            _offered, reason = install_gate(caps)
            self._extension_label.setText(f"plpgsql_check: {state}.")
            lines = [reason] if reason else []
            if state != "installed":
                # `db/ddl_check.py`'s own sentence for what tier 3 will report,
                # which itself defers to `install_gate` for the actionable half.
                lines.append(f"Tier 3 will report: {not_installed_reason(caps)}")
            self._extension_reason_label.setText("\n".join(lines))

        self._rebuild_actions()
        self._render_working_set_area()

    def _ownership_text(self) -> str:
        caps = self._controller.capabilities
        if caps is None or not caps.database:
            return (
                "Ownership: unknown -- the sandbox database has not been "
                f"probed yet. A sandbox this app can write to is named "
                f"'{SANDBOX_DB_PREFIX}…' and carries our own marker comment."
            )
        if is_app_owned(caps.database, caps.owner_marker):
            return f"Ownership: {caps.database} is a sandbox PGTP Editor created."
        # The refusal's own sentence, never a second wording of it.
        return f"Ownership: {ForeignDatabaseError(caps.database)}"

    # -- action rows --------------------------------------------------------

    def _clear_actions(self) -> None:
        self._open_button = None
        self._provision_button = None
        self._create_button = None
        self._database_name_edit = None
        self._with_data_radio = None
        self._without_data_radio = None
        self._clone_button = None
        self._reset_button = None
        self._install_button = None
        _clear_layout(self._actions_layout)

    def _rebuild_actions(self) -> None:
        """Create only the controls whose operation can actually run now.

        Absence is the affordance (§18.5 carve-out 2): a control that would be
        dead is not built, and the reason takes its place.
        """
        self._clear_actions()
        controller = self._controller
        caps = controller.capabilities
        configured = controller.sandbox_params is not None

        if not configured:
            self._add_action_note(
                "No sandbox connection is configured for this project, so there "
                "is nothing to provision. Add one in Project Settings."
            )
        elif self._settings is None or self._project_dir is None:
            self._add_action_note(NO_PROJECT_REASON)
        elif controller.target_params is None:
            self._add_action_note(
                "Provisioning builds the sandbox from the project's target "
                "database, but no target connection is configured."
            )
        else:
            self._build_provisioning_rows()

        if controller.has_session:
            if controller.mode is SandboxMode.WITH_DATA:
                self._clone_button = self._add_action_button(
                    "Re-run data clone", self.run_data_clone
                )
            else:
                self._add_action_note(SCHEMA_ONLY_CLONE_REASON)
            self._reset_button = self._add_action_button(
                "Reset sandbox", self.reset_sandbox
            )
        else:
            self._add_action_note(NO_SESSION_REASON)
            if configured:
                self._open_button = self._add_action_button(
                    "Open sandbox session", self.open_session
                )

        # One-click install, offered only when the pure gate says so; otherwise
        # the gate's own refusal sentence stands where the button would be.
        if caps is None:
            self._add_action_note(
                "Install plpgsql_check: not offered until the sandbox has been "
                "probed (use 'Re-check sandbox')."
            )
        else:
            offered, reason = install_gate(caps)
            if offered and controller.has_session:
                self._install_button = self._add_action_button(
                    "Install plpgsql_check", self.install_plpgsql_check
                )
            elif offered:
                self._add_action_note(f"Install plpgsql_check: {NO_SESSION_REASON}")
            else:
                self._add_action_note(f"Install plpgsql_check: {reason}")

    def _build_provisioning_rows(self) -> None:
        """D2a's explicit with-data/without-data choice, plus D2's mandatory
        *"create a sandbox database for me"* mitigation."""
        self._add_action_note(
            "Provisioning mode -- chosen here and recorded in the project's "
            "settings; a later Reset re-runs the SAME mode."
        )
        self._without_data_radio = QRadioButton("Without data (schema only)")
        self._with_data_radio = QRadioButton("With data (clone the target's rows)")
        self._without_data_radio.setChecked(self._chosen_mode is SandboxMode.SCHEMA_ONLY)
        self._with_data_radio.setChecked(self._chosen_mode is SandboxMode.WITH_DATA)
        self._without_data_radio.toggled.connect(self._on_mode_toggled)
        self._with_data_radio.toggled.connect(self._on_mode_toggled)
        self._actions_layout.addWidget(self._without_data_radio)
        self._actions_layout.addWidget(self._with_data_radio)

        self._provision_button = self._add_action_button(
            "Provision sandbox", self.provision
        )

        self._add_action_note(
            "PGTP Editor only writes to a sandbox database it created itself. "
            "If the configured database is not one, create one here -- the name "
            f"must look like '{SANDBOX_DB_PREFIX}myproject'."
        )
        row = QHBoxLayout()
        self._database_name_edit = QLineEdit(self._suggested_database_name())
        self._create_button = QPushButton("Create a sandbox database for me")
        self._create_button.clicked.connect(self.create_sandbox_database)
        row.addWidget(self._database_name_edit)
        row.addWidget(self._create_button)
        self._actions_layout.addLayout(row)

    def _add_action_note(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        self._actions_layout.addWidget(label)
        return label

    def _add_action_button(self, text: str, handler: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(handler)
        row = QHBoxLayout()
        row.addWidget(button)
        row.addStretch(1)
        self._actions_layout.addLayout(row)
        return button

    def _suggested_database_name(self) -> str:
        params = self._controller.sandbox_params
        current = params.database if params is not None else ""
        if current.startswith(SANDBOX_DB_PREFIX):
            return current
        # The same slug rule §18.2's New Project auto-naming uses, imported
        # rather than re-derived, so the two surfaces suggest the same shape of
        # name (this one stays user-editable; New Project's is not typed at all).
        return f"{SANDBOX_DB_PREFIX}{sandbox_name_stem(self._settings.name if self._settings else '')}"

    def _on_mode_toggled(self, _checked: bool) -> None:
        self._chosen_mode = self.chosen_mode()

    def chosen_mode(self) -> SandboxMode:
        """The mode the with-data/without-data radios currently express, or the
        recorded one when the radios are absent."""
        if self._with_data_radio is not None and self._with_data_radio.isChecked():
            return SandboxMode.WITH_DATA
        if self._without_data_radio is not None:
            return SandboxMode.SCHEMA_ONLY
        return self._chosen_mode

    # -- working set --------------------------------------------------------

    def _render_working_set_area(self) -> None:
        """Build the `applied()` table only when there is a session to read it
        from, then load it off-thread."""
        if self._working_set_table is not None:
            self._working_set_layout.removeWidget(self._working_set_table)
            self._working_set_table.setParent(None)
            self._working_set_table.deleteLater()
            self._working_set_table = None
        if not self._controller.has_session:
            self._working_set_label.setText(
                "Working set: unavailable. " + NO_SESSION_REASON
            )
            return
        self._working_set_label.setText("Working set: loading…")
        table = QTableWidget(0, len(_WORKING_SET_COLUMNS))
        table.setHorizontalHeaderLabels(list(_WORKING_SET_COLUMNS))
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._working_set_layout.addWidget(table)
        self._working_set_table = table
        self.load_working_set()

    def load_working_set(self) -> None:
        """Read `SandboxSession.applied()` off the GUI thread and render it --
        the §18.5 D2 working-set list. One `SELECT`, through the session the
        controller owns; no SQL is written here."""
        session = self._controller.session
        if session is None or self._working_set_table is None:
            return
        self._run_async(
            session.applied,
            on_result=self._render_working_set,
            on_error=self._on_working_set_error,
        )

    def _render_working_set(self, rows: list[AppliedObject]) -> None:
        table = self._working_set_table
        if table is None:
            return
        rows = list(rows or [])
        table.setRowCount(len(rows))
        for index, applied in enumerate(rows):
            for column, value in enumerate(
                (
                    applied.kind,
                    applied.schema_name,
                    applied.object_name,
                    applied.table_name,
                    applied.applied_at,
                )
            ):
                table.setItem(index, column, QTableWidgetItem(str(value)))
        count = len(rows)
        self._working_set_label.setText(
            "Working set: nothing has been applied to this sandbox yet."
            if count == 0
            else f"Working set: {count} object{'' if count == 1 else 's'} applied."
        )

    def _on_working_set_error(self, exc: BaseException) -> None:
        self._working_set_label.setText(
            "Working set: could not be read -- "
            f"{exc or exc.__class__.__name__}. Nothing was changed."
        )

    # -- operations ---------------------------------------------------------

    def refresh_capabilities(self) -> None:
        """Fresh probe (§18.8's re-check). Non-destructive."""
        self._controller.refresh_capabilities(self._on_operation)

    def open_session(self) -> None:
        """Open the one ownership-gated session. Non-destructive: a database we
        did not create fails with `ForeignDatabaseError`'s own message, which is
        reported alongside the "create one for me" control."""
        self._controller.open_session(self._on_operation)

    def provision(self) -> None:
        """**Destructive.** Record the chosen mode, then provision the already
        configured sandbox database from the target."""
        self._provision(create_database=False)

    def create_sandbox_database(self) -> None:
        """**Destructive.** D2's mandatory mitigation: create a fresh app-owned
        sandbox database (`create_sandbox_database`, validated name) and
        provision it in the same operation."""
        self._provision(create_database=True)

    def _provision(self, *, create_database: bool) -> None:
        settings = self._settings
        if settings is None or self._project_dir is None:
            self._report(NO_PROJECT_REASON)
            return
        if not self._confirmed(SandboxOperation.PROVISION):
            return

        mode = self.chosen_mode()
        database_name = (
            self._database_name_edit.text().strip()
            if create_database and self._database_name_edit is not None
            else ""
        )
        if create_database and not database_name:
            self._report(
                "Give the new sandbox database a name "
                f"('{SANDBOX_DB_PREFIX}…') before creating it."
            )
            return

        sandbox_params = settings.sandbox
        if database_name:
            sandbox_params = replace(sandbox_params, database=database_name)
        self._persist(mode=mode, sandbox_params=sandbox_params)

        self._controller.set_project(
            sandbox_params=sandbox_params,
            target_params=settings.target,
            mode=mode,
        )
        admin_params: ConnectionParams | None = None
        if database_name:
            admin_params = replace(
                sandbox_params, database=self._maintenance_database
            )
        self._controller.provision(
            self._on_operation,
            admin_params=admin_params,
            database_name=database_name or None,
        )

    def run_data_clone(self) -> None:
        """**Destructive.** Re-run D2a's `pg_dump`/`pg_restore` clone."""
        if not self._confirmed(SandboxOperation.CLONE_DATA):
            return
        self._controller.run_data_clone(self._on_operation)

    def reset_sandbox(self) -> None:
        """**Destructive.** `SandboxSession.reset()` -- drop every app schema and
        re-run whichever mode this sandbox was created with."""
        if not self._confirmed(SandboxOperation.RESET):
            return
        self._controller.reset_session(self._on_operation)

    def install_plpgsql_check(self) -> None:
        """One-click `CREATE EXTENSION IF NOT EXISTS plpgsql_check` through the
        controller, whose gate is `install_gate`'s. Non-destructive."""
        self._controller.install_plpgsql_check(self._on_operation)

    # -- internals ----------------------------------------------------------

    def _confirmed(self, operation: SandboxOperation) -> bool:
        """Ask the injected confirmation seam with the controller's own warning
        text. No `QMessageBox` is ever constructed here; with no seam injected
        the gesture proceeds to the controller, whose own
        `confirm_destructive` gate then decides (and refuses when it has none).
        """
        if self._confirm is None:
            return True
        warning = SandboxController.destructive_warning(operation)
        if self._confirm(warning):
            return True
        self._report(f"Cancelled -- this operation was not confirmed. {warning}".strip())
        return False

    def _persist(self, *, mode: SandboxMode, sandbox_params: ConnectionParams) -> None:
        """Record D2a's mode (and a newly created database's name) in the ONE
        store that already holds it -- `ProjectSettings.sandbox_mode`."""
        settings = self._settings
        if settings is None or self._project_dir is None:
            return
        self._settings = replace(settings, sandbox_mode=mode, sandbox=sandbox_params)
        self._chosen_mode = mode
        self._settings_saver(self._project_dir, self._settings)

    def settings(self) -> ProjectSettings | None:
        """The project settings as this dialog has them -- including a mode or
        sandbox database name it recorded, so the host can adopt the same
        object instead of re-reading the file."""
        return self._settings

    def _on_session_changed(self, _alive: bool) -> None:
        self.refresh_state()

    def _on_operation(self, result) -> None:
        """Report one `SandboxOperationResult` -- its stated `reason` always,
        success or failure, never swallowed -- then re-render."""
        name = result.operation.value.replace("_", " ")
        reason = (result.reason or "").strip()
        if result.ok:
            self._report(f"{name}: done." + (f" {reason}" if reason else ""))
        else:
            self._report(
                f"{name} failed: {reason}"
                if reason
                else f"{name} failed, and reported no reason."
            )
        self.refresh_state()

    def _report(self, text: str) -> None:
        self._result_label.setText(text)

    def result_text(self) -> str:
        """The last reported operation outcome -- what the user sees."""
        return self._result_label.text()

    def state_text(self) -> str:
        """Everything the state group currently says, as one string."""
        return "\n".join(
            label.text()
            for label in (
                self._connection_label,
                self._tier_label,
                self._degraded_label,
                self._ownership_label,
                self._mode_label,
                self._extension_label,
                self._extension_reason_label,
                self._caveat_label,
            )
        )

    def action_notes(self) -> str:
        """Every reason-in-place-of-a-control the actions group shows."""
        texts = []
        for index in range(self._actions_layout.count()):
            widget = self._actions_layout.itemAt(index).widget()
            if isinstance(widget, QLabel):
                texts.append(widget.text())
        return "\n".join(texts)


def _clear_layout(layout) -> None:
    """Remove and destroy everything in `layout` -- how an unavailable control
    becomes ABSENT rather than disabled."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
            continue
        child = item.layout()
        if child is not None:
            _clear_layout(child)
            child.deleteLater()
