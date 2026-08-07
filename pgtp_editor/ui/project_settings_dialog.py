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
this dialog persists nothing on its own.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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
from pgtp_editor.db.ddl_project import DeployedObject, GitConfig, PgtpLink, ProjectSettings
from pgtp_editor.db.introspect import test_connection
from pgtp_editor.db.sandbox import SandboxCapabilities, SandboxMode, probe
from pgtp_editor.ui.async_task import run_async

_DEPLOYED_COLUMNS = ("Path", "Content hash", "Deployed commit")

Tester = Callable[[ConnectionParams], "tuple[bool, str]"]
Prober = Callable[[ConnectionParams], SandboxCapabilities]


class ProjectSettingsDialog(QDialog):
    def __init__(
        self,
        settings: ProjectSettings,
        parent: QWidget | None = None,
        tester: Tester = test_connection,
        prober: Prober = probe,
    ) -> None:
        super().__init__(parent)
        # Test seams, same convention as ConnectionSetupDialog (generic
        # connectivity) and NewProjectDialog (sandbox superuser probe): both
        # flavors are reused verbatim rather than a third being invented.
        self._tester = tester
        self._prober = prober
        # Off-thread executor seam; tests replace it with a synchronous stub.
        self._run_async = run_async
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
            " the next time the sandbox is reset/recreated."
        )
        mode_note.setWordWrap(True)
        sandbox_mode_form = QFormLayout()
        sandbox_mode_form.addRow(self._sandbox_mode_without_data_radio)
        sandbox_mode_form.addRow(self._sandbox_mode_with_data_radio)
        sandbox_mode_form.addRow(mode_note)
        sandbox_group.layout().addRow(sandbox_mode_form)

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
    def _add_test_row(group: QGroupBox, slot: Callable[[], None]) -> tuple[QPushButton, QLabel]:
        """The Test button + inline colored status label row, same shape as
        `ConnectionSetupDialog` / `NewProjectDialog` (FQ-001)."""
        test_button = QPushButton("Test")
        test_button.clicked.connect(slot)
        status_label = QLabel("")
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

    def test_target(self) -> None:
        """Generic connectivity check, identical to `ConnectionSetupDialog.test`.
        Run off the GUI thread so an unreachable host can't freeze the dialog."""
        self._target_test_button.setEnabled(False)
        self._target_status_label.setStyleSheet("")
        self._target_status_label.setText("Testing connection…")
        params = self.target_params()

        def on_result(result: "tuple[bool, str]") -> None:
            ok, message = result
            color = "green" if ok else "red"
            self._target_status_label.setText(message)
            self._target_status_label.setStyleSheet(f"color: {color};")
            self._target_test_button.setEnabled(True)

        def on_error(exc: BaseException) -> None:
            self._target_status_label.setText(str(exc))
            self._target_status_label.setStyleSheet("color: red;")
            self._target_test_button.setEnabled(True)

        self._run_async(lambda: self._tester(params), on_result=on_result, on_error=on_error)

    def test_sandbox(self) -> None:
        """Superuser-specific probe, identical to `NewProjectDialog.test_sandbox`
        -- NOT a plain connectivity check, which would give a false green light
        to a connection that connects but can't `CREATE EXTENSION` (§18.5 D2)."""
        self._sandbox_test_button.setEnabled(False)
        self._sandbox_status_label.setStyleSheet("")
        self._sandbox_status_label.setText("Testing…")
        params = self.sandbox_params()

        def on_result(caps: SandboxCapabilities) -> None:
            self._apply_sandbox_probe_result(caps)

        def on_error(exc: BaseException) -> None:
            self._sandbox_status_label.setText(str(exc))
            self._sandbox_status_label.setStyleSheet("color: red;")
            self._sandbox_test_button.setEnabled(True)

        self._run_async(lambda: self._prober(params), on_result=on_result, on_error=on_error)

    def _apply_sandbox_probe_result(self, caps: SandboxCapabilities) -> None:
        self._sandbox_test_button.setEnabled(True)
        if caps.probe_error is not None:
            self._sandbox_status_label.setText(caps.probe_error)
            self._sandbox_status_label.setStyleSheet("color: red;")
            return
        if not caps.is_superuser:
            self._sandbox_status_label.setText(
                "Connected, but NOT a superuser — sandbox provisioning needs CREATE EXTENSION."
            )
            self._sandbox_status_label.setStyleSheet("color: red;")
            return
        if self.sandbox_mode() is SandboxMode.WITH_DATA and not caps.data_clone_available:
            missing = [
                name
                for name, path in (("pg_dump", caps.pg_dump_path), ("pg_restore", caps.pg_restore_path))
                if path is None
            ]
            self._sandbox_status_label.setText(
                "Connected — superuser, but 'with data' needs "
                f"{' and '.join(missing)} on PATH (not found)."
            )
            self._sandbox_status_label.setStyleSheet("color: red;")
            return
        self._sandbox_status_label.setText("Connected — superuser.")
        self._sandbox_status_label.setStyleSheet("color: green;")

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
