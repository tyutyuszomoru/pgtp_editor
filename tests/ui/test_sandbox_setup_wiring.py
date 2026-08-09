# tests/ui/test_sandbox_setup_wiring.py
"""The three sandbox gestures that existed as machinery but not as clicks:

* **Database ▸ Sandbox Setup…** -- `ui/sandbox_setup_dialog.py` shipped complete
  with no menu entry anywhere, so re-provisioning had no entry point at all and
  several user-facing strings already told the user to open a menu item that did
  not exist. Wired non-modally, with `confirm=None` so the CONTROLLER owns the
  single destructive prompt (passing both asks twice).
* **The Project Status window's two dead node actions** -- Sandbox1's "run data
  clone" and Sandbox2's "install plpgsql_check", now aimed at the controller's
  zero-argument §18.8 adapters. Present whenever a sandbox is CONFIGURED and
  stating the missing session when there is none (FQ-023's narrowing of
  carve-out 2), absent only when the project has no sandbox at all.

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

from tests.ui._sandbox_stubs import fake_session as _session, stub_sandbox_provisioning, sync_run


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


def _window(
    qtbot,
    tmp_path,
    *,
    sandbox_host="localhost",
    mode=SandboxMode.SCHEMA_ONLY,
    reachable=True,
):
    """A window with the project open. **Opening it opens the session**
    (BUG-040), so `reachable=False` is how a test reaches the sessionless state
    that used to be the default: with the manual `Open Sandbox Session` gesture
    deleted, the only way to sit in a configured-but-sessionless project is an
    auto-open that failed."""
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
    if not reachable:
        opened = window.sandbox_controller._opener

        def _unreachable(*args, **kwargs):
            raise RuntimeError("could not connect to the sandbox")

        window.sandbox_controller._opener = _unreachable
        window._ddl_project_ui.set_active_project(project_dir, settings)
        # The provisioning path (which opens its own session) stays usable, so
        # only the auto-open is what failed.
        window.sandbox_controller._opener = opened
        return window, project_dir
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
    """The entry EXISTS in every mode and is never session-gated -- this is the
    one gesture that can create a sandbox, so it must be reachable exactly when
    there is no sandbox yet.

    Its VISIBILITY is now projectless-only (BUG-040's third leg), which is why
    this asserts only that it EXISTS and leaves the two modes to
    `tests/ui/test_sandbox_check_console_wiring.py`. A project is open in this
    fixture, so it is hidden -- hidden, never deleted, because projectless it is
    the only way to get a sandbox at all.

    No `isEnabled()` assertion: Qt's `QAction.isEnabled()` folds in visibility,
    so a hidden action reports disabled and the check would say nothing about
    the enabled-state posture it looks like it is guarding."""
    window, _dir = _window(qtbot, tmp_path)

    action = _setup_action(window)

    assert action is not None
    assert action is window._sandbox_setup_action
    assert not action.isVisible()


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
    and the session it would close is the one the dialog just created.

    BUG-040 raised the stakes: since `_bind_sandbox_controller_to_project` now
    OPENS a session, rebinding here would not merely drop the provisioned
    session, it would double-open. The bypass is what keeps the Setup path
    ending with exactly one live session."""
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_setup(window, qtbot)
    _accept_confirmations(monkeypatch)
    opens = []
    provisioned = []
    controller = window.sandbox_controller
    controller._opener = lambda params, **kwargs: opens.append(params) or _session()
    controller._provisioner = (
        lambda snapshot, params, mode, **kwargs: provisioned.append(params)
        or _session()
    )

    dialog.provision()

    assert window.sandbox_controller.has_session
    # The dialog provisioned exactly one session and the host opened none on
    # top of it -- adoption never went through the auto-opening bind.
    assert len(provisioned) == 1
    assert opens == []
    dialog.close()
    assert window.sandbox_controller.has_session


def test_the_console_refusal_names_gestures_that_exist(
    qtbot, tmp_path, monkeypatch
):
    """The stale string said "Database ▸ Project Status…", which never opened a
    session; BUG-040 then deleted `Open Sandbox Session`, which the replacement
    named. The rule this test exists for outlives both: **the refusal may only
    name menu entries that exist**, and today that is `Sandbox Setup…`.

    Since FQ-023 the refusal is a dialog that OFFERS to open the session;
    declining leaves the same reason in the status bar, which is what is read
    here (the offer itself is covered in `test_sandbox_check_console_wiring`)."""
    window, _dir = _window(qtbot, tmp_path, reachable=False)
    _refuse_confirmations(monkeypatch)

    assert window._open_sandbox_sql_console() is None

    message = window.statusBar().currentMessage()
    assert "Sandbox Setup…" in message
    assert _setup_action(window) is not None  # ...and that entry really exists
    assert "Open Sandbox Session" not in message
    assert "Project Status" not in message


def test_the_consoles_no_session_text_names_the_entry_that_now_exists():
    from pgtp_editor.ui.sql_console_panel import NO_SESSION_TEXT

    assert "Sandbox Setup…" in NO_SESSION_TEXT


# --- The Project Status window's two node actions -------------------------


def test_the_node_actions_are_absent_with_no_sandbox_configured(qtbot, tmp_path):
    """FQ-023: the ABSENT case is "no sandbox at all" -- genuinely inapplicable,
    so the panel gets `None` and renders no button."""
    window, _dir = _window(qtbot, tmp_path, sandbox_host="")

    window._open_project_status()
    panel = window._project_status_window

    assert panel._on_run_data_clone is None
    assert panel._on_install_plpgsql_check is None


def test_a_configured_sandbox_gives_both_node_actions_a_reporting_button(
    qtbot, tmp_path, monkeypatch
):
    """FQ-023's other half: a sandbox with no session leaves both buttons THERE,
    and clicking one states the missing session instead of doing nothing."""
    window, _dir = _window(qtbot, tmp_path, reachable=False)
    window._open_project_status()
    panel = window._project_status_window
    assert not window.sandbox_controller.has_session
    assert panel._on_run_data_clone is not None
    assert panel._on_install_plpgsql_check is not None
    installed = []
    window.sandbox_controller._installer = lambda session: installed.append(session)
    asked = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(
            lambda _p, _t, text, *a, **k: asked.append(text)
            or modals.QMessageBox.StandardButton.Cancel
        ),
    )

    panel._on_install_plpgsql_check()

    assert installed == []  # nothing ran, and nothing connected
    assert "no sandbox session is open" in asked[0]
    assert "no sandbox session is open" in window.statusBar().currentMessage()
    # BUG-040: the refusal cannot advertise a menu entry that was deleted.
    assert "Open Sandbox Session" not in asked[0]


