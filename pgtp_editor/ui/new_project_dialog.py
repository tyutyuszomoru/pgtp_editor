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

# pgtp_editor/ui/new_project_dialog.py
"""The New Project dialog (§18.2).

A local project is a **folder the user chooses** -- not necessarily a git
repository. This dialog collects that folder plus two OPTIONAL sections:

- **Local sandbox** -- a Postgres connection whose **Test** button has one
  specific job: verifying the connected user is a **superuser** (sandbox
  provisioning needs `CREATE EXTENSION`), reusing `db/sandbox.py::probe` as
  the same capability probe the later sandbox lane uses -- not a second,
  ad hoc superuser check.
- **Git** -- server/user/checkout-branch fields, captured but **inert**
  (§18.2: "explicit TBD/placeholder only, not designed"). No Test button,
  no validation beyond being present -- nothing reads these fields yet
  except `db/ddl_project.py::GitConfig`'s round-trip through the project's
  own settings JSON.

Shown non-modally (`show()`, never `.exec()`), same convention as
`ConnectionSetupDialog`: callers read back the collected fields via getters
after `accepted` fires and perform the actual folder-creation / settings-
write themselves -- this dialog persists nothing on its own.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import GitConfig
from pgtp_editor.db.sandbox import SandboxCapabilities, probe
from pgtp_editor.ui.async_task import run_async

Prober = Callable[[ConnectionParams], SandboxCapabilities]


class NewProjectDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        prober: Prober = probe,
    ) -> None:
        super().__init__(parent)
        self._prober = prober
        # Off-thread executor seam, same convention as ConnectionSetupDialog:
        # tests replace this with a synchronous stub for determinism.
        self._run_async = run_async
        self.setWindowTitle("New Project")

        identity_form = QFormLayout()
        self._name_edit = QLineEdit()
        self._description_edit = QLineEdit()
        identity_form.addRow("Name:", self._name_edit)
        identity_form.addRow("Description:", self._description_edit)

        self._folder_edit = QLineEdit()
        self._folder_edit.setReadOnly(True)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_for_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder_edit, 1)
        folder_row.addWidget(browse_button)
        folder_form = QFormLayout()
        folder_form.addRow("Project folder:", folder_row)

        sandbox_group = QGroupBox("Local sandbox (optional)")
        self._sandbox_host_edit = QLineEdit()
        self._sandbox_port_edit = QLineEdit()
        self._sandbox_database_edit = QLineEdit()
        self._sandbox_user_edit = QLineEdit()
        self._sandbox_password_edit = QLineEdit()
        self._sandbox_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        sandbox_form = QFormLayout()
        sandbox_form.addRow("Host:", self._sandbox_host_edit)
        sandbox_form.addRow("Port:", self._sandbox_port_edit)
        sandbox_form.addRow("Database:", self._sandbox_database_edit)
        sandbox_form.addRow("User:", self._sandbox_user_edit)
        sandbox_form.addRow("Password:", self._sandbox_password_edit)
        self._sandbox_test_button = QPushButton("Test")
        self._sandbox_test_button.clicked.connect(self.test_sandbox)
        self._sandbox_status_label = QLabel("")
        sandbox_test_row = QHBoxLayout()
        sandbox_test_row.addWidget(self._sandbox_test_button)
        sandbox_test_row.addWidget(self._sandbox_status_label, 1)
        sandbox_layout = QVBoxLayout(sandbox_group)
        sandbox_layout.addLayout(sandbox_form)
        sandbox_layout.addLayout(sandbox_test_row)

        git_group = QGroupBox("Git (optional -- not yet used)")
        self._git_server_edit = QLineEdit()
        self._git_user_edit = QLineEdit()
        self._git_branch_edit = QLineEdit()
        git_form = QFormLayout()
        git_form.addRow("Server:", self._git_server_edit)
        git_form.addRow("User:", self._git_user_edit)
        git_form.addRow("Checkout branch:", self._git_branch_edit)
        git_caveat = QLabel(
            "Recorded for later -- git integration is not yet built. Nothing"
            " is cloned, committed, or pushed."
        )
        git_caveat.setWordWrap(True)
        git_layout = QVBoxLayout(git_group)
        git_layout.addLayout(git_form)
        git_layout.addWidget(git_caveat)

        self._folder_error_label = QLabel("")
        self._folder_error_label.setStyleSheet("color: red;")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept_clicked)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(identity_form)
        layout.addLayout(folder_form)
        layout.addWidget(sandbox_group)
        layout.addWidget(git_group)
        layout.addWidget(self._folder_error_label)
        layout.addWidget(buttons)

    # --- Folder picking -----------------------------------------------------
    def _browse_for_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "New Project Folder", self._folder_edit.text())
        if not folder:
            return
        self._folder_edit.setText(folder)
        self._folder_error_label.setText("")

    def _on_accept_clicked(self) -> None:
        if not self.folder():
            self._folder_error_label.setText("Choose a project folder first.")
            return
        self.accept()

    # --- Getters (read after `accepted` fires) -------------------------------
    def name(self) -> str:
        return self._name_edit.text()

    def description(self) -> str:
        return self._description_edit.text()

    def folder(self) -> str:
        return self._folder_edit.text()

    def sandbox_params(self) -> ConnectionParams:
        return ConnectionParams(
            host=self._sandbox_host_edit.text(),
            port=self._sandbox_port_edit.text(),
            database=self._sandbox_database_edit.text(),
            user=self._sandbox_user_edit.text(),
            password=self._sandbox_password_edit.text(),
        )

    def git_config(self) -> GitConfig:
        return GitConfig(
            server=self._git_server_edit.text(),
            user=self._git_user_edit.text(),
            checkout_branch=self._git_branch_edit.text(),
        )

    # --- Sandbox superuser Test ----------------------------------------------
    def test_sandbox(self) -> None:
        """Verify the sandbox connection specifically for **superuser**, not
        merely "can connect" -- sandbox provisioning needs `CREATE EXTENSION`
        (§18.5 D2). Reuses `db/sandbox.py::probe`, run off the GUI thread so
        an unreachable host can't freeze the dialog."""
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

        self._run_async(
            lambda: self._prober(params),
            on_result=on_result,
            on_error=on_error,
        )

    def _apply_sandbox_probe_result(self, caps: SandboxCapabilities) -> None:
        self._sandbox_test_button.setEnabled(True)
        if caps.probe_error is not None:
            self._sandbox_status_label.setText(caps.probe_error)
            self._sandbox_status_label.setStyleSheet("color: red;")
            return
        if caps.is_superuser:
            self._sandbox_status_label.setText("Connected — superuser.")
            self._sandbox_status_label.setStyleSheet("color: green;")
            return
        self._sandbox_status_label.setText(
            "Connected, but NOT a superuser — sandbox provisioning needs CREATE EXTENSION."
        )
        self._sandbox_status_label.setStyleSheet("color: red;")
