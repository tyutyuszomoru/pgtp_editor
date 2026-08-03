# tests/ui/test_project_settings_dialog.py
"""Tests for ProjectSettingsDialog (§18.2) -- the whole project JSON,
viewable and editable, never a simplified subset. Never `.exec()`-ed."""
from PySide6.QtWidgets import QLineEdit, QTableWidgetItem

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import DeployedObject, GitConfig, PgtpLink, ProjectSettings
from pgtp_editor.ui.project_settings_dialog import ProjectSettingsDialog


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


def test_set_settings_replaces_prior_contents_not_appends(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    dialog.set_settings(ProjectSettings(name="fresh"))

    assert dialog._name_edit.text() == "fresh"
    assert dialog._deployed_table.rowCount() == 0
