# tests/ui/test_new_project_dialog.py
"""Tests for NewProjectDialog (§18.2) — driven entirely by methods.

The dialog is never `.exec()`-ed (modal-hang guardrail); the sandbox Test
calls an injected prober stub, so no real connection is ever opened. The
folder picker is exercised by driving the underlying line edit / accept
logic rather than a real QFileDialog popup.
"""
from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import GitConfig
from pgtp_editor.db.sandbox import SandboxCapabilities, SandboxMode
from pgtp_editor.ui.new_project_dialog import NewProjectDialog


def _sync_run(fn, on_result, on_error=None):
    """Synchronous stand-in for run_async (same seam style as
    test_connection_setup_dialog.py)."""
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def test_name_and_description_round_trip(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("ERP overhaul")
    dialog._description_edit.setText("Q3 checkout")
    assert dialog.name() == "ERP overhaul"
    assert dialog.description() == "Q3 checkout"


def test_folder_starts_empty(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    assert dialog.folder() == ""


def test_browse_for_folder_sets_the_field(qtbot, tmp_path, monkeypatch):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "pgtp_editor.ui.new_project_dialog.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: str(tmp_path)),
    )

    dialog._browse_for_folder()

    assert dialog.folder() == str(tmp_path)


def test_cancelling_the_folder_picker_leaves_the_field_untouched(qtbot, monkeypatch):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText("/already/chosen")
    monkeypatch.setattr(
        "pgtp_editor.ui.new_project_dialog.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: ""),  # Cancel
    )

    dialog._browse_for_folder()

    assert dialog.folder() == "/already/chosen"


def test_accept_without_a_folder_shows_an_error_and_does_not_close(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    got = []
    dialog.accepted.connect(lambda: got.append(True))

    dialog._on_accept_clicked()

    assert got == []
    assert "folder" in dialog._folder_error_label.text().lower()


def test_accept_with_a_folder_closes_normally(qtbot, tmp_path):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path))
    got = []
    dialog.accepted.connect(lambda: got.append(True))

    dialog._on_accept_clicked()

    assert got == [True]


# --- Sandbox connection fields + superuser Test -----------------------------
def test_sandbox_params_round_trip(qtbot):
    """FQ-007: the server connection round-trips, and `database` is EMPTY --
    there is no field for it, because the app creates the database itself."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._sandbox_host_edit.setText("localhost")
    dialog._sandbox_port_edit.setText("5432")
    dialog._sandbox_user_edit.setText("dev")
    dialog._sandbox_password_edit.setText("pw")

    params = dialog.sandbox_params()

    assert params == ConnectionParams(
        host="localhost", port="5432", database="", user="dev", password="pw"
    )
    assert not hasattr(dialog, "_sandbox_database_edit")


def test_sandbox_password_field_uses_password_echo_mode(qtbot):
    from PySide6.QtWidgets import QLineEdit

    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    assert dialog._sandbox_password_edit.echoMode() == QLineEdit.EchoMode.Password


def test_test_sandbox_reports_superuser(qtbot):
    dialog = NewProjectDialog(prober=lambda params: SandboxCapabilities(is_superuser=True))
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "superuser" in dialog._sandbox_status_label.text().lower()
    assert "not a superuser" not in dialog._sandbox_status_label.text().lower()
    assert dialog._sandbox_test_button.isEnabled()


def test_test_sandbox_reports_connected_but_not_superuser(qtbot):
    dialog = NewProjectDialog(prober=lambda params: SandboxCapabilities(is_superuser=False))
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "not a superuser" in dialog._sandbox_status_label.text().lower()
    assert "create extension" in dialog._sandbox_status_label.text().lower()


def test_test_sandbox_reports_probe_error(qtbot):
    dialog = NewProjectDialog(
        prober=lambda params: SandboxCapabilities(probe_error="connection refused")
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "connection refused" in dialog._sandbox_status_label.text()


def test_test_sandbox_reports_an_exception_raised_by_the_prober(qtbot):
    def raising_prober(params):
        raise RuntimeError("no route to host")

    dialog = NewProjectDialog(prober=raising_prober)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "no route to host" in dialog._sandbox_status_label.text()
    assert dialog._sandbox_test_button.isEnabled()


def test_test_sandbox_shows_busy_status_then_result(qtbot):
    captured = {}

    def deferred(fn, on_result, on_error=None):
        captured["fn"] = fn
        captured["on_result"] = on_result

    dialog = NewProjectDialog(prober=lambda params: SandboxCapabilities(is_superuser=True))
    dialog._run_async = deferred
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "testing" in dialog._sandbox_status_label.text().lower()
    assert not dialog._sandbox_test_button.isEnabled()

    captured["on_result"](captured["fn"]())
    assert "superuser" in dialog._sandbox_status_label.text().lower()
    assert dialog._sandbox_test_button.isEnabled()


def test_uses_the_passed_params_not_stale_ones(qtbot):
    seen = []

    def prober(params):
        seen.append(params)
        return SandboxCapabilities(is_superuser=True)

    dialog = NewProjectDialog(prober=prober)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._sandbox_host_edit.setText("myhost")

    dialog.test_sandbox()

    assert seen[0].host == "myhost"


# --- "with data" / "without data" sandbox clone choice (§18.5 D2a) ----------
def test_sandbox_mode_defaults_to_schema_only(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    assert dialog.sandbox_mode() == SandboxMode.SCHEMA_ONLY


def test_selecting_with_data_radio_changes_sandbox_mode(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    dialog._sandbox_with_data_radio.setChecked(True)

    assert dialog.sandbox_mode() == SandboxMode.WITH_DATA


def test_reselecting_without_data_radio_reverts_sandbox_mode(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._sandbox_with_data_radio.setChecked(True)

    dialog._sandbox_without_data_radio.setChecked(True)

    assert dialog.sandbox_mode() == SandboxMode.SCHEMA_ONLY


def test_sandbox_mode_radios_are_mutually_exclusive(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    dialog._sandbox_with_data_radio.setChecked(True)

    assert not dialog._sandbox_without_data_radio.isChecked()


def test_with_data_caveat_mentions_one_shot_and_pg_dump_restore(qtbot):
    """§18.5 D2a: cloning is one-shot -- no refresh operation -- and needs
    pg_dump/pg_restore. The dialog must state this, not bury it."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    labels = [child.text() for child in dialog.findChildren(type(dialog._folder_error_label))]
    combined = " ".join(labels).lower()
    assert "pg_dump" in combined
    assert "pg_restore" in combined
    assert "one-shot" in combined or "destroy and recreate" in combined


