# tests/ui/test_connection_setup_dialog.py
"""Tests for ConnectionSetupDialog — driven entirely by methods.

The dialog is never `.exec()`-ed (modal-hang guardrail); `test()` calls an
injected tester stub, so no real connection is ever opened.
"""
from PySide6.QtWidgets import QLineEdit

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.ui.connection_setup_dialog import ConnectionSetupDialog


def test_set_params_and_params_round_trip(qtbot):
    dialog = ConnectionSetupDialog()
    qtbot.addWidget(dialog)
    params = ConnectionParams(
        host="db.example", port="5432", database="mydb", user="me", password="pw"
    )
    dialog.set_params(params)
    assert dialog.params() == params


def test_password_field_uses_password_echo_mode(qtbot):
    dialog = ConnectionSetupDialog()
    qtbot.addWidget(dialog)
    assert dialog._password_edit.echoMode() == QLineEdit.EchoMode.Password


def test_test_button_ok_sets_status(qtbot):
    calls = []

    def tester(params):
        calls.append(params)
        return True, "Connected."

    dialog = ConnectionSetupDialog(tester=tester)
    qtbot.addWidget(dialog)
    dialog.set_params(ConnectionParams(host="h", port="5432", database="d", user="u"))
    dialog.test()

    assert len(calls) == 1
    assert calls[0].host == "h"
    assert "Connected." in dialog._status_label.text()


def test_test_button_error_sets_status(qtbot):
    def tester(params):
        return False, "auth failed"

    dialog = ConnectionSetupDialog(tester=tester)
    qtbot.addWidget(dialog)
    dialog.test()

    assert "auth failed" in dialog._status_label.text()


def test_has_plaintext_caveat_label(qtbot):
    dialog = ConnectionSetupDialog()
    qtbot.addWidget(dialog)
    assert "plain text" in dialog._caveat_label.text().lower()
