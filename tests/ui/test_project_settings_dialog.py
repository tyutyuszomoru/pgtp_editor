# tests/ui/test_project_settings_dialog.py
"""Tests for ProjectSettingsDialog (§18.2) -- the whole project JSON,
viewable and editable, never a simplified subset. Never `.exec()`-ed."""
from PySide6.QtWidgets import QLineEdit, QTableWidgetItem, QTabWidget

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import DeployedObject, GitConfig, PgtpLink, ProjectSettings
from pgtp_editor.db.sandbox import SandboxCapabilities, SandboxMode
from pgtp_editor.ui.project_settings_dialog import ProjectSettingsDialog


def _sync_run(fn, on_result, on_error=None):
    """Synchronous stand-in for run_async (same seam style as
    test_new_project_dialog.py / test_connection_setup_dialog.py)."""
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def _full_settings() -> ProjectSettings:
    return ProjectSettings(
        name="ERP overhaul",
        description="Q3 checkout",
        pgtp=PgtpLink(
            source_path="/mnt/quality/ERP_J01.pgtp",
            working_copy_path="/home/dev/proj/ERP_J01.pgtp",
            last_known_source_checksum="abc123",
        ),
        target=ConnectionParams(host="db01", port="5432", database="erp", user="dev", password="s3cr3t"),
        sandbox=ConnectionParams(host="localhost", port="5432", database="sandbox", user="dev", password="local"),
        git=GitConfig(server="git.example.com", user="dev", checkout_branch="feature/x"),
        deployed={
            "ddl/pr.recalc.sql": DeployedObject(content_hash="h1", deployed_commit=None),
            "ddl/pr.fmt_1.sql": DeployedObject(content_hash="h2", deployed_commit="abc1234"),
        },
    )


