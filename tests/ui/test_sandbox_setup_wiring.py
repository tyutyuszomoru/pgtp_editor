# tests/ui/test_sandbox_setup_wiring.py
"""Where the sandbox's provisioning gestures live, and that they still refuse.

* **Project Settings ▸ Connections ▸ Sandbox provisioning** -- `Provision
  sandbox`, `Reset sandbox` and `Create a sandbox database for me`. They used to
  live in `Database ▸ Sandbox Setup…`, which BUG-040 hid in project mode on the
  premise that Project Settings already owned every piece of sandbox
  configuration. It did not: those three existed nowhere else, and projectless
  the setup dialog built no controls at all -- so all three were unreachable in
  every mode. The owner's ruling (2026-08-09) makes the premise true instead of
  reverting the hiding: the gestures moved here and the menu entry is DELETED,
  not hidden, because a hidden action stays pinnable to the toolbar.
* **The Project Status window's two node actions** -- Sandbox1's "run data
  clone" and Sandbox2's "install plpgsql_check", aimed at the controller's
  zero-argument §18.8 adapters. Deliberately NOT duplicated into Project
  Settings. Present whenever a sandbox is CONFIGURED and stating the missing
  session when there is none (FQ-023's narrowing of carve-out 2), absent only
  when the project has no sandbox at all.

No modal is ever reached: `QMessageBox.question` is patched wherever a
destructive operation can be confirmed, and every `db/sandbox.py` seam on the
controller is stubbed, so nothing here opens a connection or issues
`CREATE DATABASE`.
"""
from PySide6.QtCore import QSettings

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.sandbox import SandboxCapabilities, SandboxMode
from pgtp_editor.ui import modals
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.project_settings_dialog import (
    NO_SESSION_REASON,
    NO_TARGET_REASON,
    ProjectSettingsDialog,
)
from pgtp_editor.ui.project_status_model import NodeFamily
from pgtp_editor.ui.sandbox_controller import SandboxController, SandboxOperation

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


def _open_settings(window, qtbot):
    """Open Project Settings through the real handler (`File ▸ Project
    Settings…`), then make its own off-thread calls (the two Test buttons)
    synchronous so no worker thread outlives the test."""
    window._ddl_project_ui.open_settings()
    dialog = window._ddl_project_ui.project_settings_dialog
    qtbot.addWidget(dialog)
    dialog._run_async = sync_run
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
    """Every produced row, wherever FQ-028 routed it.

    The sandbox lane's `[Sandbox]` / `[Project]` lines are operation narration
    and now land in the Activity Log rather than on a findings surface, so this
    helper reads BOTH surfaces -- the tests below are about what the app SAID,
    not about which panel says it."""
    panel = window.audit_panel
    return [panel.item(i).text() for i in range(panel.count())] + (
        window.activity_panel.row_texts()
    )


# --- The Database menu no longer offers Sandbox Setup… --------------------


def _setup_action(window):
    for action in window.menuBar().actions():
        menu = action.menu()
        if menu is None or action.text() != "Database":
            continue
        for entry in menu.actions():
            if "Sandbox Setup" in entry.text():
                return entry
    return None


def test_the_database_menu_no_longer_offers_sandbox_setup(qtbot, tmp_path):
    """Deleted, in every mode -- and deleted rather than hidden, so nothing is
    left on `self` for a toolbar to pin (`ToolbarController._walk_menu_actions`
    never tests `isVisible()`)."""
    window, _dir = _window(qtbot, tmp_path)

    assert _setup_action(window) is None
    assert not hasattr(window, "_sandbox_setup_action")
    assert not hasattr(window, "_open_sandbox_setup")


def test_the_sandbox_setup_module_is_gone_entirely(qtbot, tmp_path):
    """Its three gestures moved into Project Settings and its state display was
    always §18.8\'s Project Status window\'s job, so nothing was left to import.
    A dead-but-importable module is how the previous round of this got its
    "unreachable" status in the first place."""
    import importlib

    try:
        importlib.import_module("pgtp_editor.ui.sandbox_setup_dialog")
    except ModuleNotFoundError:
        return
    raise AssertionError("ui/sandbox_setup_dialog.py should have been deleted")


# --- Project Settings hosts the three provisioning actions ----------------


def test_project_settings_offers_the_three_provisioning_actions(qtbot, tmp_path):
    """All three, reachable with a project open -- which is the whole point of
    the move: before it, none of them were reachable in any mode."""
    window, project_dir = _window(qtbot, tmp_path)

    dialog = _open_settings(window, qtbot)

    assert isinstance(dialog, ProjectSettingsDialog)
    assert not dialog.isModal()
    assert dialog._sandbox_controller is window.sandbox_controller
    assert dialog._project_dir == project_dir
    assert dialog._provision_button is not None
    assert dialog._provision_button.text() == "Provision sandbox"
    assert dialog._reset_button is not None
    assert dialog._reset_button.text() == "Reset sandbox"
    assert dialog._create_database_button is not None
    assert (
        dialog._create_database_button.text() == "Create a sandbox database for me"
    )
    dialog.close()


