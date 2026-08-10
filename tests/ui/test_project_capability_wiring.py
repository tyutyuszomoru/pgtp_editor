# tests/ui/test_project_capability_wiring.py
"""MainWindow wiring for the top-of-§18 tier/capability probe (settled
2026-08-05): the probe runs automatically whenever a project is opened or
created, and its result is stored for later consumption by the not-yet-built
Project Status screen.

No live DB, no real subprocess: `window._ddl_project_ui.probe_sandbox_capabilities` is the
injectable seam (mirrors `_fetch_db_schema`) and `window._run_async` is
stubbed synchronous, exactly like the rest of this test suite.
"""
from PySide6.QtCore import QSettings

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.sandbox import ProjectTier, SandboxCapabilities, SandboxMode
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.new_project_dialog import NewProjectDialog
from pgtp_editor.ui import modals

from ._sandbox_stubs import stub_sandbox_provisioning


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
    # FQ-007: creating a project with a sandbox connection now creates and
    # provisions the sandbox database. Stubbed here so these tier/probe tests
    # stay about the probe, and so nothing reaches a real server.
    stub_sandbox_provisioning(window)
    return window


# --- No project open ----------------------------------------------------------
def test_no_capability_status_before_any_project_is_open(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._ddl_project_ui.capability_status is None


# --- No sandbox configured -----------------------------------------------------
def test_creating_a_project_with_no_sandbox_probes_and_lands_in_quality_tier(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    called = []
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: called.append(params) or SandboxCapabilities()

    window._ddl_project_ui.create_project(dialog)

    assert called == []  # never probes the network when no sandbox is configured
    status = window._ddl_project_ui.capability_status
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
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)

    window._ddl_project_ui.create_project(dialog)

    status = window._ddl_project_ui.capability_status
    assert status.tier == ProjectTier.DEVELOPMENT
    assert status.degraded_reason is None


def test_probe_receives_the_projects_own_sandbox_params(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("sandbox-host")
    seen = []
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: (
        seen.append(params), SandboxCapabilities(is_superuser=True)
    )[1]

    window._ddl_project_ui.create_project(dialog)

    assert seen[0].host == "sandbox-host"


# --- Sandbox configured but unreachable ----------------------------------------
def test_unreachable_sandbox_degrades_to_quality_tier_with_the_probe_error_named(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("dead-host")
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        probe_error="could not connect to server"
    )

    window._ddl_project_ui.create_project(dialog)

    status = window._ddl_project_ui.capability_status
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
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        is_superuser=True, pg_dump_path=None, pg_restore_path=None
    )

    window._ddl_project_ui.create_project(dialog)

    status = window._ddl_project_ui.capability_status
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
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        is_superuser=True, pg_dump_path="/usr/bin/pg_dump", pg_restore_path="/usr/bin/pg_restore"
    )

    window._ddl_project_ui.create_project(dialog)

    assert window._ddl_project_ui.capability_status.tier == ProjectTier.DEVELOPMENT


# --- sandbox_mode is persisted alongside the rest of the sandbox settings -----
def test_creating_a_project_records_the_chosen_sandbox_mode(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    project_dir = tmp_path / "p"
    dialog._folder_edit.setText(str(project_dir))
    dialog._sandbox_with_data_radio.setChecked(True)
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities()

    window._ddl_project_ui.create_project(dialog)

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
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)

    window._ddl_project_ui.open_project()

    assert window._ddl_project_ui.capability_status.tier == ProjectTier.DEVELOPMENT


