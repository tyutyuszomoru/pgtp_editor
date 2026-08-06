# tests/ui/test_sandbox_setup_wiring.py
"""The three sandbox gestures that existed as machinery but not as clicks:

* **Database ▸ Sandbox Setup…** -- `ui/sandbox_setup_dialog.py` shipped complete
  with no menu entry anywhere, so re-provisioning had no entry point at all and
  several user-facing strings already told the user to open a menu item that did
  not exist. Wired non-modally, with `confirm=None` so the CONTROLLER owns the
  single destructive prompt (passing both asks twice).
* **The Project Status window's two dead node actions** -- Sandbox1's "run data
  clone" and Sandbox2's "install plpgsql_check", now aimed at the controller's
  zero-argument §18.8 adapters, and only while a live session exists.

No modal is ever reached: `QMessageBox.question` is patched wherever a
destructive operation can be confirmed, the setup dialog's persistence is an
injected `settings_saver`, and every `db/sandbox.py` seam on the controller is
stubbed, so nothing here opens a connection or issues `CREATE DATABASE`.
"""
from PySide6.QtCore import QSettings

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.sandbox import SandboxCapabilities, SandboxMode
from pgtp_editor.ui import modals
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.project_status_model import NodeFamily
from pgtp_editor.ui.sandbox_setup_dialog import SandboxSetupDialog

from tests.ui._sandbox_stubs import stub_sandbox_provisioning, sync_run


def _caps(**overrides):
    """A probe result good enough to open a session: superuser, app-owned
    database, and (for the WITH_DATA tests) the clone tools present."""
    fields = dict(
        is_superuser=True,
        database="pgtp_sandbox_x",
        pg_dump_path="/usr/bin/pg_dump",
        pg_restore_path="/usr/bin/pg_restore",
    )
    fields.update(overrides)
    return SandboxCapabilities(**fields)


def _window(qtbot, tmp_path, *, sandbox_host="localhost", mode=SandboxMode.SCHEMA_ONLY):
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        name="Acme",
        target=ConnectionParams(host="targethost", database="prod"),
        sandbox=ConnectionParams(host=sandbox_host, database="pgtp_sandbox_x"),
        sandbox_mode=mode,
    )
    save_settings(project_dir, settings)
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    window._run_async = sync_run
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: _caps()
    window._inspect_sandbox_provisioning = lambda params: (None, None)
    stub_sandbox_provisioning(window)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    return window, project_dir


def _open_setup(window, qtbot):
    """Open the dialog through the real menu handler, then make its ONE own
    off-thread call (`SandboxSession.applied()`) synchronous so no worker thread
    outlives the test."""
    dialog = window._open_sandbox_setup()
    qtbot.addWidget(dialog)
    dialog._run_async = sync_run
    dialog._settings_saver = lambda *a, **k: None
    return dialog


def _accept_confirmations(monkeypatch):
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.Yes),
    )


def _refuse_confirmations(monkeypatch):
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.No),
    )


def _audit_texts(window):
    panel = window.audit_panel
    return [panel.item(i).text() for i in range(panel.count())]


# --- Database ▸ Sandbox Setup… --------------------------------------------


def _setup_action(window):
    for action in window.menuBar().actions():
        menu = action.menu()
        if menu is None or action.text() != "Database":
            continue
        for entry in menu.actions():
            if entry.text() == "Sandbox Setup…":
                return entry
    return None


def test_the_database_menu_carries_a_sandbox_setup_entry(qtbot, tmp_path):
    window, _dir = _window(qtbot, tmp_path)

    action = _setup_action(window)

    assert action is not None
    assert action is window._sandbox_setup_action
    # NOT session-gated: this is the one gesture that can create a sandbox, so
    # it must be reachable exactly when there is no sandbox yet.
    assert action.isVisible()
    assert action.isEnabled()


def test_the_entry_opens_the_dialog_non_modally_bound_to_the_project(qtbot, tmp_path):
    window, project_dir = _window(qtbot, tmp_path)

    dialog = _open_setup(window, qtbot)

    assert isinstance(dialog, SandboxSetupDialog)
    assert dialog is window._sandbox_setup_dialog
    assert not dialog.isModal()
    assert dialog._controller is window.sandbox_controller
    assert dialog._settings == window._ddl_project_settings
    assert dialog._project_dir == project_dir
    dialog.close()


def test_the_dialog_leaves_confirmation_to_the_controller_so_it_asks_once(
    qtbot, tmp_path, monkeypatch
):
    """The two-mode contract: `confirm=None` means the dialog pre-confirms
    nothing and the controller's gate is the SINGLE prompt."""
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_setup(window, qtbot)
    assert dialog._confirm is None

    asked = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(
            lambda _p, _t, text, *a, **k: asked.append(text)
            or modals.QMessageBox.StandardButton.Yes
        ),
    )
    dialog.provision()

    # Exactly one prompt, carrying the controller's own warning text.
    assert len(asked) == 1
    from pgtp_editor.ui.sandbox_controller import SandboxController, SandboxOperation

    assert asked[0] == SandboxController.destructive_warning(
        SandboxOperation.PROVISION
    )
    dialog.close()


def test_declining_the_controllers_prompt_surfaces_as_cancelled_in_the_dialog(
    qtbot, tmp_path, monkeypatch
):
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_setup(window, qtbot)
    _refuse_confirmations(monkeypatch)

    dialog.provision()

    assert "cancelled" in dialog.result_text().casefold()
    assert not window.sandbox_controller.has_session
    dialog.close()


