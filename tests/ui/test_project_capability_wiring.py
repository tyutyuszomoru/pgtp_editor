# tests/ui/test_project_capability_wiring.py
"""MainWindow wiring for the top-of-§18 tier/capability probe (settled
2026-08-05): the probe runs automatically whenever a project is opened or
created, and its result is stored for later consumption by the not-yet-built
Project Status screen.

No live DB, no real subprocess: `window._probe_sandbox_capabilities` is the
injectable seam (mirrors `_fetch_db_schema`) and `window._run_async` is
stubbed synchronous, exactly like the rest of this test suite.
"""
from PySide6.QtCore import QSettings

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.sandbox import ProjectTier, SandboxCapabilities, SandboxMode
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.new_project_dialog import NewProjectDialog


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _sync_run(fn, on_result, on_error=None):
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def _window(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    window._run_async = _sync_run
    return window


# --- No project open ----------------------------------------------------------
def test_no_capability_status_before_any_project_is_open(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._ddl_project_capability_status is None


# --- No sandbox configured -----------------------------------------------------
def test_creating_a_project_with_no_sandbox_probes_and_lands_in_quality_tier(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    called = []
    window._probe_sandbox_capabilities = lambda params: called.append(params) or SandboxCapabilities()

    window._create_ddl_project(dialog)

    assert called == []  # never probes the network when no sandbox is configured
    status = window._ddl_project_capability_status
    assert status is not None
    assert status.tier == ProjectTier.QUALITY
    assert "no local sandbox" in status.degraded_reason


# --- Sandbox configured, reachable, schema-only --------------------------------
def test_creating_a_project_with_a_reachable_schema_only_sandbox_lands_in_development_tier(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("localhost")
    window._probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)

    window._create_ddl_project(dialog)

    status = window._ddl_project_capability_status
    assert status.tier == ProjectTier.DEVELOPMENT
    assert status.degraded_reason is None


def test_probe_receives_the_projects_own_sandbox_params(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("sandbox-host")
    seen = []
    window._probe_sandbox_capabilities = lambda params: (
        seen.append(params), SandboxCapabilities(is_superuser=True)
    )[1]

    window._create_ddl_project(dialog)

    assert seen[0].host == "sandbox-host"


# --- Sandbox configured but unreachable ----------------------------------------
def test_unreachable_sandbox_degrades_to_quality_tier_with_the_probe_error_named(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("dead-host")
    window._probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        probe_error="could not connect to server"
    )

    window._create_ddl_project(dialog)

    status = window._ddl_project_capability_status
    assert status.tier == ProjectTier.QUALITY
    assert "could not connect to server" in status.degraded_reason


# --- "With data" mode, tools missing -------------------------------------------
def test_with_data_mode_missing_clone_tools_degrades_to_quality_naming_the_tools(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("localhost")
    dialog._sandbox_with_data_radio.setChecked(True)
    window._probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        is_superuser=True, pg_dump_path=None, pg_restore_path=None
    )

    window._create_ddl_project(dialog)

    status = window._ddl_project_capability_status
    assert status.tier == ProjectTier.QUALITY
    assert "pg_dump" in status.degraded_reason
    assert "pg_restore" in status.degraded_reason


def test_with_data_mode_and_tools_present_lands_in_development_tier(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("localhost")
    dialog._sandbox_with_data_radio.setChecked(True)
    window._probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        is_superuser=True, pg_dump_path="/usr/bin/pg_dump", pg_restore_path="/usr/bin/pg_restore"
    )

    window._create_ddl_project(dialog)

    assert window._ddl_project_capability_status.tier == ProjectTier.DEVELOPMENT


# --- sandbox_mode is persisted alongside the rest of the sandbox settings -----
def test_creating_a_project_records_the_chosen_sandbox_mode(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    project_dir = tmp_path / "p"
    dialog._folder_edit.setText(str(project_dir))
    dialog._sandbox_with_data_radio.setChecked(True)
    window._probe_sandbox_capabilities = lambda params: SandboxCapabilities()

    window._create_ddl_project(dialog)

    assert window._ddl_project_settings.sandbox_mode == SandboxMode.WITH_DATA
    from pgtp_editor.db.ddl_project import load_settings

    assert load_settings(project_dir).sandbox_mode == SandboxMode.WITH_DATA


# --- Opening an existing project re-probes (never cached from creation time) --
def test_opening_a_project_probes_again_reflecting_the_sandboxs_current_state(
    qtbot, tmp_path, monkeypatch
):
    project_dir = tmp_path / "existing"
    save_settings(
        project_dir,
        ProjectSettings(sandbox=ConnectionParams(host="localhost"), sandbox_mode=SandboxMode.SCHEMA_ONLY),
    )
    window = _window(qtbot, tmp_path)
    import pgtp_editor.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )
    window._probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)

    window._open_ddl_project()

    assert window._ddl_project_capability_status.tier == ProjectTier.DEVELOPMENT


def test_a_sandbox_that_died_between_sessions_is_detected_on_reopen(qtbot, tmp_path, monkeypatch):
    """The probe is never cached from creation time -- a sandbox that has
    died since must degrade the project back to tier 2 on the next open."""
    project_dir = tmp_path / "existing"
    save_settings(
        project_dir,
        ProjectSettings(sandbox=ConnectionParams(host="localhost"), sandbox_mode=SandboxMode.SCHEMA_ONLY),
    )
    window = _window(qtbot, tmp_path)
    import pgtp_editor.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )
    window._probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        probe_error="connection refused"
    )

    window._open_ddl_project()

    status = window._ddl_project_capability_status
    assert status.tier == ProjectTier.QUALITY
    assert "connection refused" in status.degraded_reason


# --- On-demand re-probe (future Project Status screen's entry point) ----------
def test_refresh_project_capability_status_can_be_called_on_demand(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("localhost")
    probe_calls = []
    window._probe_sandbox_capabilities = lambda params: (
        probe_calls.append(1), SandboxCapabilities(is_superuser=True)
    )[1]
    window._create_ddl_project(dialog)
    assert len(probe_calls) == 1

    window.refresh_project_capability_status()

    assert len(probe_calls) == 2  # re-probed, not served from a cache


def test_refresh_project_capability_status_with_no_project_open_clears_the_status(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_project_capability_status = None  # already the default; explicit for clarity

    window.refresh_project_capability_status()  # must not raise

    assert window._ddl_project_capability_status is None


# --- Closing a project clears the stored status --------------------------------
def test_closing_a_project_clears_the_capability_status(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("localhost")
    window._probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)
    window._create_ddl_project(dialog)
    assert window._ddl_project_capability_status is not None

    window._close_ddl_project()

    assert window._ddl_project_capability_status is None


# --- Probe seam never touches the network in tests without an explicit stub --
def test_default_probe_seam_is_the_real_sandbox_probe_function(qtbot, tmp_path):
    from pgtp_editor.db.sandbox import probe as real_probe

    window = _window(qtbot, tmp_path)
    assert window._probe_sandbox_capabilities is real_probe