def test_a_sandbox_that_died_between_sessions_is_detected_on_reopen(qtbot, tmp_path, monkeypatch):
    """The probe is never cached from creation time -- a sandbox that has
    died since must degrade the project back to tier 2 on the next open."""
    project_dir = tmp_path / "existing"
    save_settings(
        project_dir,
        ProjectSettings(sandbox=ConnectionParams(host="localhost"), sandbox_mode=SandboxMode.SCHEMA_ONLY),
    )
    window = _window(qtbot, tmp_path)
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        probe_error="connection refused"
    )

    window._ddl_project_ui.open_project()

    status = window._ddl_project_ui.capability_status
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
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: (
        probe_calls.append(1), SandboxCapabilities(is_superuser=True)
    )[1]
    window._ddl_project_ui.create_project(dialog)
    # FQ-007: creation probes more than once now (the tier probe, the sandbox
    # controller's own probe while provisioning, then the post-provisioning
    # re-probe). What this test pins is that a later call re-probes.
    after_create = len(probe_calls)
    assert after_create >= 1

    window._ddl_project_ui.refresh_capability_status()

    assert len(probe_calls) == after_create + 1  # re-probed, not served from a cache


def test_refresh_project_capability_status_with_no_project_open_clears_the_status(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_project_ui.capability_status = None  # already the default; explicit for clarity

    window._ddl_project_ui.refresh_capability_status()  # must not raise

    assert window._ddl_project_ui.capability_status is None


# --- Closing a project clears the stored status --------------------------------
def test_closing_a_project_clears_the_capability_status(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog._sandbox_host_edit.setText("localhost")
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)
    window._ddl_project_ui.create_project(dialog)
    assert window._ddl_project_ui.capability_status is not None

    window._ddl_project_ui.close_project()

    assert window._ddl_project_ui.capability_status is None


# --- Probe seam never touches the network in tests without an explicit stub --
def test_default_probe_seam_is_the_real_sandbox_probe_function(qtbot, tmp_path):
    from pgtp_editor.db.sandbox import probe as real_probe

    window = _window(qtbot, tmp_path)
    assert window._ddl_project_ui.probe_sandbox_capabilities is real_probe


# --- BUG-030: the Quality node reflects real target reachability -------------
def _project_with_target(qtbot, tmp_path, target_host="target-host"):
    """A window with an open project whose target profile is `target_host`.

    Goes through `_set_active_ddl_project` (the real trigger point) rather than
    poking the attributes, so the target probe is exercised where it ships.
    """
    window = _window(qtbot, tmp_path)
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)
    project_dir = tmp_path / "p"
    settings = ProjectSettings(
        target=ConnectionParams(host=target_host, database="db", user="u"),
        sandbox=ConnectionParams(host="localhost"),
        sandbox_mode=SandboxMode.SCHEMA_ONLY,
    )
    save_settings(project_dir, settings)
    return window, project_dir, settings


def _quality_state(window):
    from pgtp_editor.ui.project_status_model import NodeFamily

    diagram = window._build_project_status_diagram()
    return diagram.node(NodeFamily.QUALITY).state


def test_an_unreachable_target_renders_the_quality_node_offline(qtbot, tmp_path, monkeypatch):
    """The regression: green used to mean "a target profile exists", so an
    offline target the DDL Explorer refused to reach still showed as
    Connected."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import QualityState

    window, project_dir, settings = _project_with_target(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection",
        lambda params: (False, "could not connect to server"),
    )

    window._ddl_project_ui.set_active_project(project_dir, settings)

    assert window._ddl_project_ui.target_probe_error == "could not connect to server"
    assert _quality_state(window) == QualityState.OFFLINE.value


def test_a_reachable_target_renders_the_quality_node_connected(qtbot, tmp_path, monkeypatch):
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import QualityState

    window, project_dir, settings = _project_with_target(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )

    window._ddl_project_ui.set_active_project(project_dir, settings)

    assert window._ddl_project_ui.target_probe_error is None
    assert _quality_state(window) == QualityState.CONNECTION_OK.value


def test_the_target_probe_tests_the_same_params_the_summary_line_shows(qtbot, tmp_path, monkeypatch):
    """BUG-024's selection must be single-sourced: probing a different profile
    than the summary/Explorer use is how false greens come back."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module

    window, project_dir, settings = _project_with_target(qtbot, tmp_path)
    seen = []
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection",
        lambda params: (seen.append(params), (True, "Connected."))[1],
    )

    window._ddl_project_ui.set_active_project(project_dir, settings)

    assert seen == [settings.target]
    assert seen[0] is window._project_status_target()