def test_the_host_adopts_the_settings_the_dialog_recorded(
    qtbot, tmp_path, monkeypatch
):
    """A provisioning gesture may record a new mode / database name; the host
    takes the dialog's OWN `ProjectSettings` rather than re-reading the file."""
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_setup(window, qtbot)
    _accept_confirmations(monkeypatch)
    # Choose "with data", then provision: the dialog records the mode.
    dialog._with_data_radio.setChecked(True)

    dialog.provision()

    assert dialog.settings().sandbox_mode is SandboxMode.WITH_DATA
    assert window._ddl_project_settings.sandbox_mode is SandboxMode.WITH_DATA
    dialog.close()


def test_adopting_the_settings_does_not_drop_the_session_just_provisioned(
    qtbot, tmp_path, monkeypatch
):
    """Adoption must NOT rebind the controller: `set_project` closes the session,
    and the session it would close is the one the dialog just created."""
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_setup(window, qtbot)
    _accept_confirmations(monkeypatch)

    dialog.provision()

    assert window.sandbox_controller.has_session
    dialog.close()
    assert window.sandbox_controller.has_session


def test_the_console_refusal_names_gestures_that_exist(qtbot, tmp_path):
    """The stale string said "Database ▸ Project Status…", which never opened a
    session. Both names it uses now are real Database-menu entries."""
    window, _dir = _window(qtbot, tmp_path)

    assert window._open_sandbox_sql_console() is None

    message = window.statusBar().currentMessage()
    assert "Open Sandbox Session" in message
    assert "Sandbox Setup…" in message
    assert "Project Status" not in message


def test_the_consoles_no_session_text_names_the_entry_that_now_exists():
    from pgtp_editor.ui.sql_console_panel import NO_SESSION_TEXT

    assert "Sandbox Setup…" in NO_SESSION_TEXT


# --- The Project Status window's two node actions -------------------------


def test_the_node_actions_are_absent_without_a_session(qtbot, tmp_path):
    window, _dir = _window(qtbot, tmp_path)

    window._open_project_status()
    panel = window._project_status_window

    assert panel._on_run_data_clone is None
    assert panel._on_install_plpgsql_check is None


def test_a_live_session_wires_both_node_actions_to_the_controller(qtbot, tmp_path):
    window, _dir = _window(qtbot, tmp_path)
    window._open_project_status()
    panel = window._project_status_window
    controller = window.sandbox_controller

    window._open_sandbox_session()

    assert controller.has_session
    assert panel._on_run_data_clone == controller.on_run_data_clone
    assert panel._on_install_plpgsql_check == controller.on_install_plpgsql_check


def test_a_dying_session_takes_both_node_actions_with_it(qtbot, tmp_path):
    window, _dir = _window(qtbot, tmp_path)
    window._open_project_status()
    panel = window._project_status_window
    window._open_sandbox_session()
    assert panel._on_run_data_clone is not None

    window.sandbox_controller.close_session()

    assert panel._on_run_data_clone is None
    assert panel._on_install_plpgsql_check is None


def test_the_clone_action_goes_through_the_controllers_confirmation(
    qtbot, tmp_path, monkeypatch
):
    """The destructive node action must reach `confirm_destructive` -- the
    controller's own gate with the controller's own warning -- not a bare dialog
    opened by the panel or the host."""
    window, _dir = _window(qtbot, tmp_path, mode=SandboxMode.WITH_DATA)
    window._open_sandbox_session()
    cloned = []
    window.sandbox_controller._cloner = lambda target, sandbox: cloned.append(
        (target, sandbox)
    )
    asked = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(
            lambda _p, _t, text, *a, **k: asked.append(text)
            or modals.QMessageBox.StandardButton.Yes
        ),
    )
    window._open_project_status()
    panel = window._project_status_window

    panel.node_widget(NodeFamily.SANDBOX1).click()
    node_window = panel.last_window
    assert node_window.action_button is not None
    node_window.action_button.click()

    from pgtp_editor.ui.sandbox_controller import SandboxController, SandboxOperation

    assert asked == [
        SandboxController.destructive_warning(SandboxOperation.CLONE_DATA)
    ]
    assert len(cloned) == 1


def test_declining_the_clone_confirmation_clones_nothing(
    qtbot, tmp_path, monkeypatch
):
    window, _dir = _window(qtbot, tmp_path, mode=SandboxMode.WITH_DATA)
    window._open_sandbox_session()
    cloned = []
    window.sandbox_controller._cloner = lambda target, sandbox: cloned.append(1)
    _refuse_confirmations(monkeypatch)
    window._open_project_status()
    panel = window._project_status_window

    panel.node_widget(NodeFamily.SANDBOX1).click()
    node_window = panel.last_window
    assert node_window.action_button is not None
    node_window.action_button.click()

    assert cloned == []
    assert any("cancelled" in text.casefold() for text in _audit_texts(window))


def test_the_install_action_reaches_install_plpgsql_check_without_a_prompt(
    qtbot, tmp_path, monkeypatch
):
    """Installing is non-destructive (`CREATE EXTENSION IF NOT EXISTS` drops
    nothing), so it must never reach `confirm_destructive`."""
    window, _dir = _window(qtbot, tmp_path)
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: _caps(
        available_extensions=frozenset({"plpgsql_check"})
    )
    window._open_sandbox_session()
    installed = []
    window.sandbox_controller._installer = lambda session: installed.append(session)
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: pytest_fail_no_prompt()),
    )
    window._open_project_status()
    panel = window._project_status_window

    panel.node_widget(NodeFamily.SANDBOX2).click()
    node_window = panel.last_window
    assert node_window.action_button is not None
    assert node_window.action_button.text() == "Install the plpgsql_check extension"
    node_window.action_button.click()

    assert len(installed) == 1


def pytest_fail_no_prompt():
    raise AssertionError(
        "installing plpgsql_check must not open a confirmation dialog"
    )