def test_test_sandbox_with_data_mode_and_tools_present_reports_superuser(qtbot):
    dialog = NewProjectDialog(
        prober=lambda params: SandboxCapabilities(
            is_superuser=True, pg_dump_path="/usr/bin/pg_dump", pg_restore_path="/usr/bin/pg_restore"
        )
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._sandbox_with_data_radio.setChecked(True)

    dialog.test_sandbox()

    assert "superuser" in dialog._sandbox_status_label.text().lower()
    assert "not found" not in dialog._sandbox_status_label.text().lower()


def test_test_sandbox_with_data_mode_and_missing_tools_reports_named_failure(qtbot):
    """A missing pg_dump/pg_restore must be a named, surfaced failure --
    never silently accepted as if schema-only would kick in instead."""
    dialog = NewProjectDialog(
        prober=lambda params: SandboxCapabilities(
            is_superuser=True, pg_dump_path=None, pg_restore_path=None
        )
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._sandbox_with_data_radio.setChecked(True)

    dialog.test_sandbox()

    status = dialog._sandbox_status_label.text().lower()
    assert "pg_dump" in status
    assert "pg_restore" in status
    assert "not found" in status


def test_test_sandbox_without_data_mode_ignores_missing_clone_tools(qtbot):
    """Schema-only mode needs neither pg_dump nor pg_restore -- a missing
    binary must not be reported as a blocker when "without data" is chosen."""
    dialog = NewProjectDialog(
        prober=lambda params: SandboxCapabilities(
            is_superuser=True, pg_dump_path=None, pg_restore_path=None
        )
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    assert dialog.sandbox_mode() == SandboxMode.SCHEMA_ONLY

    dialog.test_sandbox()

    status = dialog._sandbox_status_label.text().lower()
    assert "superuser" in status
    assert "pg_dump" not in status


# --- Git fields: captured, inert ---------------------------------------------
def test_git_config_round_trips(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._git_server_edit.setText("git.example.com")
    dialog._git_user_edit.setText("dev")
    dialog._git_branch_edit.setText("feature/x")

    assert dialog.git_config() == GitConfig(
        server="git.example.com", user="dev", checkout_branch="feature/x"
    )


def test_git_config_defaults_to_empty(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    assert dialog.git_config() == GitConfig()


def test_git_section_states_it_is_not_yet_used(qtbot):
    """§18.2: git is optional/TBD -- the dialog must not imply otherwise."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    labels = [child.text() for child in dialog.findChildren(type(dialog._folder_error_label))]
    assert any("not yet" in text.lower() or "later" in text.lower() for text in labels)