def test_no_target_configured_is_still_not_set_up_and_never_probed(qtbot, tmp_path, monkeypatch):
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import QualityState

    window = _window(qtbot, tmp_path)
    calls = []
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection",
        lambda params: (calls.append(params), (True, "Connected."))[1],
    )

    window._ddl_project_ui.refresh_capability_status()  # no project, no saved connection

    assert calls == []  # nothing to reach: never opens a connection
    assert _quality_state(window) == QualityState.NOT_SET_UP.value


def test_a_host_less_target_profile_is_never_probed_and_clears_a_stale_error(
    qtbot, tmp_path, monkeypatch
):
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module

    window, project_dir, settings = _project_with_target(qtbot, tmp_path, target_host="")
    calls = []
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection",
        lambda params: (calls.append(params), (False, "boom"))[1],
    )
    window._ddl_project_ui.target_probe_error = "stale error from a previous profile"

    window._ddl_project_ui.set_active_project(project_dir, settings)

    assert calls == []
    assert window._ddl_project_ui.target_probe_error is None


def test_the_probe_result_pushes_a_corrected_diagram_into_the_open_window(
    qtbot, tmp_path, monkeypatch
):
    """Gotcha (1): the first paint uses the last-known state and the async
    result corrects it -- so a healthy target never flashes red, and a target
    that died is corrected to red without the user reopening the window."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import NodeFamily, QualityState

    window, project_dir, settings = _project_with_target(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)
    window._open_project_status()
    panel = window._project_status_window
    assert panel is not None
    pushed = []
    panel.set_diagram = lambda diagram: pushed.append(diagram)

    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (False, "connection refused")
    )
    window._ddl_project_ui.refresh_capability_status()

    assert pushed, "the landing probe result must re-render the open window"
    assert pushed[-1].node(NodeFamily.QUALITY).state == QualityState.OFFLINE.value


def test_projectless_mode_probes_the_app_level_saved_connection(qtbot, tmp_path, monkeypatch):
    """BUG-024's selection has two branches and both must be probed: with no
    project open the target is the app-level saved connection, and the Quality
    node must go red for it too (the window is reachable projectless)."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.db.config import save_connection
    from pgtp_editor.ui.project_status_model import QualityState

    settings = _empty_settings(tmp_path)
    saved = ConnectionParams(host="app-level-host", database="db", user="u")
    save_connection(settings, saved)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._run_async = _sync_run
    seen = []
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection",
        lambda params: (seen.append(params), (False, "could not connect to server"))[1],
    )

    window._ddl_project_ui.refresh_capability_status()

    assert seen == [saved]
    assert _quality_state(window) == QualityState.OFFLINE.value


def test_the_windows_recheck_seam_reprobes_the_target(qtbot, tmp_path, monkeypatch):
    """§18.8's Re-check button / on-open re-probe goes through the panel's own
    `refresh()` seam, so the target probe must hang off that path too -- not
    only off a direct `refresh_project_capability_status()` call."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import NodeFamily, QualityState

    window, project_dir, settings = _project_with_target(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)
    window._open_project_status()
    panel = window._project_status_window
    assert panel.node_widget(NodeFamily.QUALITY) is not None

    # The target dies while the window is open; the user hits Re-check.
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (False, "connection refused")
    )
    panel.refresh()

    assert window._ddl_project_ui.target_probe_error == "connection refused"
    assert _quality_state(window) == QualityState.OFFLINE.value


def test_closing_a_project_clears_the_target_probe_error(qtbot, tmp_path, monkeypatch):
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module

    window, project_dir, settings = _project_with_target(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (False, "connection refused")
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)
    assert window._ddl_project_ui.target_probe_error == "connection refused"

    window._ddl_project_ui.close_project()

    assert window._ddl_project_ui.target_probe_error is None


# --- BUG-030 facet (a): "quality no setup" must be REACHABLE ------------------
def test_a_projects_blank_target_renders_not_set_up_not_green(qtbot, tmp_path, monkeypatch):
    """`ProjectSettings.target` is `field(default_factory=ConnectionParams)`, so
    it is never None -- `configured=target is not None` was constantly True and
    a brand-new project's unfilled target rendered green "Connected"."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import QualityState

    window = _window(qtbot, tmp_path)
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)
    project_dir = tmp_path / "blank"
    settings = ProjectSettings(sandbox=ConnectionParams(host="localhost"))
    save_settings(project_dir, settings)
    calls = []
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection",
        lambda params: (calls.append(params), (True, "Connected."))[1],
    )

    window._ddl_project_ui.set_active_project(project_dir, settings)

    # Guard the premise: the dataclass really is there, it is just empty.
    assert window._ddl_project_settings.target is not None
    assert window._project_status_target() is not None
    assert calls == []  # nothing to reach, so nothing was tried
    assert _quality_state(window) == QualityState.NOT_SET_UP.value


