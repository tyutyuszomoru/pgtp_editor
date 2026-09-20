# tests/ui/test_project_settings_dialog.py
"""Tests for ProjectSettingsDialog (§18.2) -- the whole project JSON,
viewable and editable, never a simplified subset. Never `.exec()`-ed."""
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLineEdit, QPushButton, QTableWidgetItem, QTabWidget

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import DeployedObject, GitConfig, PgtpLink, ProjectSettings
from pgtp_editor.db.sandbox import SandboxCapabilities, SandboxMode
from pgtp_editor.ui.project_settings_dialog import ProjectSettingsDialog
from pgtp_editor.ui.status_colours import STATUS_ERROR, STATUS_OK


def _sync_run(fn, on_result, on_error=None):
    """Synchronous stand-in for run_async (same seam style as
    test_new_project_dialog.py / test_connection_setup_dialog.py)."""
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def _offline_prober(server_version=(16, 0, 3), **fields):
    """A `Prober` stub. Required wherever the TARGET Test button is exercised:
    that button now asks the prober for the server version after the tester
    reports success (FQ-260812025353), and the real default `probe` would open
    a psycopg connection."""
    return lambda params, **_: SandboxCapabilities(server_version=server_version, **fields)


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
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    dialog = ProjectSettingsDialog(
        _full_settings(),
        tester=lambda params: (True, "Connected to PostgreSQL 16.2"),
        prober=_offline_prober(),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert dialog._target_status_label.text() == (
        "Connected to PostgreSQL 16.2 Server: PostgreSQL 16.0.3."
    )
    assert dialog._target_status_label.status_kind() == STATUS_OK
    assert dialog._target_test_button.isEnabled()


def test_target_test_reports_failure_in_red(qtbot):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    dialog = ProjectSettingsDialog(
        _full_settings(),
        tester=lambda params: (False, "could not connect to server"),
        prober=_offline_prober(),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert dialog._target_status_label.text() == "could not connect to server"
    assert dialog._target_status_label.status_kind() == STATUS_ERROR
    assert dialog._target_test_button.isEnabled()


def test_target_test_surfaces_a_raised_error_in_red(qtbot):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    def boom(params):
        raise RuntimeError("boom")

    dialog = ProjectSettingsDialog(_full_settings(), tester=boom)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert dialog._target_status_label.text() == "boom"
    assert dialog._target_status_label.status_kind() == STATUS_ERROR
    assert dialog._target_test_button.isEnabled()


def test_target_test_uses_the_currently_typed_fields_not_the_saved_settings(qtbot):
    seen = []
    dialog = ProjectSettingsDialog(
        _full_settings(),
        tester=lambda params: (seen.append(params), (True, "ok"))[1],
        prober=_offline_prober(),
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
        _full_settings(),
        tester=lambda params: (seen.append(params), (True, "ok"))[1],
        prober=_offline_prober(),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert seen[0].host == "db01"
    assert seen[0].database == "erp"


def test_sandbox_test_reports_probe_error_in_red(qtbot):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    dialog = ProjectSettingsDialog(
        _full_settings(),
        prober=lambda params, **_: SandboxCapabilities(probe_error="connection refused"),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert dialog._sandbox_status_label.text() == "connection refused"
    assert dialog._sandbox_status_label.status_kind() == STATUS_ERROR
    assert dialog._sandbox_test_button.isEnabled()


def test_sandbox_test_non_superuser_is_a_red_failure_not_a_green_light(qtbot):
    """A connection that connects but is not a superuser must NOT get a green
    light -- that is exactly the failure mode the probe exists to catch.

    Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    dialog = ProjectSettingsDialog(
        _full_settings(), prober=lambda params, **_: SandboxCapabilities(is_superuser=False)
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    status = dialog._sandbox_status_label.text()
    assert "NOT a superuser" in status
    assert "CREATE EXTENSION" in status
    assert dialog._sandbox_status_label.status_kind() == STATUS_ERROR


def test_sandbox_test_with_data_mode_names_the_missing_clone_tools(qtbot):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    dialog = ProjectSettingsDialog(
        ProjectSettings(sandbox_mode=SandboxMode.WITH_DATA),
        prober=lambda params, **_: SandboxCapabilities(
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
    assert dialog._sandbox_status_label.status_kind() == STATUS_ERROR


def test_sandbox_test_without_data_mode_ignores_missing_clone_tools(qtbot):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    dialog = ProjectSettingsDialog(
        ProjectSettings(sandbox_mode=SandboxMode.SCHEMA_ONLY),
        prober=lambda params, **_: SandboxCapabilities(
            is_superuser=True, pg_dump_path=None, pg_restore_path=None
        ),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert dialog._sandbox_status_label.text() == "Connected — superuser."
    assert dialog._sandbox_status_label.status_kind() == STATUS_OK


def test_sandbox_test_full_green_superuser_with_clone_tools(qtbot):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    dialog = ProjectSettingsDialog(
        ProjectSettings(sandbox_mode=SandboxMode.WITH_DATA),
        prober=lambda params, **_: SandboxCapabilities(
            is_superuser=True,
            pg_dump_path="/usr/bin/pg_dump",
            pg_restore_path="/usr/bin/pg_restore",
        ),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert dialog._sandbox_status_label.text() == "Connected — superuser."
    assert dialog._sandbox_status_label.status_kind() == STATUS_OK
    assert dialog._sandbox_test_button.isEnabled()


def test_sandbox_test_surfaces_a_raised_error_in_red(qtbot):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    def boom(params, **_):
        raise RuntimeError("probe exploded")

    dialog = ProjectSettingsDialog(_full_settings(), prober=boom)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert dialog._sandbox_status_label.text() == "probe exploded"
    assert dialog._sandbox_status_label.status_kind() == STATUS_ERROR
    assert dialog._sandbox_test_button.isEnabled()


def test_sandbox_test_uses_the_currently_typed_fields_not_the_saved_settings(qtbot):
    seen = []
    dialog = ProjectSettingsDialog(
        _full_settings(),
        prober=lambda params, **_: (seen.append(params), SandboxCapabilities(is_superuser=True))[1],
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

    dialog = ProjectSettingsDialog(
        _full_settings(),
        tester=lambda params: (True, "ok"),
        prober=_offline_prober(),
    )
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


# --- BUG-036: opening size ---------------------------------------------------
def test_opens_at_560x760_and_stays_resizable(qtbot):
    """BUG-036 #1. 560x760 is the *opening* size, not a lock: the dialog must
    still grow and shrink afterwards, so the assertion pairs the size with the
    absence of any fixed-size constraint. A `setFixedSize` would pass the first
    assert and fail the rest."""
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    assert dialog.size() == QSize(560, 760)
    # Not fixed: the maximum is left far above the opening size, so it can grow...
    assert dialog.maximumWidth() > 560
    assert dialog.maximumHeight() > 760
    # ...and its minimum stays strictly smaller, so it can shrink.
    assert dialog.minimumWidth() < 560
    assert dialog.minimumHeight() < 760


def test_every_tab_fits_at_the_opening_size(qtbot):
    """The BUG-036 acceptance criterion ("at open it should show all
    information") is a claim about content, not about the `resize()` call: at
    560x760 no tab may need more room than it has."""
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)
    dialog.show()

    tabs = dialog.findChild(QTabWidget)
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        page = tabs.widget(index)
        needed = page.minimumSizeHint()
        assert needed.width() <= page.width(), tabs.tabText(index)
        assert needed.height() <= page.height(), tabs.tabText(index)


# --- FQ-260812025353: the "Locate postgres binaries" folder -------------------
def _make_tool(folder, name):
    path = folder / name
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    return str(path)


def test_binaries_folder_defaults_to_empty_which_means_path(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings())
    qtbot.addWidget(dialog)

    assert dialog.postgres_bin_dir() == ""
    assert dialog.settings().postgres_bin_dir == ""
    assert "PATH" in dialog.bin_dir_status_text()


def test_binaries_folder_is_populated_and_round_trips(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings(postgres_bin_dir="/opt/pg17/bin"))
    qtbot.addWidget(dialog)

    assert dialog._postgres_bin_dir_edit.text() == "/opt/pg17/bin"
    assert dialog.settings().postgres_bin_dir == "/opt/pg17/bin"


def test_editing_the_binaries_folder_changes_the_settings_result(qtbot):
    dialog = ProjectSettingsDialog(ProjectSettings())
    qtbot.addWidget(dialog)

    dialog._postgres_bin_dir_edit.setText("/opt/pg16/bin")

    assert dialog.settings().postgres_bin_dir == "/opt/pg16/bin"


def test_browse_writes_the_chosen_folder_into_the_field(qtbot):
    dialog = ProjectSettingsDialog(
        ProjectSettings(), folder_chooser=lambda *_a: "/opt/pg18/bin"
    )
    qtbot.addWidget(dialog)

    dialog.browse_for_postgres_bin_dir()

    assert dialog.settings().postgres_bin_dir == "/opt/pg18/bin"


def test_browse_cancelled_leaves_the_field_untouched(qtbot):
    dialog = ProjectSettingsDialog(
        ProjectSettings(postgres_bin_dir="/keep/me"), folder_chooser=lambda *_a: ""
    )
    qtbot.addWidget(dialog)

    dialog.browse_for_postgres_bin_dir()

    assert dialog.settings().postgres_bin_dir == "/keep/me"


def test_a_complete_binaries_folder_reports_both_tools_found(qtbot, tmp_path):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    _make_tool(tmp_path, "pg_dump")
    _make_tool(tmp_path, "pg_restore")
    dialog = ProjectSettingsDialog(ProjectSettings())
    qtbot.addWidget(dialog)

    dialog._postgres_bin_dir_edit.setText(str(tmp_path))

    assert "Found" in dialog.bin_dir_status_text()
    assert dialog._bin_dir_status_label.status_kind() == STATUS_OK


def test_an_incomplete_binaries_folder_warns_but_does_not_block(qtbot, tmp_path):
    """Warn, never block: PATH is still a legitimate fallback and the user may
    be mid-typing a path."""
    _make_tool(tmp_path, "pg_dump")
    dialog = ProjectSettingsDialog(ProjectSettings())
    qtbot.addWidget(dialog)

    dialog._postgres_bin_dir_edit.setText(str(tmp_path))

    assert "pg_restore" in dialog.bin_dir_status_text()
    assert "pg_dump" not in dialog.bin_dir_status_text()
    # Nothing is disabled and the value is still saveable.
    assert dialog.settings().postgres_bin_dir == str(tmp_path)


def test_the_binaries_group_lives_on_the_connections_tab(qtbot):
    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)

    tabs = dialog.findChild(QTabWidget)
    connections_page = tabs.widget(
        [tabs.tabText(i) for i in range(tabs.count())].index("Connections")
    )

    assert dialog._postgres_bin_dir_edit in connections_page.findChildren(QLineEdit)
    assert dialog._browse_bin_dir_button in connections_page.findChildren(QPushButton)


def test_the_sandbox_test_passes_the_typed_binaries_folder_to_the_probe(qtbot):
    seen = {}

    def prober(params, **kwargs):
        seen.update(kwargs)
        return SandboxCapabilities(is_superuser=True, server_version=(16, 0, 3))

    dialog = ProjectSettingsDialog(_full_settings(), prober=prober)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._postgres_bin_dir_edit.setText("/opt/pg16/bin")

    dialog.test_sandbox()

    assert seen["bin_dir"] == "/opt/pg16/bin"


def test_the_target_test_passes_the_typed_binaries_folder_to_the_probe(qtbot):
    seen = {}

    def prober(params, **kwargs):
        seen.update(kwargs)
        return SandboxCapabilities(server_version=(16, 0, 3))

    dialog = ProjectSettingsDialog(
        _full_settings(), tester=lambda params: (True, "Connected."), prober=prober
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._postgres_bin_dir_edit.setText("/opt/pg16/bin")

    dialog.test_target()

    assert seen["bin_dir"] == "/opt/pg16/bin"


# --- the Test buttons report the server version ------------------------------
def test_the_sandbox_test_reports_the_server_version(qtbot):
    dialog = ProjectSettingsDialog(
        _full_settings(),
        prober=_offline_prober(server_version=(18, 0, 1), is_superuser=True),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert dialog._sandbox_status_label.text() == (
        "Connected — superuser. Server: PostgreSQL 18.0.1."
    )


def test_the_target_test_reports_the_server_version(qtbot):
    dialog = ProjectSettingsDialog(
        _full_settings(),
        tester=lambda params: (True, "Connected."),
        prober=_offline_prober(server_version=(15, 0, 6)),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert dialog._target_status_label.text() == "Connected. Server: PostgreSQL 15.0.6."


def test_an_unknown_server_version_appends_nothing_rather_than_inventing_one(qtbot):
    dialog = ProjectSettingsDialog(
        _full_settings(),
        tester=lambda params: (True, "Connected."),
        prober=_offline_prober(server_version=()),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert dialog._target_status_label.text() == "Connected."


def test_a_failed_target_test_never_asks_the_prober_for_a_version(qtbot):
    def prober(params, **kwargs):  # pragma: no cover -- must never be reached
        raise AssertionError("an unreachable host must cost one attempt, not two")

    dialog = ProjectSettingsDialog(
        _full_settings(), tester=lambda params: (False, "refused"), prober=prober
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_target()

    assert dialog._target_status_label.text() == "refused"


def test_the_sandbox_test_names_the_CONFIGURED_FOLDER_when_there_is_one(qtbot, monkeypatch):
    """`FQ-260812025353` made the binaries folder searched BEFORE `PATH`, which
    turned "on PATH (not found)" into a sentence that sends a user who set a
    folder off to edit their PATH instead. Same correction already applied to
    `determine_project_tier`'s degraded reason and `MissingCloneToolError`.

    Pinning both branches in one test on purpose: the PATH-only wording is what
    the manual documents, and it must not drift while the folder branch is
    added beside it.
    """
    from pgtp_editor.db.sandbox import SandboxCapabilities

    caps = SandboxCapabilities(is_superuser=True, pg_dump_path=None, pg_restore_path=None)

    dialog = ProjectSettingsDialog(_full_settings())
    qtbot.addWidget(dialog)
    # The missing-tools branch is WITH_DATA-only: a schema-only sandbox
    # needs neither binary, so it never reaches the sentence under test.
    dialog._sandbox_mode_with_data_radio.setChecked(True)

    dialog._postgres_bin_dir_edit.setText("")
    dialog._apply_sandbox_probe_result(caps)
    on_path_only = dialog._sandbox_status_label.text()
    assert "on PATH (not found)" in on_path_only
    assert "pg_dump and pg_restore" in on_path_only

    dialog._postgres_bin_dir_edit.setText("/opt/pg16/bin")
    dialog._apply_sandbox_probe_result(caps)
    with_folder = dialog._sandbox_status_label.text()
    assert "/opt/pg16/bin" in with_folder
    assert "or on PATH" in with_folder
    assert "pg_dump and pg_restore" in with_folder
