# tests/ui/test_sandbox_setup_dialog.py
"""Tests for SandboxSetupDialog (§18.5 D2/D2a) -- the provisioning surface.

The controller is stubbed WHOLE: no `SandboxSession` is ever constructed, no
connection is opened and no modal is reachable (the confirmation is an injected
callable, §30). The `db/sandbox.py` pure helpers (`determine_project_tier`,
`install_gate`) are the real ones, so the reason strings asserted here are the
ones the app ships rather than copies.
"""
from dataclasses import replace

from PySide6.QtCore import QObject, Signal

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import ProjectSettings
from pgtp_editor.db.sandbox import (
    OWNER_MARKER_PREFIX,
    AppliedObject,
    ForeignDatabaseError,
    SandboxCapabilities,
    SandboxMode,
    determine_project_tier,
)
from pgtp_editor.ui.sandbox_controller import (
    SandboxController,
    SandboxOperation,
    SandboxOperationResult,
)
from pgtp_editor.ui.sandbox_setup_dialog import (
    NO_PROJECT_REASON,
    SCHEMA_ONLY_CLONE_REASON,
    SandboxSetupDialog,
)

SUPERUSER_SENTENCE = (
    "CREATE EXTENSION requires superuser; ask your DBA, or connect the "
    "sandbox profile as a superuser."
)


def _sync_run(fn, on_result, on_error=None):
    """Synchronous stand-in for run_async, same seam style as the other UI tests."""
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


class FakeSession:
    """Just enough `SandboxSession` for the working-set list -- `applied()`."""

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.applied_calls = 0

    def applied(self):
        self.applied_calls += 1
        return list(self.rows)


class FakeController(QObject):
    """A whole stand-in for `SandboxController`: same read-only surface, same
    operation methods, recording calls instead of touching PostgreSQL."""

    session_changed = Signal(bool)
    operation_finished = Signal(object)

    def __init__(
        self,
        *,
        capabilities=None,
        sandbox_params=ConnectionParams(host="localhost", port="5432", database="pgtp_sandbox_erp", user="dev"),
        target_params=ConnectionParams(host="db01", port="5432", database="erp", user="dev"),
        mode=SandboxMode.SCHEMA_ONLY,
        session=None,
        configured=True,
    ):
        super().__init__()
        self._capabilities = capabilities
        self._sandbox_params = sandbox_params
        self._target_params = target_params
        self._mode = mode
        self._session = session
        self._configured = configured
        self.calls: list[tuple] = []

    # read-only state ------------------------------------------------------
    @property
    def capabilities(self):
        return self._capabilities

    @property
    def sandbox_params(self):
        return self._sandbox_params

    @property
    def target_params(self):
        return self._target_params

    @property
    def mode(self):
        return self._mode

    @property
    def has_session(self):
        return self._session is not None

    @property
    def session(self):
        return self._session

    def capability_status(self):
        caps = self._capabilities or SandboxCapabilities(
            probe_error="the sandbox has not been probed yet"
        )
        return determine_project_tier(caps, self._mode, self._configured)

    # operations -----------------------------------------------------------
    def set_project(self, **kwargs):
        self.calls.append(("set_project", kwargs))
        self._sandbox_params = kwargs.get("sandbox_params")
        self._target_params = kwargs.get("target_params")
        self._mode = kwargs.get("mode", self._mode)

    def refresh_capabilities(self, on_done=None):
        self.calls.append(("refresh_capabilities", {}))

    def open_session(self, on_done=None):
        self.calls.append(("open_session", {}))

    def provision(self, on_done=None, *, admin_params=None, database_name=None):
        self.calls.append(
            ("provision", {"admin_params": admin_params, "database_name": database_name})
        )

    def run_data_clone(self, on_done=None):
        self.calls.append(("run_data_clone", {}))

    def reset_session(self, on_done=None):
        self.calls.append(("reset_session", {}))

    def install_plpgsql_check(self, on_done=None):
        self.calls.append(("install_plpgsql_check", {}))

    def called(self, name):
        return [args for called, args in self.calls if called == name]


def _caps(**overrides) -> SandboxCapabilities:
    base = dict(
        server_version=(16, 2),
        is_superuser=True,
        installed_extensions=frozenset({"plpgsql_check"}),
        available_extensions=frozenset({"plpgsql_check"}),
        database="pgtp_sandbox_erp",
        owner_marker=f"{OWNER_MARKER_PREFIX}uuid:2026-08-06",
        pg_dump_path="/usr/bin/pg_dump",
        pg_restore_path="/usr/bin/pg_restore",
    )
    base.update(overrides)
    return SandboxCapabilities(**base)


