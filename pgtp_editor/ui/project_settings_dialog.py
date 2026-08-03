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

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import DeployedObject, GitConfig, PgtpLink, ProjectSettings

_DEPLOYED_COLUMNS = ("Path", "Content hash", "Deployed commit")


class ProjectSettingsDialog(QDialog):
    def __init__(self, settings: ProjectSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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

        sandbox_group = QGroupBox("Sandbox connection")
        (
            self._sandbox_host_edit,
            self._sandbox_port_edit,
            self._sandbox_database_edit,
            self._sandbox_user_edit,
            self._sandbox_password_edit,
        ) = self._build_connection_form(sandbox_group)

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

        layout = QVBoxLayout(self)
        layout.addLayout(identity_form)
        layout.addWidget(pgtp_group)
        layout.addWidget(target_group)
        layout.addWidget(sandbox_group)
        layout.addWidget(git_group)
        layout.addWidget(deployed_group)
        layout.addWidget(buttons)

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
            target=self._connection_from_fields(
                self._target_host_edit,
                self._target_port_edit,
                self._target_database_edit,
                self._target_user_edit,
                self._target_password_edit,
            ),
            sandbox=self._connection_from_fields(
                self._sandbox_host_edit,
                self._sandbox_port_edit,
                self._sandbox_database_edit,
                self._sandbox_user_edit,
                self._sandbox_password_edit,
            ),
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