def test_the_dialog_leaves_confirmation_to_the_controller_so_it_asks_once(
    qtbot, tmp_path, monkeypatch
):
    """`confirm=None` means the dialog pre-confirms nothing and the controller\'s
    own gate is the SINGLE prompt -- passing both would ask twice for one
    Provision."""
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
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
    dialog._provision_button.click()

    assert asked == [
        SandboxController.destructive_warning(SandboxOperation.PROVISION)
    ]
    dialog.close()


def test_provisioning_is_abandoned_when_the_confirmation_is_declined(
    qtbot, tmp_path, monkeypatch
):
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
    provisioned = []
    window.sandbox_controller._provisioner = (
        lambda snapshot, params, mode, **kwargs: provisioned.append(params)
        or _session()
    )
    _refuse_confirmations(monkeypatch)

    dialog._provision_button.click()

    assert provisioned == []
    assert any("cancelled" in text.casefold() for text in _audit_texts(window))
    dialog.close()


def test_create_a_database_for_me_confirms_and_creates_the_typed_name(
    qtbot, tmp_path, monkeypatch
):
    """§18.5 D2\'s mandatory mitigation for the `ForeignDatabaseError` refusal:
    the same confirmation, then `create_sandbox_database` against the
    maintenance database (`CREATE DATABASE` cannot run inside the database being
    created)."""
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
    created = []
    admin = []
    window.sandbox_controller._database_creator = (
        lambda admin_params, name: admin.append(admin_params) or created.append(name)
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
    dialog._new_database_name_edit.setText("pgtp_sandbox_fresh")

    dialog._create_database_button.click()

    assert asked == [
        SandboxController.destructive_warning(SandboxOperation.PROVISION)
    ]
    assert created == ["pgtp_sandbox_fresh"]
    assert admin[0].database == dialog._maintenance_database
    # The name that was actually created is what the dialog now shows and what
    # it recorded -- the field and the file can never disagree.
    assert dialog._sandbox_database_edit.text() == "pgtp_sandbox_fresh"
    assert dialog.recorded_settings().sandbox.database == "pgtp_sandbox_fresh"
    dialog.close()


def test_declining_creates_no_database(qtbot, tmp_path, monkeypatch):
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
    created = []
    window.sandbox_controller._database_creator = (
        lambda admin_params, name: created.append(name)
    )
    _refuse_confirmations(monkeypatch)

    dialog._create_database_button.click()

    assert created == []
    dialog.close()


def test_reset_confirms_before_dropping_anything(qtbot, tmp_path, monkeypatch):
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
    resets = []
    window.sandbox_controller.session.reset = lambda: resets.append(1)
    asked = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(
            lambda _p, _t, text, *a, **k: asked.append(text)
            or modals.QMessageBox.StandardButton.Yes
        ),
    )

    dialog._reset_button.click()

    assert asked == [SandboxController.destructive_warning(SandboxOperation.RESET)]
    assert resets == [1]
    dialog.close()


def test_declining_the_reset_confirmation_drops_nothing(qtbot, tmp_path, monkeypatch):
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
    resets = []
    window.sandbox_controller.session.reset = lambda: resets.append(1)
    _refuse_confirmations(monkeypatch)

    dialog._reset_button.click()

    assert resets == []
    assert any("cancelled" in text.casefold() for text in _audit_texts(window))
    dialog.close()


def test_reset_says_it_re_runs_the_creation_mode_not_the_checked_radio(
    qtbot, tmp_path
):
    """The mode radios promise a change "takes effect the next time the sandbox
    is reset/recreated". `SandboxSession.reset()` re-runs the mode the sandbox
    was CREATED with, so with Reset in the same dialog the promise is kept by
    Provision -- and the note beside Reset says exactly that instead of leaving
    the user to discover it from a reset that silently did the old thing."""
    window, _dir = _window(qtbot, tmp_path)

    dialog = _open_settings(window, qtbot)

    notes = dialog.sandbox_action_notes()
    assert "created with (without data (schema only))" in notes
    assert "takes effect when you Provision, not when you Reset" in notes
    dialog.close()


def test_an_unavailable_action_is_absent_with_its_reason_in_its_place(
    qtbot, tmp_path
):
    """Carve-out 2 travelled with the gestures: no dead controls. With no target
    there is nothing to build a baseline from, so Provision is ABSENT and the
    reason stands where it was."""
    window, project_dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)

    dialog._target_host_edit.setText("")

    assert dialog._provision_button is None
    assert dialog._create_database_button is None
    assert NO_TARGET_REASON in dialog.sandbox_action_notes()
    dialog.close()


def test_reset_is_absent_without_a_session_and_says_why(qtbot, tmp_path):
    window, _dir = _window(qtbot, tmp_path, reachable=False)

    dialog = _open_settings(window, qtbot)

    assert not window.sandbox_controller.has_session
    assert dialog._reset_button is None
    assert NO_SESSION_REASON in dialog.sandbox_action_notes()
    dialog.close()