def test_a_blank_target_stays_not_set_up_across_a_recheck(qtbot, tmp_path, monkeypatch):
    """Facet (b)'s residue: the unconfigured target skipped the probe, leaving
    `probe_error=None`, which used to fall through to green on every Re-check."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import QualityState

    window = _window(qtbot, tmp_path)
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)
    project_dir = tmp_path / "blank"
    settings = ProjectSettings(sandbox=ConnectionParams(host="localhost"))
    save_settings(project_dir, settings)
    calls = []
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection",
        lambda params: (calls.append(params), (True, "Connected."))[1],
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)

    window._ddl_project_ui.refresh_capability_status()

    assert calls == []
    assert _quality_state(window) == QualityState.NOT_SET_UP.value


def test_the_quality_click_through_shows_no_details_for_a_nonexistent_connection(
    qtbot, tmp_path, monkeypatch
):
    """Facet (a)'s phantom details: `_connection_summary_for` only said "Not
    configured." for `None`, so an all-empty `ConnectionParams` printed a
    degenerate `@:/`-shaped summary beside a green status line."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import NodeFamily

    window = _window(qtbot, tmp_path)
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)
    project_dir = tmp_path / "blank"
    settings = ProjectSettings(sandbox=ConnectionParams(host="localhost"))
    save_settings(project_dir, settings)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)

    assert window._connection_summary_for(ConnectionParams()) == "Not configured."
    window._open_project_status()
    panel = window._project_status_window
    panel.node_widget(NodeFamily.QUALITY).click()
    body = panel.last_window.body_text

    assert "Not configured" in body
    assert "Connected" not in body
    assert "@" not in body  # no user@host:port/db line for a connection that isn't