def _settings(**overrides) -> ProjectSettings:
    base = dict(
        name="ERP overhaul",
        target=ConnectionParams(host="db01", port="5432", database="erp", user="dev"),
        sandbox=ConnectionParams(
            host="localhost", port="5432", database="pgtp_sandbox_erp", user="dev"
        ),
    )
    base.update(overrides)
    return ProjectSettings(**base)


def _dialog(qtbot, controller, *, settings=None, project_dir="/tmp/proj", confirm=None, saver=None):
    saved: list[tuple] = []
    dialog = SandboxSetupDialog(
        controller,
        settings=_settings() if settings is None else settings,
        project_dir=project_dir,
        confirm=confirm,
        settings_saver=saver if saver is not None else (lambda d, s: saved.append((d, s))),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog.refresh_state()
    return dialog, saved


# -- state rendering --------------------------------------------------------


def test_unprobed_sandbox_states_it_rather_than_claiming_absence(qtbot):
    dialog, _ = _dialog(qtbot, FakeController())
    text = dialog.state_text()
    assert "has not been probed yet" in text
    assert "plpgsql_check: unknown" in text


def test_unreachable_sandbox_shows_the_degraded_reason_verbatim(qtbot):
    controller = FakeController(capabilities=_caps(probe_error="connection refused"))
    dialog, _ = _dialog(qtbot, controller)
    assert "sandbox unreachable: connection refused" in dialog.state_text()


def test_no_sandbox_configured_shows_its_own_degraded_reason(qtbot):
    controller = FakeController(sandbox_params=None, configured=False)
    dialog, _ = _dialog(qtbot, controller)
    text = dialog.state_text()
    assert "no local sandbox configured for this project" in text
    assert "Sandbox connection: none configured." in text


def test_with_data_mode_missing_clone_tools_names_the_binaries(qtbot):
    controller = FakeController(
        mode=SandboxMode.WITH_DATA,
        capabilities=_caps(pg_dump_path=None, pg_restore_path=None),
    )
    dialog, _ = _dialog(qtbot, controller, settings=_settings(sandbox_mode=SandboxMode.WITH_DATA))
    assert "pg_dump and pg_restore not found on PATH" in dialog.state_text()


def test_foreign_database_shows_the_refusal_sentence_and_a_way_forward(qtbot):
    controller = FakeController(
        capabilities=_caps(database="myapp_dev", owner_marker=None),
        sandbox_params=ConnectionParams(
            host="localhost", port="5432", database="myapp_dev", user="dev"
        ),
    )
    dialog, _ = _dialog(qtbot, controller)
    assert str(ForeignDatabaseError("myapp_dev")) in dialog.state_text()
    # D2's mandatory mitigation is present alongside the refusal.
    assert dialog._create_button is not None


def test_app_owned_database_is_reported_as_ours(qtbot):
    dialog, _ = _dialog(qtbot, FakeController(capabilities=_caps()))
    assert "is a sandbox PGTP Editor created" in dialog.state_text()


def test_recorded_mode_is_shown(qtbot):
    dialog, _ = _dialog(
        qtbot,
        FakeController(mode=SandboxMode.WITH_DATA, capabilities=_caps()),
        settings=_settings(sandbox_mode=SandboxMode.WITH_DATA),
    )
    assert "with data" in dialog.state_text()


def test_baseline_incompleteness_is_stated_in_the_ui(qtbot):
    dialog, _ = _dialog(qtbot, FakeController(capabilities=_caps()))
    assert "are NOT reproduced" in dialog.state_text()


# -- provisioning: with data vs without data --------------------------------


def test_without_data_is_the_default_and_is_what_gets_recorded(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog, saved = _dialog(qtbot, controller)

    dialog._provision_button.click()

    assert dialog.chosen_mode() is SandboxMode.SCHEMA_ONLY
    assert saved[-1][1].sandbox_mode is SandboxMode.SCHEMA_ONLY
    assert controller.called("set_project")[-1]["mode"] is SandboxMode.SCHEMA_ONLY
    assert controller.called("provision") == [{"admin_params": None, "database_name": None}]


def test_with_data_choice_is_passed_through_and_recorded(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog, saved = _dialog(qtbot, controller)

    dialog._with_data_radio.setChecked(True)
    dialog._provision_button.click()

    assert saved[-1][1].sandbox_mode is SandboxMode.WITH_DATA
    assert controller.called("set_project")[-1]["mode"] is SandboxMode.WITH_DATA


def test_recorded_mode_seeds_the_radios(qtbot):
    dialog, _ = _dialog(
        qtbot,
        FakeController(mode=SandboxMode.WITH_DATA, capabilities=_caps()),
        settings=_settings(sandbox_mode=SandboxMode.WITH_DATA),
    )
    assert dialog._with_data_radio.isChecked()
    assert not dialog._without_data_radio.isChecked()


def test_create_sandbox_database_passes_admin_params_and_the_name(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog, saved = _dialog(qtbot, controller)

    dialog._database_name_edit.setText("pgtp_sandbox_erp2")
    dialog._create_button.click()

    call = controller.called("provision")[-1]
    assert call["database_name"] == "pgtp_sandbox_erp2"
    assert call["admin_params"].database == "postgres"
    assert call["admin_params"].host == "localhost"
    # The new database name is recorded in the ONE store, with the mode.
    assert saved[-1][1].sandbox.database == "pgtp_sandbox_erp2"
    assert controller.called("set_project")[-1]["sandbox_params"].database == (
        "pgtp_sandbox_erp2"
    )


def test_create_without_a_name_refuses_and_provisions_nothing(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog, saved = _dialog(qtbot, controller)

    dialog._database_name_edit.setText("   ")
    dialog._create_button.click()

    assert controller.called("provision") == []
    assert saved == []
    assert "before creating it" in dialog.result_text()


def test_provisioning_is_absent_without_an_open_project(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog = SandboxSetupDialog(controller, settings=None, project_dir=None)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    assert dialog._provision_button is None
    assert dialog._create_button is None
    assert dialog._with_data_radio is None
    assert NO_PROJECT_REASON in dialog.action_notes()


# -- the confirmation seam --------------------------------------------------


def test_provision_shows_the_controllers_own_warning_and_aborts_on_decline(qtbot):
    controller = FakeController(capabilities=_caps())
    seen: list[str] = []

    def decline(warning):
        seen.append(warning)
        return False

    dialog, saved = _dialog(qtbot, controller, confirm=decline)
    dialog._provision_button.click()

    assert seen == [SandboxController.destructive_warning(SandboxOperation.PROVISION)]
    assert controller.called("provision") == []
    assert saved == []  # nothing recorded either -- the gesture never started
    assert "Cancelled" in dialog.result_text()
    assert SandboxController.destructive_warning(SandboxOperation.PROVISION) in (
        dialog.result_text()
    )


def test_reset_consults_the_seam_and_aborts_on_decline(qtbot):
    controller = FakeController(capabilities=_caps(), session=FakeSession())
    seen: list[str] = []
    dialog, _ = _dialog(
        qtbot, controller, confirm=lambda w: (seen.append(w), False)[1]
    )

    dialog._reset_button.click()

    assert seen == [SandboxController.destructive_warning(SandboxOperation.RESET)]
    assert controller.called("reset_session") == []


def test_data_clone_consults_the_seam_and_aborts_on_decline(qtbot):
    controller = FakeController(
        capabilities=_caps(), session=FakeSession(), mode=SandboxMode.WITH_DATA
    )
    seen: list[str] = []
    dialog, _ = _dialog(
        qtbot,
        controller,
        settings=_settings(sandbox_mode=SandboxMode.WITH_DATA),
        confirm=lambda w: (seen.append(w), False)[1],
    )

    dialog._clone_button.click()

    assert seen == [SandboxController.destructive_warning(SandboxOperation.CLONE_DATA)]
    assert controller.called("run_data_clone") == []


def test_with_no_confirm_seam_the_gestures_reach_the_controller_unprompted(qtbot):
    """Mode 1 of the documented two-mode contract: `confirm=None` (the default)
    means the dialog pre-confirms NOTHING -- the controller's own
    `confirm_destructive` is the single prompt, so every destructive gesture must
    reach it rather than being swallowed here. The dialog cannot install itself as
    that gate (it is constructor-only and private), which is why this mode
    exists at all."""
    controller = FakeController(
        capabilities=_caps(), session=FakeSession(), mode=SandboxMode.WITH_DATA
    )
    dialog, _ = _dialog(
        qtbot,
        controller,
        settings=_settings(sandbox_mode=SandboxMode.WITH_DATA),
    )
    assert dialog._confirm is None

    dialog._reset_button.click()
    dialog._clone_button.click()
    dialog._provision_button.click()

    assert controller.called("reset_session") == [{}]
    assert controller.called("run_data_clone") == [{}]
    assert len(controller.called("provision")) == 1
    # Nothing was reported as cancelled: the dialog declined nothing.
    assert "ancelled" not in dialog.result_text()


def test_a_controller_declined_operation_surfaces_as_its_cancelled_result(qtbot):
    """The other half of mode 1, end to end against the REAL controller: with no
    gate of its own the controller refuses and reports; the dialog must render
    that sentence rather than looking like nothing happened. The wording is the
    controller's own -- nothing is retyped here."""
    controller = SandboxController(confirm_destructive=None)
    controller.set_project(
        sandbox_params=ConnectionParams(
            host="localhost", port="5432", database="pgtp_sandbox_erp", user="dev"
        ),
        target_params=ConnectionParams(host="db01", port="5432", database="erp", user="dev"),
    )
    dialog, _ = _dialog(qtbot, FakeController(capabilities=_caps()))

    controller.provision(dialog._on_operation)

    text = dialog.result_text()
    assert "not confirmed" in text
    assert SandboxController.destructive_warning(SandboxOperation.PROVISION) in text


def test_the_dialog_module_never_reaches_a_modal_qt_call():
    """The confirmation is an injected callable precisely so no test can reach a
    modal (CLAUDE.md's hard rule). A future edit adding a bare `QMessageBox` here
    would give the dialog a second, un-patchable confirmation surface."""
    import inspect

    source = inspect.getsource(
        __import__("pgtp_editor.ui.sandbox_setup_dialog", fromlist=["x"])
    )
    code = "\n".join(
        line.split("#", 1)[0] for line in source.splitlines()
    )
    for name in ("QMessageBox(", "QMessageBox.", "QFileDialog", "QInputDialog"):
        assert name not in code


def test_approved_destructive_gestures_reach_the_controller(qtbot):
    controller = FakeController(
        capabilities=_caps(), session=FakeSession(), mode=SandboxMode.WITH_DATA
    )
    dialog, _ = _dialog(
        qtbot,
        controller,
        settings=_settings(sandbox_mode=SandboxMode.WITH_DATA),
        confirm=lambda _w: True,
    )

    dialog._reset_button.click()
    dialog._clone_button.click()
    dialog._provision_button.click()

    assert controller.called("reset_session") == [{}]
    assert controller.called("run_data_clone") == [{}]
    assert len(controller.called("provision")) == 1


# -- results ----------------------------------------------------------------


def test_a_failing_operation_surfaces_its_stated_reason(qtbot):
    dialog, _ = _dialog(qtbot, FakeController(capabilities=_caps()))

    dialog._on_operation(
        SandboxOperationResult(
            operation=SandboxOperation.CLONE_DATA,
            ok=False,
            reason="pg_dump was not found on PATH (searched /usr/bin)",
        )
    )

    assert "clone data failed" in dialog.result_text()
    assert "pg_dump was not found on PATH (searched /usr/bin)" in dialog.result_text()


def test_a_successful_operation_still_reports_its_explanatory_reason(qtbot):
    dialog, _ = _dialog(qtbot, FakeController(capabilities=_caps()))

    dialog._on_operation(
        SandboxOperationResult(
            operation=SandboxOperation.INSTALL_PLPGSQL_CHECK,
            ok=True,
            reason="already installed.",
        )
    )

    assert "already installed." in dialog.result_text()


# -- the install gate -------------------------------------------------------


def test_non_superuser_shows_the_gates_own_sentence_and_no_install_button(qtbot):
    controller = FakeController(
        capabilities=_caps(installed_extensions=frozenset(), is_superuser=False),
        session=FakeSession(),
    )
    dialog, _ = _dialog(qtbot, controller)

    assert dialog._install_button is None
    assert SUPERUSER_SENTENCE in dialog.action_notes()
    assert SUPERUSER_SENTENCE in dialog.state_text()


def test_absent_extension_shows_the_platform_reason_and_no_button(qtbot):
    controller = FakeController(
        capabilities=_caps(
            installed_extensions=frozenset(), available_extensions=frozenset()
        ),
        session=FakeSession(),
    )
    dialog, _ = _dialog(qtbot, controller)

    assert dialog._install_button is None
    assert "installed as a C library on disk" in dialog.action_notes()


def test_installable_superuser_session_offers_one_click_install(qtbot):
    controller = FakeController(
        capabilities=_caps(installed_extensions=frozenset()), session=FakeSession()
    )
    dialog, _ = _dialog(qtbot, controller)

    assert dialog._install_button is not None
    dialog._install_button.click()
    assert controller.called("install_plpgsql_check") == [{}]


def test_already_installed_shows_the_gates_no_op_line_and_no_button(qtbot):
    controller = FakeController(capabilities=_caps(), session=FakeSession())
    dialog, _ = _dialog(qtbot, controller)

    assert dialog._install_button is None
    assert "already installed." in dialog.state_text()


# -- absent, not disabled ---------------------------------------------------


def test_session_only_controls_are_absent_without_a_session(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog, _ = _dialog(qtbot, controller)

    assert dialog._reset_button is None
    assert dialog._clone_button is None
    assert dialog._install_button is None
    assert dialog._open_button is not None
    assert "No sandbox session is open" in dialog.action_notes()


def test_clone_control_is_absent_for_a_schema_only_sandbox(qtbot):
    controller = FakeController(capabilities=_caps(), session=FakeSession())
    dialog, _ = _dialog(qtbot, controller)

    assert dialog._clone_button is None
    assert SCHEMA_ONLY_CLONE_REASON in dialog.action_notes()
    assert dialog._reset_button is not None


def test_open_session_button_drives_the_controller(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog, _ = _dialog(qtbot, controller)
    dialog._open_button.click()
    assert controller.called("open_session") == [{}]


def test_recheck_button_asks_for_a_fresh_probe(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog, _ = _dialog(qtbot, controller)
    dialog._refresh_button.click()
    assert controller.called("refresh_capabilities") == [{}]


# -- the working set --------------------------------------------------------


def test_working_set_renders_applied_rows(qtbot):
    session = FakeSession(
        [
            AppliedObject(
                kind="routine",
                schema_name="pr",
                object_name="recalc(integer)",
                table_name="",
                applied_at="2026-08-06T10:00:00+00:00",
                text_sha1="abc",
            ),
            AppliedObject(
                kind="trigger",
                schema_name="pr",
                object_name="trg_equipment",
                table_name="equipment",
                applied_at="2026-08-06T10:05:00+00:00",
                text_sha1="def",
            ),
        ]
    )
    controller = FakeController(capabilities=_caps(), session=session)
    dialog, _ = _dialog(qtbot, controller)

    table = dialog._working_set_table
    assert table is not None
    assert table.rowCount() == 2
    assert table.item(0, 0).text() == "routine"
    assert table.item(0, 1).text() == "pr"
    assert table.item(0, 2).text() == "recalc(integer)"
    assert table.item(1, 3).text() == "equipment"
    assert table.item(1, 4).text() == "2026-08-06T10:05:00+00:00"
    assert "2 objects applied" in dialog._working_set_label.text()


def test_empty_working_set_says_so_rather_than_looking_broken(qtbot):
    controller = FakeController(capabilities=_caps(), session=FakeSession([]))
    dialog, _ = _dialog(qtbot, controller)
    assert dialog._working_set_table is not None
    assert "nothing has been applied" in dialog._working_set_label.text()


def test_working_set_is_absent_without_a_session(qtbot):
    dialog, _ = _dialog(qtbot, FakeController(capabilities=_caps()))
    assert dialog._working_set_table is None
    assert "unavailable" in dialog._working_set_label.text()


def test_working_set_read_failure_is_reported_not_swallowed(qtbot):
    class Exploding(FakeSession):
        def applied(self):
            raise RuntimeError("relation pgtp_editor_sandbox.applied does not exist")

    controller = FakeController(capabilities=_caps(), session=Exploding())
    dialog, _ = _dialog(qtbot, controller)

    assert "relation pgtp_editor_sandbox.applied does not exist" in (
        dialog._working_set_label.text()
    )


def test_session_changed_signal_re_renders(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog, _ = _dialog(qtbot, controller)
    assert dialog._reset_button is None

    controller._session = FakeSession()
    controller.session_changed.emit(True)

    assert dialog._reset_button is not None


def test_settings_reflects_what_the_dialog_recorded(qtbot):
    controller = FakeController(capabilities=_caps())
    dialog, _ = _dialog(qtbot, controller)

    dialog._with_data_radio.setChecked(True)
    dialog._provision_button.click()

    assert dialog.settings() == replace(
        _settings(), sandbox_mode=SandboxMode.WITH_DATA
    )