def test_a_live_session_wires_both_node_actions_to_the_controller(qtbot, tmp_path):
    window, _dir = _window(qtbot, tmp_path)
    window._open_project_status()
    panel = window._project_status_window
    controller = window.sandbox_controller
    # `installable` + superuser is the one state `install_gate` OFFERS on, so the
    # click reaches `_installer` instead of stopping at the gate's own reason.
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: _caps(
        available_extensions=frozenset({"plpgsql_check"})
    )

    window._open_sandbox_session()

    assert controller.has_session
    # The callbacks are FQ-023 wrappers rather than the bound adapters
    # themselves, so what is asserted is that they reach the controller's
    # operation -- no modal, because with a session there is nothing to refuse.
    installed = []
    controller._installer = lambda session: installed.append(session)
    panel._on_install_plpgsql_check()

    assert installed == [controller.session]


def test_a_dying_session_leaves_both_node_actions_reporting(
    qtbot, tmp_path, monkeypatch
):
    """The session, not the sandbox, went away -- so the buttons stay (FQ-023)
    and the refusal is what changes. The session is re-read at CLICK time, which
    is why no refresh is needed for the wrapper to notice."""
    window, _dir = _window(qtbot, tmp_path)
    window._open_project_status()
    panel = window._project_status_window
    assert window.sandbox_controller.has_session  # BUG-040: it came up with the project
    cloned = []
    window.sandbox_controller._cloner = lambda target, sandbox: cloned.append(1)
    _refuse_confirmations(monkeypatch)

    window.sandbox_controller.close_session()

    assert panel._on_run_data_clone is not None
    assert panel._on_install_plpgsql_check is not None
    panel._on_run_data_clone()
    assert cloned == []
    assert "no sandbox session is open" in window.statusBar().currentMessage()


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
