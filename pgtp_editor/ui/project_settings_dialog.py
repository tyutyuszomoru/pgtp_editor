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

# pgtp_editor/ui/project_settings_dialog.py
"""The Project Settings dialog (§18.2).

Exposes the project's ENTIRE centralized, gitignored, plaintext JSON for
viewing and editing -- **not a simplified subset, the whole thing**: project
identity, the `.pgtp` link and its paths, both connection profiles
(including the password fields, plaintext-in-this-file-by-design, §18.2),
and the deploy manifest's raw per-object entries.

Shown non-modally (`show()`, never `.exec()`), same convention as every
other dialog in this codebase: the caller reads `settings()` back after
`accepted` fires and performs the actual `save_settings` write itself --
this dialog persists nothing on its own **except** through the one
provisioning path described below.

**Sandbox provisioning lives here (2026-08-09 owner ruling).** `Provision
sandbox`, `Reset sandbox` and `Create a sandbox database for me` used to live in
`Database ▸ Sandbox Setup…` (`ui/sandbox_setup_dialog.py`), which was DELETED:
BUG-040 had hidden that menu entry in project mode on the premise that *"in
project mode all sandbox configuration already lives in Project Settings"*, and
this dialog carried only the connection fields, a Test button and the recorded
mode -- so the premise was false and the three gestures were unreachable in
every mode. They now sit on the **Connections** tab, in the sandbox connection
group, immediately under the mode radios whose promise (*"takes effect the next
time the sandbox is reset/recreated"*) they are what makes keepable.

Everything those gestures were is preserved, only its host changed:

- **nothing destructive happens without a confirmation** -- Provision, "create
  one for me" and Reset each go through `_confirmed`, which asks with
  `SandboxController.destructive_warning(op)`'s exact text; `confirm=None` (the
  default, and what the app passes) leaves the single prompt to the controller's
  own `confirm_destructive` gate, so the user is asked exactly once;
- **no dead controls** (§18.5 carve-out 2): a control whose operation cannot run
  is not built, and the reason takes its place -- hence `_rebuild_sandbox_actions`
  rather than `setEnabled(False)`;
- the `ForeignDatabaseError` refusal is stated in the refusal's own words, above
  the *"create a sandbox database for me"* row that answers it;
- D2a's mode is **recorded, never re-derived**: a provisioning gesture writes
  the settings as currently typed (including the chosen mode and any freshly
  created database name) through `settings_saver` BEFORE the operation starts,
  and `recorded_settings()` hands that exact object back so the host adopts it
  instead of re-reading the file.

Data cloning and the `plpgsql_check` install are deliberately NOT duplicated
here: §18.8's Project Status window already owns those two node buttons.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import (
    DeployedObject,
    GitConfig,
    PgtpLink,
    ProjectSettings,
    save_settings,
)
from pgtp_editor.db.introspect import test_connection
from pgtp_editor.db.sandbox import (
    DATA_CLONE_TOOLS,
    SANDBOX_DB_PREFIX,
    ForeignDatabaseError,
    SandboxCapabilities,
    SandboxMode,
    is_app_owned,
    probe,
    resolve_tool,
)
from pgtp_editor.ui.async_task import run_async
from pgtp_editor.ui.sandbox_controller import (
    MAINTENANCE_DATABASE,
    SandboxController,
    SandboxOperation,
    sandbox_name_stem,
)
from pgtp_editor.ui.status_colours import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_WARNING,
    StatusLabel,
)

_DEPLOYED_COLUMNS = ("Path", "Content hash", "Deployed commit")

Tester = Callable[[ConnectionParams], "tuple[bool, str]"]
#: Takes the params plus the project's configured binaries folder
#: (FQ-260812025353), because `pg_dump`/`pg_restore` detection is part of what
#: a probe reports and PATH is no longer the only place they can live. A stub
#: therefore has the shape `lambda params, **_: SandboxCapabilities(...)`.
Prober = Callable[..., SandboxCapabilities]
#: Injectable folder picker, so no test ever reaches an un-patched modal
#: `QFileDialog` (§30 / the testing policy's modal rule).
FolderChooser = Callable[[QWidget, str, str], str]

#: Which database `create_sandbox_database`'s admin connection targets --
#: PostgreSQL forbids `CREATE DATABASE` inside the database being created. An
#: **alias** of `ui/sandbox_controller.py::MAINTENANCE_DATABASE`, not a second
#: literal, so §18.2's New Project step and this dialog cannot disagree.
DEFAULT_MAINTENANCE_DATABASE = MAINTENANCE_DATABASE

_MODE_LABELS = {
    SandboxMode.SCHEMA_ONLY: "without data (schema only)",
    SandboxMode.WITH_DATA: "with data (pg_dump/pg_restore clone)",
}

#: Stated where the provisioning controls would be when this dialog was built
#: without the app's `SandboxController` (or without the project directory the
#: recorded mode has to be written to) -- i.e. never in the running app, which
#: always supplies both, but this dialog is also constructed bare in tests.
NO_CONTROLLER_REASON = (
    "Sandbox provisioning is unavailable: this dialog was opened without the "
    "app's sandbox controller."
)

#: Stated where Provision would be when the sandbox group above is still blank.
NO_SANDBOX_REASON = (
    "No sandbox server is configured yet. Fill in the sandbox connection above "
    "first — provisioning needs somewhere to provision."
)

#: Stated where Provision would be when the project has no target to build the
#: baseline from. The controller refuses for the same reason; this is only the
#: refusal made visible before the click rather than after it.
NO_TARGET_REASON = (
    "Provisioning builds the sandbox from the project's target database, but no "
    "target connection is configured on this tab."
)

#: Stated where Reset would be with no live session.
NO_SESSION_REASON = (
    "No sandbox session is open, so the sandbox's contents cannot be changed. "
    "Provision the sandbox first."
)

#: The *"create a sandbox database for me"* row's reason for existing (§18.5 D2's
#: mandatory mitigation for the `ForeignDatabaseError` refusal).
CREATE_DATABASE_NOTE = (
    "PGTP Editor only writes to a sandbox database it created itself. If the "
    "database above is not one, create one here — the name must look like "
    f"'{SANDBOX_DB_PREFIX}myproject'."
)

#: What Reset actually re-runs. `SandboxSession.reset()` re-runs the mode the
#: sandbox was CREATED with, not whichever radio is currently checked, so the
#: mode note's *"next time it is reset/recreated"* promise is only kept by
#: Provision when the mode is being CHANGED. Said here rather than left for the
#: user to discover from a reset that silently did the old thing.
RESET_MODE_NOTE = (
    "Reset drops every application schema in the sandbox and rebuilds it in the "
    "mode it was created with ({mode}). Changing the mode above takes effect "
    "when you Provision, not when you Reset."
)

#: The incompleteness of the schema-only baseline, stated in the UI rather than
#: buried (§18.5 D2). Shown where the schema-only mode is chosen.
BASELINE_CAVEAT = (
    "The schema-only baseline reproduces schemas, types, tables (columns only), "
    "views, routines and triggers. Extensions, sequences, constraints, defaults "
    "and data are NOT reproduced, so findings that reference them are "
    "unreliable."
)


#: The *Locate postgres binaries* field's explanation (FQ-260812025353). Says
#: what EMPTY means, because "leave it blank" is the common, correct answer and
#: a blank required-looking field otherwise reads as unfinished configuration.
POSTGRES_BIN_DIR_NOTE = (
    "The folder holding this project's pg_dump / pg_restore. Leave EMPTY to "
    "use whatever is on PATH (today's behaviour). Set it when several "
    "PostgreSQL versions are installed, or when the client tools are not on "
    "PATH at all — pg_dump refuses to dump from a server NEWER than itself, "
    "so the major must match this project's server. Stored per project, in "
    "the gitignored settings file, so this machine-specific path never "
    "travels via git."
)

#: Shown when the folder is set but a tool is not in it. **Warn, never block**
#: (the entry's own ruling): the field is optional, the user may be mid-typing,
#: and PATH is still a legitimate fallback — which is exactly what the resolver
#: does.
BIN_DIR_MISSING_TEMPLATE = (
    "{missing} not in this folder — falling back to PATH for {missing_short}."
)


def _with_server_version(message: str, caps: SandboxCapabilities) -> str:
    """Append `" Server: PostgreSQL 16.0.3."` to a Test button's status text.

    The point of showing it (FQ-260812025353) is that the user can SEE a
    server-vs-`pg_dump` major mismatch — quality and sandbox each state their
    own, and `pg_dump` refuses a server newer than itself. An **unknown**
    version (a probe that could not read `server_version_num`) appends
    nothing: silence is honest, an invented number is not.
    """
    if not caps.server_version:
        return message
    version = ".".join(str(part) for part in caps.server_version)
    return f"{message} Server: PostgreSQL {version}."


def _clear_layout(layout) -> None:
    """Remove and destroy everything in `layout` -- how an unavailable control
    becomes ABSENT rather than disabled (§18.5 carve-out 2)."""
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


class ProjectSettingsDialog(QDialog):
    def __init__(
        self,
        settings: ProjectSettings,
        parent: QWidget | None = None,
        tester: Tester = test_connection,
        prober: Prober = probe,
        *,
        sandbox_controller: SandboxController | None = None,
        project_dir: str | Path | None = None,
        confirm: Callable[[str], bool] | None = None,
        settings_saver: Callable[..., None] = save_settings,
        maintenance_database: str = DEFAULT_MAINTENANCE_DATABASE,
        folder_chooser: FolderChooser = QFileDialog.getExistingDirectory,
        tool_resolver: Callable[..., "str | None"] = resolve_tool,
    ) -> None:
        super().__init__(parent)
        # Test seams, same convention as ConnectionSetupDialog (generic
        # connectivity) and NewProjectDialog (sandbox superuser probe): both
        # flavors are reused verbatim rather than a third being invented.
        self._tester = tester
        self._prober = prober
        # Off-thread executor seam; tests replace it with a synchronous stub.
        self._run_async = run_async
        # -- provisioning seams (see the module docstring) -------------------
        self._sandbox_controller = sandbox_controller
        self._project_dir = project_dir
        self._confirm = confirm
        self._settings_saver = settings_saver
        self._maintenance_database = maintenance_database
        self._folder_chooser = folder_chooser
        self._tool_resolver = tool_resolver
        #: The `ProjectSettings` a provisioning gesture PERSISTED, or None when
        #: none has run. Deliberately not `settings()` (which is the live field
        #: state): the host must adopt exactly what was written to disk.
        self._recorded_settings: ProjectSettings | None = None
        self.setWindowTitle("Project Settings")

        identity_form = QFormLayout()
        self._name_edit = QLineEdit()
        self._description_edit = QLineEdit()
        identity_form.addRow("Name:", self._name_edit)
        identity_form.addRow("Description:", self._description_edit)

        pgtp_group = QGroupBox(".pgtp link")
        self._pgtp_source_edit = QLineEdit()
        self._pgtp_working_copy_edit = QLineEdit()
        self._pgtp_checksum_edit = QLineEdit()
        pgtp_form = QFormLayout(pgtp_group)
        pgtp_form.addRow("Source path (sshfs-mounted):", self._pgtp_source_edit)
        pgtp_form.addRow("Working copy path:", self._pgtp_working_copy_edit)
        pgtp_form.addRow("Last known source checksum:", self._pgtp_checksum_edit)

        target_group = QGroupBox("Target connection")
        (
            self._target_host_edit,
            self._target_port_edit,
            self._target_database_edit,
            self._target_user_edit,
            self._target_password_edit,
        ) = self._build_connection_form(target_group)
        self._target_test_button, self._target_status_label = self._add_test_row(
            target_group, self.test_target
        )
        # BUG-034: this is now literally the connection every gesture opens
        # while the project is open, so say so -- and say what BLANK means, so
        # a fresh FQ-007 project (which collects no target at all) reads as
        # "not configured yet" rather than as a display bug.
        self._target_note = QLabel(
            "This is the connection the DDL Explorer and the database checks"
            " actually use while this project is open. Imported from the"
            " .pgtp's <ConnectionOptions> the first time it is opened (the"
            " password is never in the XML -- it is asked for once, then"
            " stored here). Blank means no target is configured yet."
        )
        self._target_note.setWordWrap(True)
        target_group.layout().addRow(self._target_note)

        sandbox_group = QGroupBox("Sandbox connection")
        (
            self._sandbox_host_edit,
            self._sandbox_port_edit,
            self._sandbox_database_edit,
            self._sandbox_user_edit,
            self._sandbox_password_edit,
        ) = self._build_connection_form(sandbox_group)
        self._sandbox_test_button, self._sandbox_status_label = self._add_test_row(
            sandbox_group, self.test_sandbox
        )

        # Sandbox provisioning mode (§18.5 D2a) -- chosen once at New Project
        # time; shown/editable here too since this dialog exposes the JSON's
        # FULL contents, not a subset. Changing it here does NOT re-clone
        # anything by itself -- it only edits the recorded intent for the
        # NEXT reset()/recreate, exactly like every other field in this dialog.
        self._sandbox_mode_without_data_radio = QRadioButton("Without data (schema only)")
        self._sandbox_mode_with_data_radio = QRadioButton("With data")
        mode_note = QLabel(
            "Changing this does not re-clone the sandbox -- it takes effect"
            " the next time the sandbox is provisioned (Provision sandbox,"
            " below)."
        )
        mode_note.setWordWrap(True)
        sandbox_mode_form = QFormLayout()
        sandbox_mode_form.addRow(self._sandbox_mode_without_data_radio)
        sandbox_mode_form.addRow(self._sandbox_mode_with_data_radio)
        sandbox_mode_form.addRow(mode_note)
        sandbox_group.layout().addRow(sandbox_mode_form)

        # -- the three provisioning actions (owner ruling, 2026-08-09) -------
        # Rebuilt wholesale on every state change rather than enabled/disabled,
        # because carve-out 2 makes an unavailable control ABSENT with the
        # reason in its place. `None` therefore means absent, never "disabled".
        provisioning_group = QGroupBox("Sandbox provisioning")
        self._sandbox_actions_layout = QVBoxLayout(provisioning_group)
        self._provision_button: QPushButton | None = None
        self._reset_button: QPushButton | None = None
        self._create_database_button: QPushButton | None = None
        self._new_database_name_edit: QLineEdit | None = None
        self._sandbox_action_status = QLabel("")
        self._sandbox_action_status.setWordWrap(True)
        sandbox_group.layout().addRow(provisioning_group)
        sandbox_group.layout().addRow(self._sandbox_action_status)

        # -- FQ-260812025353: where this project's client binaries live ------
        # On the Connections tab, not a tab of its own: which pg_dump answers
        # is a property of WHICH SERVER this project talks to (its major must
        # match), so it belongs beside the two connection profiles that
        # determine it.
        binaries_group = QGroupBox("PostgreSQL binaries")
        self._postgres_bin_dir_edit = QLineEdit()
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self.browse_for_postgres_bin_dir)
        self._browse_bin_dir_button = browse_button
        bin_dir_row = QHBoxLayout()
        bin_dir_row.addWidget(self._postgres_bin_dir_edit, 1)
        bin_dir_row.addWidget(browse_button)
        self._bin_dir_status_label = StatusLabel("")
        self._bin_dir_status_label.setWordWrap(True)
        bin_dir_note = QLabel(POSTGRES_BIN_DIR_NOTE)
        bin_dir_note.setWordWrap(True)
        binaries_form = QFormLayout(binaries_group)
        binaries_form.addRow("Locate postgres binaries:", bin_dir_row)
        binaries_form.addRow(self._bin_dir_status_label)
        binaries_form.addRow(bin_dir_note)

        git_group = QGroupBox("Git (optional -- not yet used)")
        self._git_server_edit = QLineEdit()
        self._git_user_edit = QLineEdit()
        self._git_branch_edit = QLineEdit()
        git_form = QFormLayout(git_group)
        git_form.addRow("Server:", self._git_server_edit)
        git_form.addRow("User:", self._git_user_edit)
        git_form.addRow("Checkout branch:", self._git_branch_edit)

        deployed_group = QGroupBox("Deploy manifest (per-object last-deployed reference)")
        self._deployed_table = QTableWidget(0, len(_DEPLOYED_COLUMNS))
        self._deployed_table.setHorizontalHeaderLabels(_DEPLOYED_COLUMNS)
        self._deployed_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        add_row_button = QPushButton("Add Row")
        add_row_button.clicked.connect(self._add_deployed_row)
        remove_row_button = QPushButton("Remove Selected Row")
        remove_row_button.clicked.connect(self._remove_selected_deployed_row)
        deployed_layout = QVBoxLayout(deployed_group)
        deployed_layout.addWidget(self._deployed_table)
        deployed_layout.addWidget(add_row_button)
        deployed_layout.addWidget(remove_row_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        tabs = QTabWidget(self)

        general_page = QWidget()
        general_layout = QVBoxLayout(general_page)
        general_layout.addLayout(identity_form)
        general_layout.addWidget(pgtp_group)
        tabs.addTab(general_page, "General")

        connections_page = QWidget()
        connections_layout = QVBoxLayout(connections_page)
        connections_layout.addWidget(target_group)
        connections_layout.addWidget(sandbox_group)
        connections_layout.addWidget(binaries_group)
        tabs.addTab(connections_page, "Connections")

        git_page = QWidget()
        git_layout = QVBoxLayout(git_page)
        git_layout.addWidget(git_group)
        tabs.addTab(git_page, "Git")

        deploy_page = QWidget()
        deploy_layout = QVBoxLayout(deploy_page)
        deploy_layout.addWidget(deployed_group)
        tabs.addTab(deploy_page, "Deploy manifest")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

        # Opening size only (BUG-036) -- the dialog stays freely resizable, so
        # this is a `resize()` and deliberately not `setFixedSize`/`setMinimumSize`.
        # 760 tall clears the tallest tab (Deploy manifest's table, Connections'
        # two connection forms) with the OK/Cancel box still visible.
        self.resize(560, 760)

        self.set_settings(settings)

        # Which provisioning controls exist depends on what is typed above
        # (a sandbox server, a target to build from) and on whether a session is
        # live -- so every one of those is a rebuild trigger. Connected after
        # `set_settings` so the seeding writes do not fire a rebuild before the
        # action layout has ever been built.
        self._postgres_bin_dir_edit.textChanged.connect(self._refresh_bin_dir_status)
        self._refresh_bin_dir_status()
        self._sandbox_host_edit.textChanged.connect(self._rebuild_sandbox_actions)
        self._target_host_edit.textChanged.connect(self._rebuild_sandbox_actions)
        self._sandbox_mode_with_data_radio.toggled.connect(
            self._rebuild_sandbox_actions
        )
        if sandbox_controller is not None:
            sandbox_controller.session_changed.connect(self._on_session_changed)
        self._rebuild_sandbox_actions()

    @staticmethod
    def _build_connection_form(group: QGroupBox) -> tuple[QLineEdit, QLineEdit, QLineEdit, QLineEdit, QLineEdit]:
        host_edit = QLineEdit()
        port_edit = QLineEdit()
        database_edit = QLineEdit()
        user_edit = QLineEdit()
        password_edit = QLineEdit()
        password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form = QFormLayout(group)
        form.addRow("Host:", host_edit)
        form.addRow("Port:", port_edit)
        form.addRow("Database:", database_edit)
        form.addRow("User:", user_edit)
        form.addRow("Password:", password_edit)
        return host_edit, port_edit, database_edit, user_edit, password_edit

    @staticmethod
    def _add_test_row(
        group: QGroupBox, slot: Callable[[], None]
    ) -> tuple[QPushButton, StatusLabel]:
        """The Test button + inline colored status label row, same shape as
        `ConnectionSetupDialog` / `NewProjectDialog` (FQ-001).

        A `StatusLabel`, not a plain `QLabel`: the verdict's colour is a
        per-theme value derived from a remembered KIND (BUG-260812063745)."""
        test_button = QPushButton("Test")
        test_button.clicked.connect(slot)
        status_label = StatusLabel("")
        test_row = QHBoxLayout()
        test_row.addWidget(test_button)
        test_row.addWidget(status_label, 1)
        group.layout().addRow(test_row)
        return test_button, status_label

    # --- Connection tests (FQ-001) -------------------------------------------
    def target_params(self) -> ConnectionParams:
        """The target connection as **currently typed**, not as last saved."""
        return self._connection_from_fields(
            self._target_host_edit,
            self._target_port_edit,
            self._target_database_edit,
            self._target_user_edit,
            self._target_password_edit,
        )

    def sandbox_params(self) -> ConnectionParams:
        """The sandbox connection as **currently typed**, not as last saved."""
        return self._connection_from_fields(
            self._sandbox_host_edit,
            self._sandbox_port_edit,
            self._sandbox_database_edit,
            self._sandbox_user_edit,
            self._sandbox_password_edit,
        )

    def sandbox_mode(self) -> SandboxMode:
        if self._sandbox_mode_with_data_radio.isChecked():
            return SandboxMode.WITH_DATA
        return SandboxMode.SCHEMA_ONLY

    # --- PostgreSQL binaries folder (FQ-260812025353) -------------------------
    def postgres_bin_dir(self) -> str:
        """The binaries folder as **currently typed**, not as last saved --
        same rule as `target_params`/`sandbox_params`, so a Test run right
        after editing the field tests what is on screen."""
        return self._postgres_bin_dir_edit.text().strip()

    def browse_for_postgres_bin_dir(self) -> None:
        """Pick the folder. Goes through the injected `folder_chooser` seam so
        no test ever reaches an un-patched modal `QFileDialog`."""
        chosen = self._folder_chooser(
            self, "Locate postgres binaries", self.postgres_bin_dir()
        )
        if chosen:
            self._postgres_bin_dir_edit.setText(str(chosen))

    def _refresh_bin_dir_status(self, *_args) -> None:
        """**Warn, never block.** States what the folder currently resolves to
        -- empty means PATH; set-and-complete says so; set-but-incomplete names
        the tools that will fall back to PATH. No subprocess is spawned here:
        this runs on every keystroke, and existence is a filesystem question."""
        bin_dir = self.postgres_bin_dir()
        if not bin_dir:
            self._bin_dir_status_label.setText(
                "Empty — pg_dump and pg_restore are taken from PATH."
            )
            self._bin_dir_status_label.set_status_kind(None)
            return
        missing = [
            name
            for name in DATA_CLONE_TOOLS
            if self._tool_resolver(name, bin_dir=bin_dir, which=lambda _name: None) is None
        ]
        if not missing:
            self._bin_dir_status_label.setText(
                f"Found {' and '.join(DATA_CLONE_TOOLS)} in this folder."
            )
            self._bin_dir_status_label.set_status_kind(STATUS_OK)
            return
        joined = " and ".join(missing)
        self._bin_dir_status_label.setText(
            BIN_DIR_MISSING_TEMPLATE.format(missing=joined, missing_short=joined)
        )
        # Amber, not red: this is a warning, and the operation can still work
        # (PATH answers). `STATUS_WARNING` resolves it per theme from the
        # `status_warning` accent -- which is what this line was reaching for
        # when it named `darkorange` to satisfy the colour guard's letter
        # (BUG-260812063745); that name measured 2.23:1 on the light chrome.
        self._bin_dir_status_label.set_status_kind(STATUS_WARNING)

    def bin_dir_status_text(self) -> str:
        """What the binaries-folder warning line currently says."""
        return self._bin_dir_status_label.text()

    def test_target(self) -> None:
        """Generic connectivity check, identical to `ConnectionSetupDialog.test`.
        Run off the GUI thread so an unreachable host can't freeze the dialog."""
        self._target_test_button.setEnabled(False)
        self._target_status_label.set_status("Testing connection…", None)
        params = self.target_params()
        bin_dir = self.postgres_bin_dir()

        def work() -> "tuple[bool, str]":
            # The connectivity verdict stays the `tester`'s (unchanged); the
            # VERSION comes from the probe, because `test_connection` runs
            # `SELECT 1` and knows nothing about the server. Only asked for
            # once the connection is known good, so an unreachable host costs
            # one failed attempt, not two.
            ok, message = self._tester(params)
            if not ok:
                return False, message
            caps = self._prober(params, bin_dir=bin_dir)
            return True, _with_server_version(message, caps)

        def on_result(result: "tuple[bool, str]") -> None:
            ok, message = result
            # A KIND, not a colour: the indirect `"green" if ok else "red"`
            # form this replaces was invisible to the colour guard *and*
            # theme-blind (BUG-260812063745).
            self._target_status_label.set_status(
                message, STATUS_OK if ok else STATUS_ERROR
            )
            self._target_test_button.setEnabled(True)

        def on_error(exc: BaseException) -> None:
            self._target_status_label.set_status(str(exc), STATUS_ERROR)
            self._target_test_button.setEnabled(True)

        self._run_async(work, on_result=on_result, on_error=on_error)

    def test_sandbox(self) -> None:
        """Superuser-specific probe, identical to `NewProjectDialog.test_sandbox`
        -- NOT a plain connectivity check, which would give a false green light
        to a connection that connects but can't `CREATE EXTENSION` (§18.5 D2)."""
        self._sandbox_test_button.setEnabled(False)
        self._sandbox_status_label.set_status("Testing…", None)
        params = self.sandbox_params()
        bin_dir = self.postgres_bin_dir()

        def on_result(caps: SandboxCapabilities) -> None:
            self._apply_sandbox_probe_result(caps)

        def on_error(exc: BaseException) -> None:
            self._sandbox_status_label.set_status(str(exc), STATUS_ERROR)
            self._sandbox_test_button.setEnabled(True)

        self._run_async(
            lambda: self._prober(params, bin_dir=bin_dir),
            on_result=on_result,
            on_error=on_error,
        )

    def _apply_sandbox_probe_result(self, caps: SandboxCapabilities) -> None:
        self._sandbox_test_button.setEnabled(True)
        if caps.probe_error is not None:
            self._sandbox_status_label.set_status(caps.probe_error, STATUS_ERROR)
            return
        if not caps.is_superuser:
            self._sandbox_status_label.setText(
                "Connected, but NOT a superuser — sandbox provisioning needs CREATE EXTENSION."
            )
            self._sandbox_status_label.set_status_kind(STATUS_ERROR)
            return
        if self.sandbox_mode() is SandboxMode.WITH_DATA and not caps.data_clone_available:
            missing = [
                name
                for name, path in (("pg_dump", caps.pg_dump_path), ("pg_restore", caps.pg_restore_path))
                if path is None
            ]
            # Name the CONFIGURED FOLDER when there is one. "on PATH (not
            # found)" was true before FQ-260812025353 and sends a user who set
            # a binaries folder off to edit their PATH -- the wrong thing. Same
            # correction as `determine_project_tier`'s degraded reason and
            # `MissingCloneToolError`, which already name both places.
            bin_dir = self.postgres_bin_dir()
            where = (
                f"in {bin_dir} or on PATH" if bin_dir else "on PATH"
            )
            self._sandbox_status_label.setText(
                _with_server_version(
                    "Connected — superuser, but 'with data' needs "
                    f"{' and '.join(missing)} {where} (not found).",
                    caps,
                )
            )
            self._sandbox_status_label.set_status_kind(STATUS_ERROR)
            return
        self._sandbox_status_label.setText(
            _with_server_version("Connected — superuser.", caps)
        )
        self._sandbox_status_label.set_status_kind(STATUS_OK)

    # --- Sandbox provisioning (§18.5 D2/D2a) ---------------------------------
    def _on_session_changed(self, _alive: bool) -> None:
        self._rebuild_sandbox_actions()

    def _rebuild_sandbox_actions(self, *_args) -> None:
        """Create only the controls whose operation can actually run now; a
        label states the reason wherever one is missing (carve-out 2)."""
        self._provision_button = None
        self._reset_button = None
        self._create_database_button = None
        self._new_database_name_edit = None
        _clear_layout(self._sandbox_actions_layout)

        controller = self._sandbox_controller
        if controller is None or self._project_dir is None:
            self._add_action_note(NO_CONTROLLER_REASON)
            return

        if self.sandbox_mode() is SandboxMode.SCHEMA_ONLY:
            self._add_action_note(BASELINE_CAVEAT)

        if not self.sandbox_params().host:
            self._add_action_note(NO_SANDBOX_REASON)
        elif not self.target_params().host:
            self._add_action_note(NO_TARGET_REASON)
        else:
            self._build_provisioning_rows()

        if controller.has_session:
            self._reset_button = self._add_action_button(
                "Reset sandbox", self.reset_sandbox
            )
            self._add_action_note(
                RESET_MODE_NOTE.format(mode=_MODE_LABELS[controller.mode])
            )
        else:
            self._add_action_note(NO_SESSION_REASON)

    def _build_provisioning_rows(self) -> None:
        """`Provision sandbox` plus D2's mandatory *"create a sandbox database
        for me"* mitigation, whose reason is `ForeignDatabaseError`'s own
        sentence when the configured database really is a foreign one."""
        self._provision_button = self._add_action_button(
            "Provision sandbox", self.provision_sandbox
        )
        caps = self._sandbox_controller.capabilities
        if caps is not None and caps.database and not is_app_owned(
            caps.database, caps.owner_marker
        ):
            # The refusal's own wording, never a second version of it.
            self._add_action_note(str(ForeignDatabaseError(caps.database)))
        self._add_action_note(CREATE_DATABASE_NOTE)
        row = QHBoxLayout()
        self._new_database_name_edit = QLineEdit(self._suggested_database_name())
        self._create_database_button = QPushButton("Create a sandbox database for me")
        self._create_database_button.clicked.connect(self.create_sandbox_database)
        row.addWidget(self._new_database_name_edit)
        row.addWidget(self._create_database_button)
        self._sandbox_actions_layout.addLayout(row)

    def _add_action_note(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        self._sandbox_actions_layout.addWidget(label)
        return label

    def _add_action_button(self, text: str, handler: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(handler)
        row = QHBoxLayout()
        row.addWidget(button)
        row.addStretch(1)
        self._sandbox_actions_layout.addLayout(row)
        return button

    def _suggested_database_name(self) -> str:
        current = self._sandbox_database_edit.text()
        if current.startswith(SANDBOX_DB_PREFIX):
            return current
        # §18.2's New Project auto-naming slug rule, imported rather than
        # re-derived, so the two surfaces suggest the same shape of name.
        return f"{SANDBOX_DB_PREFIX}{sandbox_name_stem(self._name_edit.text())}"

    def provision_sandbox(self) -> None:
        """**Destructive.** Record the settings as typed (including D2a's mode),
        then provision the configured sandbox database from the target."""
        self._provision(create_database=False)

    def create_sandbox_database(self) -> None:
        """**Destructive.** D2's mandatory mitigation: create a fresh app-owned
        sandbox database and provision it in the same operation."""
        self._provision(create_database=True)

    def _provision(self, *, create_database: bool) -> None:
        controller = self._sandbox_controller
        if controller is None or self._project_dir is None:
            self._report(NO_CONTROLLER_REASON)
            return
        if not self._confirmed(SandboxOperation.PROVISION):
            return
        database_name = (
            self._new_database_name_edit.text().strip()
            if create_database and self._new_database_name_edit is not None
            else ""
        )
        if create_database and not database_name:
            self._report(
                "Give the new sandbox database a name "
                f"('{SANDBOX_DB_PREFIX}…') before creating it."
            )
            return

        settings = self.settings()
        if database_name:
            settings = replace(
                settings, sandbox=replace(settings.sandbox, database=database_name)
            )
            # Keep the field and the recorded settings in agreement, so a later
            # OK writes the database that was actually created.
            self._sandbox_database_edit.setText(database_name)
        self._persist(settings)

        controller.set_project(
            sandbox_params=settings.sandbox,
            target_params=settings.target,
            mode=settings.sandbox_mode,
            configured=bool(settings.sandbox.host),
        )
        admin_params = (
            replace(settings.sandbox, database=self._maintenance_database)
            if database_name
            else None
        )
        controller.provision(
            self._on_sandbox_operation,
            admin_params=admin_params,
            database_name=database_name or None,
        )

    def reset_sandbox(self) -> None:
        """**Destructive.** `SandboxSession.reset()` -- drop every application
        schema and re-run whichever mode this sandbox was created with."""
        controller = self._sandbox_controller
        if controller is None:
            self._report(NO_CONTROLLER_REASON)
            return
        if not self._confirmed(SandboxOperation.RESET):
            return
        controller.reset_session(self._on_sandbox_operation)

    def _confirmed(self, operation: SandboxOperation) -> bool:
        """Ask the injected confirmation seam with the CONTROLLER's own warning
        text. No `QMessageBox` is ever constructed here (§30); with no seam
        injected the gesture proceeds to the controller, whose own
        `confirm_destructive` gate is then the single prompt."""
        if self._confirm is None:
            return True
        warning = SandboxController.destructive_warning(operation)
        if self._confirm(warning):
            return True
        self._report(f"Cancelled — this operation was not confirmed. {warning}".strip())
        return False

    def _persist(self, settings: ProjectSettings) -> None:
        """Write the settings a provisioning gesture is about to act on, BEFORE
        it runs -- D2a's mode is recorded, never re-derived from the database."""
        self._recorded_settings = settings
        self._settings_saver(self._project_dir, settings)

    def recorded_settings(self) -> ProjectSettings | None:
        """What a provisioning gesture persisted, or None if none has run. The
        host adopts this rather than re-reading the file it just wrote."""
        return self._recorded_settings

    def _on_sandbox_operation(self, result) -> None:
        """Report one `SandboxOperationResult` -- its stated `reason` always,
        success or failure, never swallowed -- then re-render."""
        name = result.operation.value.replace("_", " ")
        reason = (getattr(result, "reason", "") or "").strip()
        if result.ok:
            self._report(f"{name}: done." + (f" {reason}" if reason else ""))
        else:
            self._report(
                f"{name} failed: {reason}"
                if reason
                else f"{name} failed, and reported no reason."
            )
        self._rebuild_sandbox_actions()

    def _report(self, text: str) -> None:
        self._sandbox_action_status.setText(text)

    def sandbox_action_text(self) -> str:
        """The last reported provisioning outcome -- what the user sees."""
        return self._sandbox_action_status.text()

    def sandbox_action_notes(self) -> str:
        """Every reason-in-place-of-a-control the provisioning group shows."""
        return "\n".join(
            widget.text()
            for index in range(self._sandbox_actions_layout.count())
            if isinstance(
                widget := self._sandbox_actions_layout.itemAt(index).widget(), QLabel
            )
        )

    # --- Load / save the whole ProjectSettings -------------------------------
    def set_settings(self, settings: ProjectSettings) -> None:
        self._name_edit.setText(settings.name)
        self._description_edit.setText(settings.description)
        self._pgtp_source_edit.setText(settings.pgtp.source_path or "")
        self._pgtp_working_copy_edit.setText(settings.pgtp.working_copy_path or "")
        self._pgtp_checksum_edit.setText(settings.pgtp.last_known_source_checksum or "")
        self._set_connection_fields(
            settings.target,
            self._target_host_edit,
            self._target_port_edit,
            self._target_database_edit,
            self._target_user_edit,
            self._target_password_edit,
        )
        self._set_connection_fields(
            settings.sandbox,
            self._sandbox_host_edit,
            self._sandbox_port_edit,
            self._sandbox_database_edit,
            self._sandbox_user_edit,
            self._sandbox_password_edit,
        )
        if settings.sandbox_mode is SandboxMode.WITH_DATA:
            self._sandbox_mode_with_data_radio.setChecked(True)
        else:
            self._sandbox_mode_without_data_radio.setChecked(True)
        self._postgres_bin_dir_edit.setText(settings.postgres_bin_dir)
        self._git_server_edit.setText(settings.git.server)
        self._git_user_edit.setText(settings.git.user)
        self._git_branch_edit.setText(settings.git.checkout_branch)
        self._deployed_table.setRowCount(0)
        for relpath, entry in sorted(settings.deployed.items()):
            self._append_deployed_row(relpath, entry.content_hash, entry.deployed_commit or "")

    @staticmethod
    def _set_connection_fields(params: ConnectionParams, host, port, database, user, password) -> None:
        host.setText(params.host)
        port.setText(params.port)
        database.setText(params.database)
        user.setText(params.user)
        password.setText(params.password)

    def settings(self) -> ProjectSettings:
        return ProjectSettings(
            name=self._name_edit.text(),
            description=self._description_edit.text(),
            pgtp=PgtpLink(
                source_path=self._pgtp_source_edit.text() or None,
                working_copy_path=self._pgtp_working_copy_edit.text() or None,
                last_known_source_checksum=self._pgtp_checksum_edit.text() or None,
            ),
            target=self.target_params(),
            sandbox=self.sandbox_params(),
            sandbox_mode=self.sandbox_mode(),
            postgres_bin_dir=self.postgres_bin_dir(),
            git=GitConfig(
                server=self._git_server_edit.text(),
                user=self._git_user_edit.text(),
                checkout_branch=self._git_branch_edit.text(),
            ),
            deployed=self._deployed_from_table(),
        )

    @staticmethod
    def _connection_from_fields(host, port, database, user, password) -> ConnectionParams:
        return ConnectionParams(
            host=host.text(), port=port.text(), database=database.text(),
            user=user.text(), password=password.text(),
        )

    # --- Deploy manifest table ------------------------------------------------
    def _append_deployed_row(self, relpath: str, content_hash: str, deployed_commit: str) -> None:
        row = self._deployed_table.rowCount()
        self._deployed_table.insertRow(row)
        self._deployed_table.setItem(row, 0, QTableWidgetItem(relpath))
        self._deployed_table.setItem(row, 1, QTableWidgetItem(content_hash))
        self._deployed_table.setItem(row, 2, QTableWidgetItem(deployed_commit))

    def _add_deployed_row(self) -> None:
        self._append_deployed_row("", "", "")

    def _remove_selected_deployed_row(self) -> None:
        rows = {index.row() for index in self._deployed_table.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self._deployed_table.removeRow(row)

    def _deployed_from_table(self) -> dict[str, DeployedObject]:
        deployed: dict[str, DeployedObject] = {}
        for row in range(self._deployed_table.rowCount()):
            relpath = self._cell_text(row, 0)
            if not relpath:
                continue  # a blank Add-Row entry the user never filled in
            deployed[relpath] = DeployedObject(
                content_hash=self._cell_text(row, 1),
                deployed_commit=self._cell_text(row, 2) or None,
            )
        return deployed

    def _cell_text(self, row: int, column: int) -> str:
        item = self._deployed_table.item(row, column)
        return item.text() if item is not None else ""
