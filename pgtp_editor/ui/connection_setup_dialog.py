# pgtp_editor/ui/connection_setup_dialog.py
"""The Database Connection Setup dialog.

Shown non-modally (`show()`, never `.exec()`) so tests can drive it purely
through methods: `set_params`, `params`, and `test`. The connection Test uses
an injectable `tester=` callable (default: `db.introspect.test_connection`) so
tests stub it and never open a real connection.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.introspect import test_connection

Tester = Callable[[ConnectionParams], "tuple[bool, str]"]


class ConnectionSetupDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        tester: Tester = test_connection,
    ) -> None:
        super().__init__(parent)
        self._tester = tester
        self.setWindowTitle("Database Connection Setup")

        self._host_edit = QLineEdit()
        self._port_edit = QLineEdit()
        self._database_edit = QLineEdit()
        self._user_edit = QLineEdit()
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout()
        form.addRow("Host:", self._host_edit)
        form.addRow("Port:", self._port_edit)
        form.addRow("Database:", self._database_edit)
        form.addRow("User:", self._user_edit)
        form.addRow("Password:", self._password_edit)

        self._test_button = QPushButton("Test")
        self._test_button.clicked.connect(self.test)
        self._status_label = QLabel("")
        test_row = QHBoxLayout()
        test_row.addWidget(self._test_button)
        test_row.addWidget(self._status_label, 1)

        self._caveat_label = QLabel(
            "Password is stored in app settings in plain text."
        )
        self._caveat_label.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(test_row)
        layout.addWidget(self._caveat_label)
        layout.addWidget(buttons)

    def set_params(self, params: ConnectionParams) -> None:
        self._host_edit.setText(params.host)
        self._port_edit.setText(params.port)
        self._database_edit.setText(params.database)
        self._user_edit.setText(params.user)
        self._password_edit.setText(params.password)

    def params(self) -> ConnectionParams:
        return ConnectionParams(
            host=self._host_edit.text(),
            port=self._port_edit.text(),
            database=self._database_edit.text(),
            user=self._user_edit.text(),
            password=self._password_edit.text(),
        )

    def test(self) -> None:
        ok, message = self._tester(self.params())
        color = "green" if ok else "red"
        self._status_label.setText(message)
        self._status_label.setStyleSheet(f"color: {color};")
