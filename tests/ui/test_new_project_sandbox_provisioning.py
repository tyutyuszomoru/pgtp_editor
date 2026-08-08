# tests/ui/test_new_project_sandbox_provisioning.py
"""FQ-007 -- the New Project sandbox step CREATES and provisions the sandbox
database instead of asking for an existing one (§18.2 + §18.5 D2).

What is pinned here is the *wiring*, since `db/sandbox.py` already proves the
ownership convention and `tests/ui/test_sandbox_controller.py` proves the
create-with-retry logic:

- the user supplies a **server** connection only -- there is no database field,
  and the app generates a `pgtp_sandbox_*` name itself;
- creating the project actually creates + provisions + installs, off the GUI
  thread, through the one `SandboxController`;
- the created name lands in `ProjectSettings.sandbox.database`, so a later
  Sandbox Setup…/`reset()` reopens the same database;
- a failure never blocks project creation, never records a sandbox the project
  does not have, and never gets swallowed;
- the session ends up live, which is what makes Apply to Sandbox reachable.

No server, no `CREATE DATABASE`, no thread: every seam is injected.
"""
import re
from dataclasses import replace

from PySide6.QtCore import QSettings

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import load_settings
from pgtp_editor.db.sandbox import (
    SANDBOX_DB_PREFIX,
    SandboxCapabilities,
    SandboxMode,
    is_app_owned,
)
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.new_project_dialog import NewProjectDialog
from pgtp_editor.ui.sandbox_controller import MAINTENANCE_DATABASE

from ._sandbox_stubs import fake_session, stub_sandbox_provisioning, sync_run

_NAME_RE = re.compile(r"^pgtp_sandbox_[a-z0-9_]{1,40}$")


def _refuse_uncreated_databases(window):
    """Narrow the shared `_opener` stub so it only opens a database that has a
    NAME, and record every attempt.

    BUG-040 auto-opens a session on project bind — and on the CREATE path that
    bind runs *before* provisioning has chosen a database name. The auto-open
    guard is what keeps a nameless dial from happening at all; this stub is the
    proof it holds, because a real server cannot hand back a sandbox session for
    a database that does not exist yet while the shared stub happily would,
    which would make "no sandbox was created, so there is no session" pass for
    the wrong reason. Returns the list of params the opener was asked for —
    `[]` is the expected shape on the create path.
    """
    asked = []

    def opener(params, **kwargs):
        asked.append(params)
        if not params.database:
            raise RuntimeError("no sandbox database to open")
        return fake_session(params)

    window.sandbox_controller._opener = opener
    return asked


def _window(qtbot, tmp_path):
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    window._run_async = sync_run
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        is_superuser=True,
        available_extensions=frozenset({"plpgsql_check"}),
        database="pgtp_sandbox_x",
        owner_marker="pgtp-editor-sandbox:1:2026-08-06T00:00:00+00:00",
        pg_dump_path="/usr/bin/pg_dump",
        pg_restore_path="/usr/bin/pg_restore",
    )
    return window


def _dialog(qtbot, window, tmp_path, *, name="ERP Overhaul", host="localhost"):
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText(name)
    dialog._folder_edit.setText(str(tmp_path / "proj"))
    if host:
        dialog._sandbox_host_edit.setText(host)
        dialog._sandbox_port_edit.setText("5432")
        dialog._sandbox_user_edit.setText("postgres")
        dialog._sandbox_password_edit.setText("pw")
    return dialog