def test_provisioning_records_the_chosen_mode_before_it_runs(
    qtbot, tmp_path, monkeypatch
):
    """D2a\'s mode is RECORDED, never re-derived -- written through the
    settings saver before the operation starts, so a crash mid-provision still
    leaves the project describing what it asked for."""
    window, project_dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
    _accept_confirmations(monkeypatch)
    dialog._sandbox_mode_with_data_radio.setChecked(True)

    dialog._provision_button.click()

    assert dialog.recorded_settings().sandbox_mode is SandboxMode.WITH_DATA
    from pgtp_editor.db.ddl_project import load_settings

    assert load_settings(project_dir).sandbox_mode is SandboxMode.WITH_DATA
    dialog.close()


def test_the_host_adopts_the_settings_provisioning_recorded(
    qtbot, tmp_path, monkeypatch
):
    """Adopted on the PROVISION result, not on the dialog closing: the dialog is
    non-modal and may be cancelled or left open for an hour, and the file was
    written the moment provisioning started."""
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
    _accept_confirmations(monkeypatch)
    dialog._sandbox_mode_with_data_radio.setChecked(True)

    dialog._provision_button.click()

    assert window._ddl_project_settings.sandbox_mode is SandboxMode.WITH_DATA
    dialog.close()


def test_adopting_the_settings_does_not_drop_the_session_just_provisioned(
    qtbot, tmp_path, monkeypatch
):
    """Adoption must NOT rebind the controller: `set_project` closes the session,
    and the session it would close is the one just provisioned -- which since
    BUG-040\'s auto-open would then be double-opened on top."""
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
    _accept_confirmations(monkeypatch)
    opens = []
    provisioned = []
    controller = window.sandbox_controller
    controller._opener = lambda params, **kwargs: opens.append(params) or _session()
    controller._provisioner = (
        lambda snapshot, params, mode, **kwargs: provisioned.append(params)
        or _session()
    )

    dialog._provision_button.click()

    assert controller.has_session
    assert len(provisioned) == 1
    assert opens == []
    dialog.close()
    assert controller.has_session


def test_the_host_ignores_uncommitted_field_edits(qtbot, tmp_path):
    """`recorded_settings()`, never `settings()`: the live field state includes
    edits the user has committed to nothing, and adopting those would make the
    window describe a project no file agrees with."""
    window, _dir = _window(qtbot, tmp_path)
    dialog = _open_settings(window, qtbot)
    before = window._ddl_project_settings

    dialog._name_edit.setText("typed but never OK'd")
    window._adopt_provisioned_sandbox_settings()

    assert dialog.recorded_settings() is None
    assert window._ddl_project_settings == before
    dialog.close()


def test_data_cloning_still_refuses_for_a_schema_only_sandbox(
    qtbot, tmp_path, monkeypatch
):
    """The refusal survived the move untouched, because it never lived in the
    dialog: cloning into a schema-only sandbox would silently change what kind
    of sandbox it is, and the mode is chosen once at creation time (D2a)."""
    window, _dir = _window(qtbot, tmp_path, mode=SandboxMode.SCHEMA_ONLY)
    cloned = []
    window.sandbox_controller._cloner = lambda target, sandbox: cloned.append(1)
    _accept_confirmations(monkeypatch)

    window.sandbox_controller.run_data_clone()

    assert cloned == []
    assert any(
        "without data" in text and "schema-only" in text
        for text in _audit_texts(window)
    )


def test_the_console_refusal_names_gestures_that_exist(qtbot, tmp_path, monkeypatch):
    """The rule this test exists for has now outlived four wordings: "Database ▸
    Project Status…", then `Open Sandbox Session` (deleted by BUG-040), then
    `Sandbox Setup…` (hidden in project mode by BUG-040), and now `Sandbox
    Setup…` again (deleted outright).

    The rule: **the refusal may only name a way back that is REACHABLE FROM
    WHERE THE REFUSAL FIRES.** Naming a deleted entry is the same dead end as
    naming a hidden one. Project Settings is the name that survives, and it is
    now the truthful one -- it really does host the provisioning gestures."""
    window, _dir = _window(qtbot, tmp_path, reachable=False)
    _refuse_confirmations(monkeypatch)

    assert window._open_sandbox_sql_console() is None

    message = window.statusBar().currentMessage()
    assert "Project Settings" in message
    assert "Sandbox Setup" not in message
    assert "Open Sandbox Session" not in message
    assert "Project Status" not in message


def test_the_consoles_no_session_text_names_a_reachable_way_back():
    """Same rule, same reason: the console only exists in project mode."""
    from pgtp_editor.ui.sql_console_panel import NO_SESSION_TEXT

    assert "Project Settings" in NO_SESSION_TEXT
    assert "Sandbox Setup" not in NO_SESSION_TEXT


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