def test_set_settings_then_settings_round_trips_everything(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    assert dialog.settings() == _full_settings()


def test_identity_fields_are_populated(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)
    assert dialog._name_edit.text() == "ERP overhaul"
    assert dialog._description_edit.text() == "Q3 checkout"


def test_pgtp_link_fields_are_populated(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)
    assert dialog._pgtp_source_edit.text() == "/mnt/quality/ERP_J01.pgtp"
    assert dialog._pgtp_working_copy_edit.text() == "/home/dev/proj/ERP_J01.pgtp"
    assert dialog._pgtp_checksum_edit.text() == "abc123"


def test_editing_pgtp_fields_changes_the_settings_result(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    dialog._pgtp_source_edit.setText("/mnt/quality/new.pgtp")

    assert dialog.settings().pgtp.source_path == "/mnt/quality/new.pgtp"


def test_target_and_sandbox_connections_are_populated_independently(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)
    assert dialog._target_host_edit.text() == "db01"
    assert dialog._sandbox_host_edit.text() == "localhost"
    assert dialog._target_password_edit.text() == "s3cr3t"
    assert dialog._sandbox_password_edit.text() == "local"


def test_password_fields_use_password_echo_mode(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)
    assert dialog._target_password_edit.echoMode() == QLineEdit.EchoMode.Password
    assert dialog._sandbox_password_edit.echoMode() == QLineEdit.EchoMode.Password


def test_editing_target_connection_changes_the_settings_result(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    dialog._target_host_edit.setText("db02")

    assert dialog.settings().target.host == "db02"
    assert dialog.settings().sandbox.host == "localhost"  # unaffected


def test_git_fields_are_populated_and_editable(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)
    assert dialog._git_server_edit.text() == "git.example.com"

    dialog._git_branch_edit.setText("main")

    assert dialog.settings().git.checkout_branch == "main"


def test_deployed_table_is_populated_with_every_entry(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)
    assert dialog._deployed_table.rowCount() == 2


def test_deployed_table_can_edit_an_existing_entry(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    dialog._deployed_table.item(0, 1).setText("new-hash")

    result = dialog.settings().deployed
    relpath = dialog._deployed_table.item(0, 0).text()
    assert result[relpath].content_hash == "new-hash"


def test_deployed_table_add_row_then_fill_it_in(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings())
    qtbot.addWidget(dialog)

    dialog._add_deployed_row()
    dialog._deployed_table.setItem(0, 0, QTableWidgetItem("ddl/pr.new.sql"))
    dialog._deployed_table.setItem(0, 1, QTableWidgetItem("hash1"))

    result = dialog.settings().deployed
    assert result["ddl/pr.new.sql"] == DeployedObject(content_hash="hash1", deployed_commit=None)


def test_deployed_table_blank_added_row_is_dropped_from_the_result(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    dialog._add_deployed_row()  # left entirely blank

    assert len(dialog.settings().deployed) == 2  # blank row not carried through


def test_deployed_table_remove_selected_row(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)
    dialog._deployed_table.selectRow(0)

    dialog._remove_selected_deployed_row()

    assert dialog._deployed_table.rowCount() == 1
    assert len(dialog.settings().deployed) == 1


def test_empty_project_settings_populates_all_fields_blank(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings())
    qtbot.addWidget(dialog)
    assert dialog._name_edit.text() == ""
    assert dialog._pgtp_source_edit.text() == ""
    assert dialog._deployed_table.rowCount() == 0
    assert dialog.settings() == ProjectSettings()


# --- sandbox_mode (§18.5 D2a) -------------------------------------------------
def test_schema_only_sandbox_mode_selects_the_without_data_radio(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings(sandbox_mode=SandboxMode.SCHEMA_ONLY))
    qtbot.addWidget(dialog)
    assert dialog._sandbox_mode_without_data_radio.isChecked()
    assert not dialog._sandbox_mode_with_data_radio.isChecked()


def test_with_data_sandbox_mode_selects_the_with_data_radio(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings(sandbox_mode=SandboxMode.WITH_DATA))
    qtbot.addWidget(dialog)
    assert dialog._sandbox_mode_with_data_radio.isChecked()
    assert not dialog._sandbox_mode_without_data_radio.isChecked()


def test_sandbox_mode_round_trips_through_settings(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings(sandbox_mode=SandboxMode.WITH_DATA))
    qtbot.addWidget(dialog)
    assert dialog.settings().sandbox_mode == SandboxMode.WITH_DATA


def test_toggling_the_sandbox_mode_radio_changes_the_settings_result(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings(sandbox_mode=SandboxMode.SCHEMA_ONLY))
    qtbot.addWidget(dialog)

    dialog._sandbox_mode_with_data_radio.setChecked(True)

    assert dialog.settings().sandbox_mode == SandboxMode.WITH_DATA


def test_full_settings_round_trip_preserves_with_data_sandbox_mode(qtbot):
    settings = ProjectSettings(name="x", sandbox_mode=SandboxMode.WITH_DATA)
    dialog = ProjectSettingsDialog(settings)
    qtbot.addWidget(dialog)

    assert dialog.settings() == settings


def test_set_settings_replaces_prior_contents_not_appends(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    dialog.set_settings(ProjectSettings(name="fresh"))

    assert dialog._name_edit.text() == "fresh"
    assert dialog._deployed_table.rowCount() == 0


# --- tabbed layout (BUG-025) --------------------------------------------------
def test_dialog_exposes_a_tab_widget_with_the_expected_tabs(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    tabs = dialog.findChild(QTabWidget)
    assert tabs is not None
    titles = [tabs.tabText(i) for i in range(tabs.count())]
    assert titles == ["General", "Connections", "Git", "Deploy manifest"]


def test_non_current_tab_fields_are_still_populated_by_set_settings(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    tabs = dialog.findChild(QTabWidget)
    tabs.setCurrentIndex(0)  # "General" -- not the "Git" tab

    assert tabs.tabText(tabs.currentIndex()) != "Git"
    assert dialog._git_server_edit.text() == "git.example.com"


# --- connection Test buttons (FQ-001) ----------------------------------------
def test_target_test_reports_success_in_green(qtbot):
    dialog = ProjectSettingsDialog(
        _full_settings(), tester=lambda params: (True, "Connected to PostgreSQL 16.2")
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert dialog._target_status_label.text() == "Connected to PostgreSQL 16.2"
    assert "green" in dialog._target_status_label.styleSheet()
    assert dialog._target_test_button.isEnabled()


def test_target_test_reports_failure_in_red(qtbot):
    dialog = ProjectSettingsDialog(
        _full_settings(), tester=lambda params: (False, "could not connect to server")
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert dialog._target_status_label.text() == "could not connect to server"
    assert "red" in dialog._target_status_label.styleSheet()
    assert dialog._target_test_button.isEnabled()


def test_target_test_surfaces_a_raised_error_in_red(qtbot):
    def boom(params):
        raise RuntimeError("boom")

    dialog = ProjectSettingsDialog(_full_settings(), tester=boom)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert dialog._target_status_label.text() == "boom"
    assert "red" in dialog._target_status_label.styleSheet()
    assert dialog._target_test_button.isEnabled()


def test_target_test_uses_the_currently_typed_fields_not_the_saved_settings(qtbot):
    seen = []
    dialog = ProjectSettingsDialog(
        _full_settings(), tester=lambda params: (seen.append(params), (True, "ok"))[1]
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._target_host_edit.setText("db99")
    dialog._target_password_edit.setText("rotated")

    dialog.test_target()

    assert seen == [
        ConnectionParams(host="db99", port="5432", database="erp", user="dev", password="rotated")
    ]


def test_target_test_does_not_use_the_sandbox_fields(qtbot):
    seen = []
    dialog = ProjectSettingsDialog(
        _full_settings(), tester=lambda params: (seen.append(params), (True, "ok"))[1]
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert seen[0].host == "db01"
    assert seen[0].database == "erp"


def test_sandbox_test_reports_probe_error_in_red(qtbot):
    dialog = ProjectSettingsDialog(
        _full_settings(),
        prober=lambda params: SandboxCapabilities(probe_error="connection refused"),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert dialog._sandbox_status_label.text() == "connection refused"
    assert "red" in dialog._sandbox_status_label.styleSheet()
    assert dialog._sandbox_test_button.isEnabled()


def test_sandbox_test_non_superuser_is_a_red_failure_not_a_green_light(qtbot):
    """A connection that connects but is not a superuser must NOT get a green
    light -- that is exactly the failure mode the probe exists to catch."""
    dialog = ProjectSettingsDialog(
        _full_settings(), prober=lambda params: SandboxCapabilities(is_superuser=False)
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    status = dialog._sandbox_status_label.text()
    assert "NOT a superuser" in status
    assert "CREATE EXTENSION" in status
    assert "red" in dialog._sandbox_status_label.styleSheet()


def test_sandbox_test_with_data_mode_names_the_missing_clone_tools(qtbot):
    dialog = ProjectSettingsDialog(
        ProjectSettings(sandbox_mode=SandboxMode.WITH_DATA),
        prober=lambda params: SandboxCapabilities(
            is_superuser=True, pg_dump_path=None, pg_restore_path=None
        ),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    status = dialog._sandbox_status_label.text().lower()
    assert "pg_dump" in status
    assert "pg_restore" in status
    assert "not found" in status
    assert "red" in dialog._sandbox_status_label.styleSheet()


def test_sandbox_test_without_data_mode_ignores_missing_clone_tools(qtbot):
    dialog = ProjectSettingsDialog(
        ProjectSettings(sandbox_mode=SandboxMode.SCHEMA_ONLY),
        prober=lambda params: SandboxCapabilities(
            is_superuser=True, pg_dump_path=None, pg_restore_path=None
        ),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert dialog._sandbox_status_label.text() == "Connected — superuser."
    assert "green" in dialog._sandbox_status_label.styleSheet()


def test_sandbox_test_full_green_superuser_with_clone_tools(qtbot):
    dialog = ProjectSettingsDialog(
        ProjectSettings(sandbox_mode=SandboxMode.WITH_DATA),
        prober=lambda params: SandboxCapabilities(
            is_superuser=True,
            pg_dump_path="/usr/bin/pg_dump",
            pg_restore_path="/usr/bin/pg_restore",
        ),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert dialog._sandbox_status_label.text() == "Connected — superuser."
    assert "green" in dialog._sandbox_status_label.styleSheet()
    assert dialog._sandbox_test_button.isEnabled()


def test_sandbox_test_surfaces_a_raised_error_in_red(qtbot):
    def boom(params):
        raise RuntimeError("probe exploded")

    dialog = ProjectSettingsDialog(_full_settings(), prober=boom)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert dialog._sandbox_status_label.text() == "probe exploded"
    assert "red" in dialog._sandbox_status_label.styleSheet()
    assert dialog._sandbox_test_button.isEnabled()


def test_sandbox_test_uses_the_currently_typed_fields_not_the_saved_settings(qtbot):
    seen = []
    dialog = ProjectSettingsDialog(
        _full_settings(),
        prober=lambda params: (seen.append(params), SandboxCapabilities(is_superuser=True))[1],
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._sandbox_host_edit.setText("127.0.0.1")
    dialog._sandbox_user_edit.setText("postgres")

    dialog.test_sandbox()

    assert seen == [
        ConnectionParams(
            host="127.0.0.1", port="5432", database="sandbox", user="postgres", password="local"
        )
    ]


def test_test_buttons_are_disabled_while_a_test_is_in_flight(qtbot):
    pending = {}

    def deferred(fn, on_result, on_error=None):
        pending["fn"] = fn
        pending["on_result"] = on_result

    dialog = ProjectSettingsDialog(_full_settings(), tester=lambda params: (True, "ok"))
    dialog._run_async = deferred
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert not dialog._target_test_button.isEnabled()
    assert dialog._target_status_label.text() == "Testing connection…"

    pending["on_result"](pending["fn"]())

    assert dialog._target_test_button.isEnabled()


def test_test_buttons_and_status_labels_live_on_the_connections_tab(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    tabs = dialog.findChild(QTabWidget)
    connections_page = tabs.widget(
        [tabs.tabText(i) for i in range(tabs.count())].index("Connections")
    )

    assert dialog._target_test_button.text() == "Test"
    assert dialog._sandbox_test_button.text() == "Test"
    assert dialog._target_test_button.parent() is not None
    for widget in (
        dialog._target_test_button,
        dialog._sandbox_test_button,
        dialog._target_status_label,
        dialog._sandbox_status_label,
    ):
        assert connections_page.isAncestorOf(widget)


# --- BUG-034: the target the app really uses, shown here --------------------
def test_a_target_imported_from_the_pgtp_renders_populated(qtbot):
    """Guards the reported symptom directly: quality/target fields came up
    empty because nothing ever populated `ProjectSettings.target` from the
    `.pgtp`. Given a populated `.target`, the dialog must show it."""
    settings = ProjectSettings(
        target=ConnectionParams(
            host="dbhost", port="5433", database="erpdb", user="erp", password=""
        )
    )
    dialog = ProjectSettingsDialog(settings)
    qtbot.addWidget(dialog)

    assert dialog._target_host_edit.text() == "dbhost"
    assert dialog._target_port_edit.text() == "5433"
    assert dialog._target_database_edit.text() == "erpdb"
    assert dialog._target_user_edit.text() == "erp"
    assert dialog._target_password_edit.text() == ""
    assert dialog.target_params() == settings.target


def test_the_target_group_states_that_it_is_the_connection_actually_used(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings())
    qtbot.addWidget(dialog)

    note = dialog._target_note.text()
    assert "actually use" in note
    assert "Blank means no target is configured yet." in note