# --- the dialog no longer asks for a database -------------------------------
def test_the_dialog_has_no_database_field_and_reports_an_empty_database(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._sandbox_host_edit.setText("localhost")

    assert not hasattr(dialog, "_sandbox_database_edit")
    assert dialog.sandbox_params().database == ""


def test_the_admin_connection_is_the_sandbox_creds_against_the_maintenance_db(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._sandbox_host_edit.setText("localhost")
    dialog._sandbox_user_edit.setText("postgres")
    dialog._sandbox_password_edit.setText("pw")

    admin = dialog.sandbox_admin_params()

    assert admin.database == MAINTENANCE_DATABASE
    assert (admin.host, admin.user, admin.password) == ("localhost", "postgres", "pw")


def test_the_test_button_probes_the_maintenance_database(qtbot):
    seen = []
    dialog = NewProjectDialog(
        prober=lambda params: seen.append(params) or SandboxCapabilities(is_superuser=True)
    )
    dialog._run_async = sync_run
    qtbot.addWidget(dialog)
    dialog._sandbox_host_edit.setText("localhost")

    dialog.test_sandbox()

    assert seen[0].database == MAINTENANCE_DATABASE


def test_the_generated_candidates_are_convention_satisfying_and_carry_the_stem(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("ERP Overhaul")

    names = dialog.sandbox_database_names()

    assert len(names) > 1 and len(set(names)) == len(names)
    assert all(_NAME_RE.match(name) for name in names)
    assert all(name.startswith(f"{SANDBOX_DB_PREFIX}erp_overhaul_") for name in names)


# --- creating the project creates the database ------------------------------
def test_creating_a_project_creates_and_records_an_auto_named_sandbox_database(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    created = stub_sandbox_provisioning(window)
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    assert len(created) == 1
    assert _NAME_RE.match(created[0])
    assert created[0].startswith(f"{SANDBOX_DB_PREFIX}erp_overhaul_")
    # recorded in the ONE store, both in memory and on disk
    assert window._ddl_project_settings.sandbox.database == created[0]
    assert load_settings(tmp_path / "proj").sandbox.database == created[0]
    # and the server connection the user typed survived alongside it
    assert window._ddl_project_settings.sandbox.host == "localhost"


def test_the_session_is_live_after_creation_so_apply_to_sandbox_is_reachable(
    qtbot, tmp_path
):
    """The session that matters is the PROVISIONED one, and BUG-040's auto-open
    stays out of its way: on `New Project` the sandbox database has not been
    named yet (`_provision_sandbox` chooses it, deliberately last), so the
    auto-open guard requires a database and dials NOTHING here. Without that
    guard every project creation spent a doomed connection and left the user an
    "not a PGTP-created database" line in the Audit panel, one step before the
    project provisioned correctly."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    asked = _refuse_uncreated_databases(window)
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    assert asked == []  # no dial at all before the database has a name
    assert window.sandbox_controller.has_session is True
    assert window.sandbox_controller.can_check is True
    # BUG-039: the two check gestures are `Parsing` members gated on a DDL
    # object tab being active, so their presence is asserted on one.
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")
    window.center_stage.setCurrentWidget(window.center_stage.ddl_object_tab(ref.key))
    assert window._sandbox_check_action.isVisible() is True
    assert window._sandbox_probe_check_action.isVisible() is True


def test_a_project_without_a_sandbox_connection_creates_nothing(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    created = stub_sandbox_provisioning(window)
    dialog = _dialog(qtbot, window, tmp_path, host="")

    window._ddl_project_ui.create_project(dialog)

    assert created == []
    assert window.sandbox_controller.has_session is False
    assert window._ddl_project_settings.sandbox.database == ""


def test_a_taken_name_is_skipped_and_the_created_one_is_what_gets_recorded(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    created = stub_sandbox_provisioning(window)
    attempts = []

    def creator(admin_params, name):
        attempts.append(name)
        if len(attempts) == 1:
            raise Exception(f'database "{name}" already exists')
        created.append(name)

    window.sandbox_controller._database_creator = creator
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    assert len(attempts) == 2 and attempts[0] != attempts[1]
    assert window._ddl_project_settings.sandbox.database == attempts[1]


def test_the_admin_connection_used_is_the_maintenance_database(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    seen = []
    window.sandbox_controller._database_creator = lambda admin, name: seen.append(admin)
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    assert seen[0].database == MAINTENANCE_DATABASE
    assert seen[0].user == "postgres"


# --- failure degrades, never blocks and never lies --------------------------
def test_a_failed_creation_still_creates_the_project_and_records_no_sandbox_db(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    _refuse_uncreated_databases(window)

    def creator(admin_params, name):
        raise RuntimeError("permission denied to create database")

    window.sandbox_controller._database_creator = creator
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    # the project exists and is open -- a sandbox failure is a tier-2 degrade
    assert window._ddl_project_folder == tmp_path / "proj"
    assert load_settings(tmp_path / "proj").name == "ERP Overhaul"
    # ...and it claims no sandbox database, because none was created
    assert window._ddl_project_settings.sandbox.database == ""
    assert load_settings(tmp_path / "proj").sandbox.database == ""
    assert window.sandbox_controller.has_session is False
    # the reason is surfaced, not swallowed
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("permission denied to create database" in line for line in lines)


def test_a_failed_provisioning_leaves_the_reported_tier_agreeing_with_reality(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    window.sandbox_controller._provisioner = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("could not build the baseline")
    )
    # A sandbox that cannot be reached/built must degrade the project, whatever
    # the recorded mode says (BUG-035's class of lie).
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        probe_error="database does not exist"
    )
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    status = window._ddl_project_ui.capability_status
    assert status is not None
    assert status.tier.value != "development"
    assert "database does not exist" in status.degraded_reason
    assert window._ddl_project_settings.sandbox.database == ""


def test_a_with_data_choice_is_recorded_verbatim(qtbot, tmp_path):
    """D2a: the mode is the user's one-time choice, recorded, never rewritten by
    what one provisioning run happened to manage."""
    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    dialog = _dialog(qtbot, window, tmp_path)
    dialog._sandbox_with_data_radio.setChecked(True)

    window._ddl_project_ui.create_project(dialog)

    assert load_settings(tmp_path / "proj").sandbox_mode is SandboxMode.WITH_DATA


def test_provisioning_never_opens_a_modal(qtbot, tmp_path, monkeypatch):
    """Creating a brand-new database destroys nothing, so the destructive
    confirmation is not asked -- and no `QMessageBox` is reachable either way."""
    from pgtp_editor.ui import modals

    def explode(*args, **kwargs):
        raise AssertionError("a modal was reached")

    monkeypatch.setattr(modals.QMessageBox, "question", explode)
    monkeypatch.setattr(modals.QMessageBox, "warning", explode)
    monkeypatch.setattr(modals.QMessageBox, "critical", explode)
    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    assert window.sandbox_controller.has_session is True


def test_the_target_profile_is_what_the_baseline_is_built_from(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    snapshots = []
    window.sandbox_controller._snapshotter = lambda params: snapshots.append(params)
    dialog = _dialog(qtbot, window, tmp_path)
    window._ddl_project_ui.create_project(dialog)
    # A brand-new project has no target yet: nothing is connected to, and the
    # sandbox is provisioned empty with that said out loud.
    assert snapshots == []

    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("created EMPTY" in line for line in lines)


def test_a_configured_target_is_snapshotted_for_the_baseline(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    snapshots = []
    window.sandbox_controller._snapshotter = lambda params: snapshots.append(params)
    dialog = _dialog(qtbot, window, tmp_path)
    window._ddl_project_ui.create_project(dialog)
    # Configure a target the way Project Settings does, then re-provision through
    # the same controller entry point the New Project step uses.
    target = ConnectionParams(host="db.example", database="prod", user="me")
    window.sandbox_controller.set_project(
        sandbox_params=window._ddl_project_settings.sandbox,
        target_params=target,
        mode=SandboxMode.SCHEMA_ONLY,
    )

    window.sandbox_controller.provision_new_database(
        admin_params=dialog.sandbox_admin_params(),
        name_candidates=dialog.sandbox_database_names(),
    )

    assert snapshots == [target]


# --- the dialog's server connection, in full ---------------------------------
def test_the_admin_connection_carries_every_typed_server_field(qtbot):
    """`sandbox_admin_params()` differs from `sandbox_params()` in the database
    and nothing else -- a dropped port or password would send `CREATE DATABASE`
    somewhere the user never named."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._sandbox_host_edit.setText("db.local")
    dialog._sandbox_port_edit.setText("5433")
    dialog._sandbox_user_edit.setText("root")
    dialog._sandbox_password_edit.setText("s3cret")

    admin = dialog.sandbox_admin_params()

    assert admin == ConnectionParams(
        host="db.local",
        port="5433",
        database=MAINTENANCE_DATABASE,
        user="root",
        password="s3cret",
    )
    assert dialog.sandbox_params() == replace(admin, database="")


def test_a_nameless_project_still_generates_legal_candidates(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    names = dialog.sandbox_database_names()

    assert all(_NAME_RE.match(name) for name in names)
    assert all(name.startswith(f"{SANDBOX_DB_PREFIX}project_") for name in names)


def test_the_step_explains_that_the_app_creates_the_database_itself(qtbot):
    """The removed field has to be replaced by an explanation, or the step reads
    as "we will use some database of yours"."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    caveat = dialog._sandbox_database_caveat.text()

    assert SANDBOX_DB_PREFIX in caveat
    assert "CREATES" in caveat
    assert "plpgsql_check" in caveat


# --- more failure shapes ----------------------------------------------------
def test_every_candidate_taken_records_no_sandbox_and_says_why(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    _refuse_uncreated_databases(window)
    attempts = []

    def creator(admin_params, name):
        attempts.append(name)
        raise Exception(f'database "{name}" already exists')

    window.sandbox_controller._database_creator = creator
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    assert len(attempts) > 1  # every generated candidate was tried
    assert window._ddl_project_settings.sandbox.database == ""
    assert load_settings(tmp_path / "proj").sandbox.database == ""
    assert window.sandbox_controller.has_session is False
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("already exists" in line for line in lines)
    assert any("no existing database was touched" in line for line in lines)


def test_a_refused_plpgsql_check_install_still_records_the_created_database(
    qtbot, tmp_path
):
    """Tier 2 is a working project (FQ-007 Q4): the sandbox was created, so its
    name must be recorded even though the extension is unavailable -- otherwise
    the next Sandbox Setup… would create a second orphan database."""
    window = _window(qtbot, tmp_path)
    created = stub_sandbox_provisioning(window)
    window.sandbox_controller._installer = lambda session: (_ for _ in ()).throw(
        RuntimeError("must be superuser to create extension")
    )
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    assert len(created) == 1
    assert load_settings(tmp_path / "proj").sandbox.database == created[0]
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("must be superuser to create extension" in line for line in lines)


def test_the_recorded_sandbox_database_is_an_app_owned_name(qtbot, tmp_path):
    """Half of the §18.5 D2 ownership test is the NAME, and `open_sandbox`
    refuses anything failing it -- so whatever lands in the project file has to
    satisfy it, or the sandbox this flow just built could never be reopened."""
    window = _window(qtbot, tmp_path)
    stub_sandbox_provisioning(window)
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    recorded = load_settings(tmp_path / "proj").sandbox.database
    assert is_app_owned(recorded, "pgtp-editor-sandbox:1:2026-08-06T00:00:00+00:00")


def test_creation_touches_no_database_other_than_the_one_it_creates(qtbot, tmp_path):
    """The strongest guarantee of the flow: an existing database is skipped, not
    reused and not dropped -- so the only database written to is the created one."""
    window = _window(qtbot, tmp_path)
    created = stub_sandbox_provisioning(window)
    provisioned = []
    window.sandbox_controller._provisioner = (
        lambda snapshot, params, mode, **kwargs: provisioned.append(params.database)
    )
    taken = {"first"}

    def creator(admin_params, name):
        if not taken:
            created.append(name)
            return
        taken.clear()
        raise Exception(f'database "{name}" already exists')

    window.sandbox_controller._database_creator = creator
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    assert provisioned == created  # exactly the created database, nothing else
    assert window._ddl_project_settings.sandbox.database == created[0]


def test_the_created_name_is_what_the_session_is_opened_on(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    created = stub_sandbox_provisioning(window)
    dialog = _dialog(qtbot, window, tmp_path)

    window._ddl_project_ui.create_project(dialog)

    assert window.sandbox_controller.sandbox_params.database == created[0]
    assert window.sandbox_controller.session.params.database == created[0]