def test_a_real_target_still_shows_its_details(qtbot, tmp_path, monkeypatch):
    """The fix must not silence details for a connection that DOES exist."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import NodeFamily

    window, project_dir, settings = _project_with_target(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)

    window._open_project_status()
    panel = window._project_status_window
    panel.node_widget(NodeFamily.QUALITY).click()
    body = panel.last_window.body_text

    assert "target-host" in body


# --- BUG-035: Sandbox1 reports verified facts, never the configured mode ------
def _project_with_sandbox(qtbot, tmp_path, mode=SandboxMode.SCHEMA_ONLY):
    window = _window(qtbot, tmp_path)
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(is_superuser=True)
    project_dir = tmp_path / "p"
    settings = ProjectSettings(
        target=ConnectionParams(host="target-host", database="db", user="u"),
        sandbox=ConnectionParams(host="sandbox-host", database="pgtp_sandbox_x"),
        sandbox_mode=mode,
    )
    save_settings(project_dir, settings)
    return window, project_dir, settings


def _sandbox1_state(window):
    from pgtp_editor.ui.project_status_model import NodeFamily

    node = window._build_project_status_diagram().node(NodeFamily.SANDBOX1)
    return None if node is None else node.state


def test_schema_only_mode_alone_never_produces_the_schema_only_state(
    qtbot, tmp_path, monkeypatch
):
    """The reported bug verbatim: "sandbox says schema only, but there's no
    schema, just a connection". A SCHEMA_ONLY project whose sandbox is merely
    reachable must NOT claim a schema."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import SandboxFact

    window, project_dir, settings = _project_with_sandbox(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._inspect_sandbox_provisioning = lambda params: (
        SandboxFact.ABSENT, SandboxFact.ABSENT
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)
    window._open_project_status()

    assert _sandbox1_state(window) == "sandbox1_not_provisioned"


def test_with_data_mode_alone_never_produces_the_filled_state(qtbot, tmp_path, monkeypatch):
    """The sibling instance from the gap register: `data_clone_done` used to be
    `sandbox_mode is WITH_DATA`, i.e. the radio button reading itself back."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import SandboxFact

    window, project_dir, settings = _project_with_sandbox(
        qtbot, tmp_path, mode=SandboxMode.WITH_DATA
    )
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._inspect_sandbox_provisioning = lambda params: (
        SandboxFact.PRESENT, SandboxFact.ABSENT
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)
    window._open_project_status()

    assert _sandbox1_state(window) == "sandbox1_empty"


def test_verified_data_is_what_produces_the_filled_state(qtbot, tmp_path, monkeypatch):
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import SandboxFact

    window, project_dir, settings = _project_with_sandbox(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._inspect_sandbox_provisioning = lambda params: (
        SandboxFact.PRESENT, SandboxFact.PRESENT
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)
    window._open_project_status()

    # SCHEMA_ONLY mode, yet data was really found: the fact wins over the mode.
    assert _sandbox1_state(window) == "sandbox1_filled"


def test_an_uninspectable_sandbox_reports_unknown_never_a_default(
    qtbot, tmp_path, monkeypatch
):
    """"Could not check" must not become "genuinely not there" -- and must not
    become a cheerful "Schema only" either."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import SandboxFact

    window, project_dir, settings = _project_with_sandbox(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._inspect_sandbox_provisioning = lambda params: (
        SandboxFact.UNKNOWN, SandboxFact.UNKNOWN
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)
    window._open_project_status()

    assert _sandbox1_state(window) == "sandbox1_unknown"


def test_sandbox1_is_unknown_before_anything_has_been_inspected(qtbot, tmp_path, monkeypatch):
    """The diagram is built once before the async inspection lands; that first
    paint must claim nothing rather than default to a state."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module

    window, project_dir, settings = _project_with_sandbox(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)

    # `_set_active_ddl_project` probes capabilities but not contents.
    assert window._ddl_sandbox_content_facts is None
    assert _sandbox1_state(window) == "sandbox1_unknown"


def test_the_inspection_receives_the_projects_own_sandbox_params(qtbot, tmp_path, monkeypatch):
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import SandboxFact

    window, project_dir, settings = _project_with_sandbox(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    seen = []
    window._inspect_sandbox_provisioning = lambda params: (
        seen.append(params), (SandboxFact.PRESENT, SandboxFact.ABSENT)
    )[1]
    window._ddl_project_ui.set_active_project(project_dir, settings)
    window._open_project_status()

    assert seen and seen[0] == settings.sandbox


def test_facts_measured_against_another_sandbox_are_never_reused(qtbot, tmp_path, monkeypatch):
    """Stored facts carry the connection they were measured against, so a
    project switch cannot leave the previous sandbox's answer on screen."""
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import SandboxFact

    window, project_dir, settings = _project_with_sandbox(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)
    window._ddl_sandbox_content_facts = (
        ConnectionParams(host="some-other-sandbox"),
        SandboxFact.PRESENT,
        SandboxFact.PRESENT,
    )

    assert _sandbox1_state(window) == "sandbox1_unknown"


def test_no_sandbox_host_means_nothing_is_inspected(qtbot, tmp_path, monkeypatch):
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module
    from pgtp_editor.ui.project_status_model import SandboxFact

    window, project_dir, settings = _project_with_sandbox(qtbot, tmp_path)
    settings = ProjectSettings(target=settings.target)  # no sandbox at all
    save_settings(project_dir, settings)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )
    calls = []
    window._inspect_sandbox_provisioning = lambda params: (
        calls.append(params), (SandboxFact.PRESENT, SandboxFact.PRESENT)
    )[1]
    window._ddl_project_ui.set_active_project(project_dir, settings)

    window._refresh_sandbox_provisioning_status()

    assert calls == []
    assert window._ddl_sandbox_content_facts is None
    # Absence rule: no sandbox configured means no Sandbox1 node at all.
    assert _sandbox1_state(window) is None


def test_a_broken_inspection_seam_is_surfaced_and_leaves_the_facts_unknown(
    qtbot, tmp_path, monkeypatch
):
    import pgtp_editor.ui.ddl_project_controller as ddl_project_module

    window, project_dir, settings = _project_with_sandbox(qtbot, tmp_path)
    monkeypatch.setattr(
        ddl_project_module, "db_test_connection", lambda params: (True, "Connected.")
    )

    def boom(params):
        raise RuntimeError("seam is broken")

    window._inspect_sandbox_provisioning = boom
    window._ddl_project_ui.set_active_project(project_dir, settings)

    window._refresh_sandbox_provisioning_status()

    assert window._ddl_sandbox_content_facts is None
    assert _sandbox1_state(window) == "sandbox1_unknown"
    messages = window.activity_panel.row_texts()
    assert any("Sandbox content inspection failed" in m for m in messages)


def test_the_inspection_never_raises_and_degrades_to_unknown(qtbot, tmp_path, monkeypatch):
    """The real seam's never-raises contract, exercised with a runner that
    fails both the two-query call and the schema-only retry."""
    import pgtp_editor.db.introspect as introspect
    from pgtp_editor.ui.project_status_model import SandboxFact

    window = _window(qtbot, tmp_path)

    def dead(params, sql_list, connect_timeout=10):
        raise RuntimeError("could not connect to server")

    monkeypatch.setattr(introspect, "run_queries", dead)

    assert window._inspect_sandbox_provisioning(ConnectionParams(host="h")) == (
        SandboxFact.UNKNOWN,
        SandboxFact.UNKNOWN,
    )


def test_a_server_without_xml_support_still_answers_the_schema_question(
    qtbot, tmp_path, monkeypatch
):
    """The data query needs `query_to_xml`; when it is unavailable the schema
    fact -- the one this bug was about -- must survive, with data UNKNOWN."""
    import pgtp_editor.db.introspect as introspect
    from pgtp_editor.ui.project_status_model import SandboxFact

    window = _window(qtbot, tmp_path)
    seen = []

    def runner(params, sql_list, connect_timeout=10):
        seen.append(len(sql_list))
        if len(sql_list) == 2:
            raise RuntimeError('function query_to_xml does not exist')
        return [[(3,)]]

    monkeypatch.setattr(introspect, "run_queries", runner)

    assert window._inspect_sandbox_provisioning(ConnectionParams(host="h")) == (
        SandboxFact.PRESENT,
        SandboxFact.UNKNOWN,
    )
    assert seen == [2, 1]


def test_the_inspection_reads_both_facts_from_one_round_trip(qtbot, tmp_path, monkeypatch):
    import pgtp_editor.db.introspect as introspect
    from pgtp_editor.db.sandbox import BOOKKEEPING_SCHEMA
    from pgtp_editor.ui.project_status_model import SandboxFact

    window = _window(qtbot, tmp_path)
    captured = []

    def runner(params, sql_list, connect_timeout=10):
        captured.extend(sql_list)
        return [[(7,)], [(0,)]]

    monkeypatch.setattr(introspect, "run_queries", runner)

    assert window._inspect_sandbox_provisioning(ConnectionParams(host="h")) == (
        SandboxFact.PRESENT,
        SandboxFact.ABSENT,
    )
    assert len(captured) == 2
    for sql in captured:
        # The reserved bookkeeping schema always exists in an owned sandbox, so
        # counting it would make every unprovisioned sandbox look provisioned.
        assert f"'{BOOKKEEPING_SCHEMA}'" in sql
        # Extension-owned objects must not pass for provisioning.
        assert "deptype = 'e'" in sql
