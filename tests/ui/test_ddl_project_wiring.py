# tests/ui/test_ddl_project_wiring.py
"""MainWindow wiring for local DDL-versioning projects (§18.2): New/Open/Close
Project, the "*_ddl_project_folder/_ddl_project_settings*" state (distinct
from `_current_project`, the open `.pgtp`), and the `.pgtp` checksum drift
report on Open.

No live DB, no modal calls (NewProjectDialog is shown non-modally, exactly
like ConnectionSetupDialog).
"""
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import GitConfig, PgtpLink, ProjectSettings, load_settings
from pgtp_editor.ui.ddl_buffer_panel import DISCARD_LOCAL_LABEL
from pgtp_editor.ui.ddl_project_controller import DdlProjectController
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.new_project_dialog import NewProjectDialog
from pgtp_editor.ui.project_settings_dialog import ProjectSettingsDialog

from ._menu_helpers import find_action, find_top_menu
from ._sandbox_stubs import stub_sandbox_provisioning, sync_run
from pgtp_editor.ui import modals


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _window(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    # BUG-043: the window-wide off-thread seam. `_shell_run_async` re-reads this
    # at call time, and since BUG-043 the sandbox controller goes through that
    # trampoline too, so this one line makes EVERY lane run in-test -- including
    # `refresh_target_connection_status`, which really dialled a configured
    # target host and delivered the result after this window was destroyed.
    window._run_async = sync_run
    # FQ-007: New Project now CREATES + provisions the sandbox database, so the
    # controller's db/sandbox.py seams are stubbed here -- no test may reach a
    # real server, and none of these tests is about provisioning.
    stub_sandbox_provisioning(window)
    return window


# --- Menu ---------------------------------------------------------------
def test_database_menu_has_new_open_close_project_actions(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    menu = find_top_menu(window, "File")
    assert find_action(menu, "New Project…") is not None
    assert find_action(menu, "Open Project…") is not None
    assert find_action(menu, "Close Project") is not None


def test_close_project_action_starts_disabled(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._ddl_project_ui.close_project_action.isEnabled() is False


# --- New Project ----------------------------------------------------------
def test_new_ddl_project_creates_the_folder_and_settings_file(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "my-project"
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("ERP overhaul")
    dialog._folder_edit.setText(str(project_dir))
    dialog._sandbox_host_edit.setText("localhost")

    window._ddl_project_ui.create_project(dialog)

    assert project_dir.exists()
    loaded = load_settings(project_dir)
    assert loaded.name == "ERP overhaul"
    assert loaded.sandbox.host == "localhost"


def test_new_ddl_project_becomes_the_active_project(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "my-project"
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(project_dir))

    window._ddl_project_ui.create_project(dialog)

    assert window._ddl_project_folder == project_dir
    assert window._ddl_project_settings is not None
    assert window._ddl_project_ui.close_project_action.isEnabled() is True


def test_new_ddl_project_captures_git_config_inert(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "my-project"
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(project_dir))
    dialog._git_server_edit.setText("git.example.com")
    dialog._git_branch_edit.setText("feature/x")

    window._ddl_project_ui.create_project(dialog)

    loaded = load_settings(project_dir)
    assert loaded.git == GitConfig(server="git.example.com", checkout_branch="feature/x")


def test_new_ddl_project_on_an_existing_folder_reuses_it(qtbot, tmp_path):
    """Folder already exists (e.g. picked via the folder browser) -- must
    not fail, must not wipe anything already there."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "already-there"
    project_dir.mkdir()
    (project_dir / "unrelated.txt").write_text("keep me", encoding="utf-8")
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(project_dir))

    window._ddl_project_ui.create_project(dialog)

    assert (project_dir / "unrelated.txt").read_text(encoding="utf-8") == "keep me"


# --- Open Project -----------------------------------------------------------
def test_open_ddl_project_loads_existing_settings(qtbot, tmp_path, monkeypatch):
    project_dir = tmp_path / "existing"
    from pgtp_editor.db.ddl_project import save_settings

    save_settings(project_dir, ProjectSettings(name="Prior work"))
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()

    assert window._ddl_project_settings.name == "Prior work"
    assert window._ddl_project_folder == project_dir
    assert window._ddl_project_ui.close_project_action.isEnabled() is True


def test_open_ddl_project_cancelled_picker_does_nothing(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: ""),  # Cancel
    )

    window._ddl_project_ui.open_project()

    assert window._ddl_project_folder is None
    assert window._ddl_project_ui.close_project_action.isEnabled() is False


def test_open_ddl_project_on_a_non_project_folder_is_rejected(qtbot, tmp_path, monkeypatch):
    """BUG-022: a folder with no `.ddlproject/settings.json` marker is not a
    project -- Open must reject it (message + abort) rather than silently
    loading default settings for it."""
    project_dir = tmp_path / "brand-new"
    project_dir.mkdir()
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )
    monkeypatch.setattr(modals.QMessageBox, "warning", lambda *a, **k: None)

    window._ddl_project_ui.open_project()

    assert window._ddl_project_folder is None
    assert window._ddl_project_settings is None
    assert window._ddl_project_ui.close_project_action.isEnabled() is False


def test_open_ddl_project_on_a_valid_project_folder_proceeds(qtbot, tmp_path, monkeypatch):
    """A folder that DOES carry the `.ddlproject/settings.json` marker (even
    with otherwise-default settings, e.g. freshly created and never
    customized) is a real project and Open must proceed normally."""
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "real-project"
    save_settings(project_dir, ProjectSettings())
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()

    assert window._ddl_project_settings == ProjectSettings()
    assert window._ddl_project_folder == project_dir
    assert window._ddl_project_ui.close_project_action.isEnabled() is True


def test_open_ddl_project_folder_picker_shows_dirs_only(qtbot, tmp_path, monkeypatch):
    """BUG-022: the folder chooser must pass ShowDirsOnly so files aren't
    shown alongside folders."""
    window = _window(qtbot, tmp_path)

    captured = {}

    def fake_get_existing_directory(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return ""

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(fake_get_existing_directory),
    )

    window._ddl_project_ui.open_project()

    options = captured["args"][3] if len(captured["args"]) > 3 else captured["kwargs"].get("options")
    assert modals.QFileDialog.Option.ShowDirsOnly in modals.QFileDialog.Options(options)


# --- Auto-open the linked .pgtp on Open Project (BUG-021) ------------------
def test_open_ddl_project_auto_opens_the_linked_working_copy(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    working_copy = project_dir / "app.pgtp"
    project_dir.mkdir()
    working_copy.write_text(_VALID_PGTP, encoding="utf-8")
    save_settings(
        project_dir,
        ProjectSettings(pgtp=PgtpLink(working_copy_path=str(working_copy))),
    )
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()

    assert window._current_project_path == str(working_copy)
    assert window._current_project is not None


def test_open_project_action_signal_path_auto_opens_the_linked_working_copy(
    qtbot, tmp_path, monkeypatch
):
    """BUG-021 regression: the test above calls `_open_ddl_project()` directly,
    so `on_ready` is None and auto-open fires. The REAL menu path goes through
    `QAction.triggered`, which passes `checked=False` -- and `False is not None`
    took the on_ready branch, calling `False()`. Drive the actual signal."""
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    working_copy = project_dir / "app.pgtp"
    project_dir.mkdir()
    working_copy.write_text(_VALID_PGTP, encoding="utf-8")
    save_settings(
        project_dir,
        ProjectSettings(pgtp=PgtpLink(working_copy_path=str(working_copy))),
    )
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    action = find_action(find_top_menu(window, "File"), "Open Project…")
    assert action is not None
    action.trigger()

    assert window._current_project_path == str(working_copy)
    assert window._current_project is not None


def test_new_project_action_signal_path_does_not_treat_checked_as_on_ready(
    qtbot, tmp_path, monkeypatch
):
    """BUG-021, parallel latent defect: `new_project` is wired the same
    way, so the dialog's accepted handler would call `False()` (TypeError)."""
    window = _window(qtbot, tmp_path)
    created = []
    monkeypatch.setattr(
        DdlProjectController, "create_project",
        lambda self, dialog: created.append(dialog),
    )

    action = find_action(find_top_menu(window, "File"), "New Project…")
    assert action is not None
    action.trigger()

    dialog = window._ddl_project_ui.new_project_dialog
    assert isinstance(dialog, NewProjectDialog)
    dialog.accepted.emit()  # must not raise TypeError: 'bool' object is not callable
    assert created == [dialog]


def test_open_ddl_project_with_no_linked_pgtp_does_nothing(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    save_settings(project_dir, ProjectSettings())  # no .pgtp linked, empty folder
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()  # must not raise

    assert window._current_project is None
    assert window._current_project_path is None


def test_open_ddl_project_with_exactly_one_unlinked_pgtp_auto_opens_it(qtbot, tmp_path, monkeypatch):
    """No recorded link yet, but exactly one `.pgtp` sits in the project
    folder -- auto-open it (BUG-021 zero/one/multiple scope)."""
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    save_settings(project_dir, ProjectSettings())
    only_pgtp = project_dir / "solo.pgtp"
    only_pgtp.write_text(_VALID_PGTP, encoding="utf-8")
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()

    assert window._current_project_path == str(only_pgtp)


def test_open_ddl_project_with_multiple_unlinked_pgtp_reports_via_audit_and_guesses_nothing(
    qtbot, tmp_path, monkeypatch
):
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    save_settings(project_dir, ProjectSettings())
    (project_dir / "one.pgtp").write_text(_VALID_PGTP, encoding="utf-8")
    (project_dir / "two.pgtp").write_text(_VALID_PGTP, encoding="utf-8")
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()

    assert window._current_project is None  # never guessed which one
    texts = window.activity_panel.row_texts()
    assert any(
        ("[Project]" in t) and "multiple" in t.lower() for t in texts
    )


def test_open_ddl_project_via_prompt_pgtp_open_mode_does_not_double_load(qtbot, tmp_path, monkeypatch):
    """The on_ready gotcha: when _open_ddl_project is invoked with an
    on_ready callback (e.g. from _prompt_pgtp_open_mode's "Open Project…"
    choice), the auto-open-linked-pgtp behavior must NOT also fire -- only
    the caller's own on_ready load should happen."""
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    linked_copy = project_dir / "other.pgtp"
    project_dir.mkdir()
    linked_copy.write_text(_VALID_PGTP, encoding="utf-8")
    save_settings(
        project_dir,
        ProjectSettings(pgtp=PgtpLink(working_copy_path=str(linked_copy))),
    )
    window = _window(qtbot, tmp_path)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    opened = []
    original_open = window.open_project_file

    def tracking_open(path):
        opened.append(str(path))
        return original_open(path)

    window.open_project_file = tracking_open
    window._ddl_project_ui.open_project(on_ready=lambda: window.open_project_file(str(source)))

    # Only the caller's own path was opened -- never the linked working copy.
    assert opened == [str(source)]


# --- .pgtp checksum drift report on open ------------------------------------
def _existing_working_copy(project_dir: Path, name: str = "source.pgtp") -> Path:
    """A real, parseable working copy inside `project_dir` -- what a WHOLE
    §18.2 link points at (BUG-260810173246)."""
    project_dir.mkdir(parents=True, exist_ok=True)
    working_copy = project_dir / name
    working_copy.write_text(_VALID_PGTP, encoding="utf-8")
    return working_copy


def test_open_reports_unchanged_source_pgtp(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import content_hash, save_settings

    source = tmp_path / "source.pgtp"
    source.write_text("<Project/>", encoding="utf-8")
    project_dir = tmp_path / "proj"
    # BUG-260810173246: a drift verdict needs a WHOLE link -- a recorded working
    # copy with a real file behind it -- so these drift tests carry one.
    working_copy = _existing_working_copy(project_dir, "source.pgtp")
    save_settings(
        project_dir,
        ProjectSettings(
            pgtp=PgtpLink(
                source_path=str(source),
                working_copy_path=str(working_copy),
                last_known_source_checksum=content_hash("<Project/>"),
            )
        ),
    )
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()

    texts = window.activity_panel.row_texts()
    assert any("unchanged" in t.lower() for t in texts if ("[Project]" in t))


def test_open_reports_drifted_source_pgtp(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import content_hash, save_settings

    source = tmp_path / "source.pgtp"
    source.write_text("<Project><Changed/></Project>", encoding="utf-8")
    project_dir = tmp_path / "proj"
    working_copy = _existing_working_copy(project_dir, "source.pgtp")
    save_settings(
        project_dir,
        ProjectSettings(
            pgtp=PgtpLink(
                source_path=str(source),
                working_copy_path=str(working_copy),
                last_known_source_checksum=content_hash("<Project/>"),  # stale
            )
        ),
    )
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()

    texts = window.activity_panel.row_texts()
    assert any(
        ("[Project]" in t) and "changed" in t.lower() for t in texts
    )


def test_open_with_no_pgtp_link_reports_nothing(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    save_settings(project_dir, ProjectSettings())  # no .pgtp linked
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )
    before = window.audit_panel.count()

    window._ddl_project_ui.open_project()

    assert window.audit_panel.count() == before


def test_open_reports_unreadable_source_pgtp_gracefully(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    working_copy = _existing_working_copy(project_dir, "source.pgtp")
    save_settings(
        project_dir,
        ProjectSettings(
            pgtp=PgtpLink(
                source_path=str(tmp_path / "does-not-exist.pgtp"),
                working_copy_path=str(working_copy),
            )
        ),
    )
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()  # must not raise

    texts = window.activity_panel.row_texts()
    assert any("could not read" in t.lower() for t in texts)


# --- Close Project -----------------------------------------------------------
def test_close_ddl_project_clears_state_and_disables_action(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    window._ddl_project_ui.create_project(dialog)

    window._ddl_project_ui.close_project()

    assert window._ddl_project_folder is None
    assert window._ddl_project_settings is None
    assert window._ddl_project_ui.close_project_action.isEnabled() is False


def test_close_ddl_project_when_none_open_is_a_no_op(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_project_ui.close_project()  # must not raise
    assert window._ddl_project_folder is None


# --- Project Settings dialog -------------------------------------------------
def test_project_settings_menu_action_exists(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    menu = find_top_menu(window, "File")
    assert find_action(menu, "Project Settings…") is not None


def test_project_settings_opens_directly_when_a_project_is_already_active(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    window._ddl_project_ui.create_project(dialog)

    window._ddl_project_ui.open_settings()

    assert isinstance(window._ddl_project_ui.project_settings_dialog, ProjectSettingsDialog)
    assert window._ddl_project_ui.project_settings_dialog.settings() == window._ddl_project_settings


def test_saving_project_settings_writes_to_disk_and_updates_state(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "p"
    new_project_dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(new_project_dialog)
    new_project_dialog._folder_edit.setText(str(project_dir))
    window._ddl_project_ui.create_project(new_project_dialog)

    window._ddl_project_ui.open_settings()
    settings_dialog = window._ddl_project_ui.project_settings_dialog
    settings_dialog._name_edit.setText("renamed")

    settings_dialog.accepted.emit()

    assert window._ddl_project_settings.name == "renamed"
    assert load_settings(project_dir).name == "renamed"


# --- "Project Required" (Create…/Open…/Cancel) ------------------------------
def test_project_required_create_path(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "created-via-required"

    class _FakeBox:
        ButtonRole = QMessageBox.ButtonRole

        def __init__(self, parent=None):
            self.buttons = {}

        def setWindowTitle(self, _title):
            pass

        def setText(self, _text):
            pass

        def addButton(self, label, role):
            button = object()
            self.buttons[label] = button
            return button

        def exec(self):
            return None

        def clickedButton(self):
            return self.buttons["Create…"]

    monkeypatch.setattr("pgtp_editor.ui.modals.QMessageBox", _FakeBox)
    got = []

    window._ddl_project_ui.require_project(lambda: got.append(True))

    # The Create… path opened NewProjectDialog; complete it as the user would.
    dialog = window._ddl_project_ui.new_project_dialog
    dialog._folder_edit.setText(str(project_dir))
    dialog.accepted.emit()

    assert got == [True]
    assert window._ddl_project_folder == project_dir


def test_project_required_cancel_path_never_calls_on_ready(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)

    class _FakeBox:
        ButtonRole = QMessageBox.ButtonRole

        def __init__(self, parent=None):
            self.buttons = {}

        def setWindowTitle(self, _title):
            pass

        def setText(self, _text):
            pass

        def addButton(self, label, role):
            button = object()
            self.buttons[label] = button
            return button

        def exec(self):
            return None

        def clickedButton(self):
            return self.buttons["Cancel"]

    monkeypatch.setattr("pgtp_editor.ui.modals.QMessageBox", _FakeBox)
    got = []

    window._ddl_project_ui.require_project(lambda: got.append(True))

    assert got == []
    assert window._ddl_project_folder is None


def test_project_required_skips_the_dialog_entirely_when_already_open(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    window._ddl_project_ui.create_project(dialog)
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not prompt")),
    )
    got = []

    window._ddl_project_ui.require_project(lambda: got.append(True))

    assert got == [True]


# --- Edit DDL, project-open branch: the §18.2 checkout (FQ-024) --------------
def _open_project(window, folder):
    from pgtp_editor.db.ddl_project import ProjectSettings, save_settings

    save_settings(folder, ProjectSettings())
    window._ddl_project_ui.set_active_project(folder, ProjectSettings())


def test_checkout_seeds_the_file_when_absent(qtbot, tmp_path):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

    window._edit_ddl_checked_out(ref, "CREATE FUNCTION pr.recalc() ...")

    ddl_path = project_dir / "ddl" / "pr.recalc.sql"
    assert ddl_path.read_text(encoding="utf-8") == "CREATE FUNCTION pr.recalc() ..."


def test_checkout_opens_a_tab_pointed_at_the_checked_out_file(qtbot, tmp_path):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

    window._edit_ddl_checked_out(ref, "CREATE FUNCTION pr.recalc() ...")

    ddl_path = (project_dir / "ddl" / "pr.recalc.sql").resolve()
    # Keyed on object identity, never on the resolved path (FQ-024) -- the save
    # DESTINATION is the project-dependent part, not the key.
    panel = window.center_stage.ddl_object_tab(ref.key)
    assert panel is not None
    assert window.center_stage.ddl_object_tab(str(ddl_path)) is None
    assert panel.text() == "CREATE FUNCTION pr.recalc() ..."
    assert panel.resolve_save_path() == ddl_path


def test_checkout_of_an_already_checked_out_file_opens_from_disk_not_the_live_source(qtbot, tmp_path):
    """File present -> open from disk. The local file is the editable truth
    and is never silently overwritten from the live DB."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ddl_path = project_dir / "ddl" / "pr.recalc.sql"
    ddl_path.parent.mkdir(parents=True)
    ddl_path.write_text("-- hand-edited local truth\n", encoding="utf-8")
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

    window._edit_ddl_checked_out(ref, "CREATE FUNCTION pr.recalc() ... -- stale live def")

    panel = window.center_stage.ddl_object_tab(ref.key)
    assert panel.text() == "-- hand-edited local truth\n"
    assert ddl_path.read_text(encoding="utf-8") == "-- hand-edited local truth\n"  # untouched


def test_re_invoking_checkout_focuses_the_existing_tab(qtbot, tmp_path):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    window._edit_ddl_checked_out(ref, "text")
    first = window.center_stage.ddl_object_tab(ref.key)
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    window._edit_ddl_checked_out(ref, "ignored -- already checked out")

    second = window.center_stage.ddl_object_tab(ref.key)
    assert second is first
    assert window.center_stage.currentWidget() is first


def test_checkout_of_a_trigger_uses_the_table_qualified_path(qtbot, tmp_path):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="trigger", schema="pr", name="trg_audit", table="orders")

    window._edit_ddl_checked_out(ref, "CREATE TRIGGER trg_audit ...")

    ddl_path = project_dir / "ddl" / "pr.orders.trg_audit.sql"
    assert ddl_path.exists()


def test_projectless_edit_ddl_never_raises_the_project_required_prompt(qtbot, tmp_path, monkeypatch):
    """FQ-024: with ONE `Edit DDL` entry, `require_project`'s
    Create…/Open…/Cancel modal must NOT ride along -- it would fire on every
    edit in projectless mode, which is a first-class supported mode (§18.2)."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not prompt")),
    )
    monkeypatch.setattr(
        window._ddl_project_ui,
        "require_project",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not require a project")),
    )

    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")

    assert window._ddl_project_folder is None  # nothing created, nothing asked
    assert window.center_stage.ddl_object_tab(ref.key) is not None


def test_checkout_reports_drift_from_the_last_deployed_reference(qtbot, tmp_path):
    from pgtp_editor.db.ddl_project import DeployedObject, ProjectSettings, save_settings
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash="stale-hash")}
    )
    save_settings(project_dir, settings)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

    window._edit_ddl_checked_out(ref, "CREATE FUNCTION pr.recalc() ... -- drifted")

    texts = window.activity_panel.row_texts()
    assert any(("[Project]" in t) and "drifted" in t.lower() for t in texts)


def test_checkout_reports_no_drift_when_hash_matches_the_deployed_reference(qtbot, tmp_path):
    from pgtp_editor.db.ddl_project import (
        DeployedObject,
        ProjectSettings,
        content_hash,
        save_settings,
    )
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    live_source = "CREATE FUNCTION pr.recalc() ..."
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash=content_hash(live_source))}
    )
    save_settings(project_dir, settings)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    before = window.audit_panel.count()

    window._edit_ddl_checked_out(ref, live_source)

    assert window.audit_panel.count() == before  # nothing drifted, nothing reported


def test_checkout_disambiguates_overloads_using_the_live_schema(qtbot, tmp_path):
    """Path computation for a routine must use the WHOLE routine set from
    the currently-loaded schema, not just the one ref being checked out."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
    from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    window.ddl_browser_panel._schema = DatabaseSchema(
        routines={
            "pr.fmt(integer)": RoutineInfo(schema="pr", name="fmt", arg_types=["integer"]),
            "pr.fmt(text)": RoutineInfo(schema="pr", name="fmt", arg_types=["text"]),
        }
    )
    ref = DdlObjectRef(kind="function", schema="pr", name="fmt", arg_types=("text",))

    window._edit_ddl_checked_out(ref, "CREATE FUNCTION pr.fmt(a text) ...")

    # "text" sorts after "integer" -- the second overload, so it gets _1.
    assert (project_dir / "ddl" / "pr.fmt_1.sql").exists()


# --- Edit DDL: ONE gesture, two behaviours from project state (FQ-024) -------
def test_edit_ddl_takes_the_checkout_branch_when_a_project_is_open(qtbot, tmp_path):
    """The behaviour comes from project state, never from which words were
    clicked: with a project open, `Edit DDL` IS the checkout."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")

    ddl_path = (project_dir / "ddl" / "pr.recalc.sql").resolve()
    assert ddl_path.read_text(encoding="utf-8") == "CREATE FUNCTION pr.recalc() ..."
    assert window.center_stage.ddl_object_tab(ref.key).resolve_save_path() == ddl_path
    assert "ddl/pr.recalc.sql" in load_settings(project_dir).deployed


def test_projectless_edit_ddl_holds_the_live_source_and_writes_nothing(qtbot, tmp_path):
    """The other branch: no checkout, no manifest, no file -- the tab holds the
    live introspected definition and saves through Save As… later."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")

    panel = window.center_stage.ddl_object_tab(ref.key)
    assert panel.text() == "CREATE FUNCTION pr.recalc() ..."
    assert panel.save_path is None  # nothing resolved yet, nothing written
    assert list(tmp_path.glob("**/*.sql")) == []


def test_edit_ddl_twice_across_opening_a_project_yields_exactly_one_tab(qtbot, tmp_path):
    """THE FQ-024 regression test, and the reason the keying rule is one rule.

    Before this, the two branches keyed tabs in different namespaces -- the live
    branch on `ref.key`, checkout on `str(ddl_path)` -- and neither existence
    check consulted the other, so this exact sequence produced TWO identically
    titled tabs with TWO different save destinations, silently diverging copies
    of one object. `CenterStage.open_ddl_object_tab`'s docstring claimed the
    opposite.
    """
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")
    first = window.center_stage.ddl_object_tab(ref.key)
    assert first is not None

    _open_project(window, tmp_path / "proj")
    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")

    assert window.center_stage.ddl_object_panels() == [first]


def test_checking_out_then_editing_the_same_object_yields_exactly_one_tab(qtbot, tmp_path):
    """The same divergence in the order the user actually hit it: check out (a
    project is open, so `Edit DDL` checks out), then invoke `Edit DDL` again."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path / "proj")
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    window._edit_ddl_checked_out(ref, "CREATE FUNCTION pr.recalc() ...")
    checked_out = window.center_stage.ddl_object_tab(ref.key)

    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")

    assert window.center_stage.ddl_object_panels() == [checked_out]
    assert window.center_stage.currentWidget() is checked_out


# --- BUG-260810193333 Part B: Discard local change ---------------------------
def _project_narration(window):
    """`[Project]` rows are journalled, not listed (FQ-028's router) -- so the
    Audit assertions read the journal the row actually lands in."""
    return [e.verb or "" for e in window.activity_log.entries]


def _answer_confirm(monkeypatch, button):
    """Stub the ONE confirmation seam. Never a real modal (CLAUDE.md)."""
    seen = []

    def question(_parent, title, text, *a, **k):
        seen.append((title, text))
        return button

    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox.question", staticmethod(question)
    )
    return seen


def _checked_out(window, tmp_path, *, source="CREATE FUNCTION pr.recalc() ..."):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    window._edit_ddl_checked_out(ref, source)
    return ref, project_dir, (project_dir / "ddl" / "pr.recalc.sql")


def test_the_checked_out_predicate_follows_the_working_file(qtbot, tmp_path):
    """It is the panel's entry-visibility gate, and a checkout IS the file
    write (§18.2) -- so the answer flips with the file, both ways."""
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    other = DdlObjectRef(kind="function", schema="pr", name="never_touched")
    assert window._ddl_object_is_checked_out(other) is False  # projectless

    ref, _project_dir, ddl_path = _checked_out(window, tmp_path)

    assert window._ddl_object_is_checked_out(ref) is True
    assert window._ddl_object_is_checked_out(other) is False
    ddl_path.unlink()
    assert window._ddl_object_is_checked_out(ref) is False


def test_discard_local_drops_the_file_the_reference_and_the_tab(qtbot, tmp_path, monkeypatch):
    """All four pieces of a checkout go together -- a half-dropped link is
    worse than none."""
    window = _window(qtbot, tmp_path)
    ref, project_dir, ddl_path = _checked_out(window, tmp_path)
    assert window.center_stage.ddl_object_tab(ref.key) is not None
    assert "ddl/pr.recalc.sql" in window._ddl_project_settings.deployed
    _answer_confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    window._on_ddl_discard_local_requested(ref)

    assert not ddl_path.exists()
    assert "ddl/pr.recalc.sql" not in window._ddl_project_settings.deployed
    assert "ddl/pr.recalc.sql" not in load_settings(project_dir).deployed  # persisted
    assert window.center_stage.ddl_object_tab(ref.key) is None
    assert window._ddl_object_is_checked_out(ref) is False


def test_discard_local_throws_away_unsaved_edits_without_a_save_prompt(qtbot, tmp_path, monkeypatch):
    """The confirmation IS the save/discard prompt: offering to Save the file
    about to be deleted would be nonsense."""
    window = _window(qtbot, tmp_path)
    ref, _project_dir, ddl_path = _checked_out(window, tmp_path)
    panel = window.center_stage.ddl_object_tab(ref.key)
    panel.editor.insertPlainText("-- unsaved local work\n")
    assert panel.is_dirty()
    seen = _answer_confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    window._on_ddl_discard_local_requested(ref)

    assert len(seen) == 1  # exactly one dialog, and it is the discard one
    assert seen[0][0] == DISCARD_LOCAL_LABEL
    assert not ddl_path.exists()
    assert window.center_stage.ddl_object_tab(ref.key) is None


def test_discard_local_confirmation_names_the_file_and_absolves_the_database(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    ref, _project_dir, _ddl_path = _checked_out(window, tmp_path)
    seen = _answer_confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    window._on_ddl_discard_local_requested(ref)

    _title, text = seen[0]
    assert "pr.recalc.sql" in text
    assert "pr.recalc()" in text
    assert "NOT touched" in text


def test_declining_the_discard_keeps_everything_and_says_so(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    ref, _project_dir, ddl_path = _checked_out(window, tmp_path)
    _answer_confirm(monkeypatch, QMessageBox.StandardButton.No)

    window._on_ddl_discard_local_requested(ref)

    assert ddl_path.exists()
    assert "ddl/pr.recalc.sql" in window._ddl_project_settings.deployed
    assert window.center_stage.ddl_object_tab(ref.key) is not None
    lines = _project_narration(window)
    assert any("cancelled" in line for line in lines)


def test_discard_local_touches_only_the_clicked_overloads_file(qtbot, tmp_path, monkeypatch):
    """Overloads share the `ddl/` directory and differ only by disambiguation:
    discarding one must not take its sibling with it."""
    from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    one = RoutineInfo(schema="pr", name="fmt", arg_types=["text"])
    two = RoutineInfo(schema="pr", name="fmt", arg_types=["integer"])
    window.ddl_browser_panel._schema = DatabaseSchema(
        routines={one.signature: one, two.signature: two}
    )
    ref_one = DdlObjectRef(kind="function", schema="pr", name="fmt", arg_types=("text",))
    ref_two = DdlObjectRef(
        kind="function", schema="pr", name="fmt", arg_types=("integer",)
    )
    window._edit_ddl_checked_out(ref_one, "-- text overload\n")
    window._edit_ddl_checked_out(ref_two, "-- integer overload\n")
    # `routine_ddl_paths` orders overloads by argument-type tuple, so the
    # integer one keeps the unsuffixed name and the text one is `_1`.
    kept = project_dir / "ddl" / "pr.fmt.sql"
    dropped = project_dir / "ddl" / "pr.fmt_1.sql"
    assert kept.exists() and dropped.exists()
    _answer_confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    window._on_ddl_discard_local_requested(ref_one)

    assert kept.exists()
    assert not dropped.exists()
    assert window._ddl_object_is_checked_out(ref_two) is True
    assert window._ddl_object_is_checked_out(ref_one) is False


def test_discarding_something_not_checked_out_reports_instead_of_raising(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path / "proj")
    ref = DdlObjectRef(kind="function", schema="pr", name="ghost")
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox.question",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("no modal"))),
    )

    window._on_ddl_discard_local_requested(ref)

    lines = _project_narration(window)
    assert any("is not checked out" in line for line in lines)


def test_discard_local_projectless_reports_that_there_is_nothing_to_discard(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox.question",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("no modal"))),
    )

    window._on_ddl_discard_local_requested(
        DdlObjectRef(kind="function", schema="pr", name="recalc")
    )

    lines = _project_narration(window)
    assert any("no project is open" in line for line in lines)


def test_the_explorer_tree_is_wired_to_the_discard_gesture(qtbot, tmp_path, monkeypatch):
    """End to end from the panel signal, so the entry cannot ship emitting into
    nothing (BUG-062's half-shipped shape)."""
    window = _window(qtbot, tmp_path)
    ref, _project_dir, ddl_path = _checked_out(window, tmp_path)
    _answer_confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    window.ddl_browser_panel.discard_local_requested.emit(ref)

    assert not ddl_path.exists()


def test_an_already_open_projectless_tab_keeps_its_save_as_resolver(qtbot, tmp_path, monkeypatch):
    """Documented current behaviour (FQ-024 open question, deliberately left
    as-is): opening a project does NOT re-point an already-open tab's save
    destination. §18.5 carve-out 5's posture -- a live edit's destination is
    never silently moved under it -- so the tab still runs Save As…, and the
    user closes and reopens it to get the object under versioning.
    """
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")
    panel = window.center_stage.ddl_object_tab(ref.key)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    picked = tmp_path / "elsewhere.sql"
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(picked), ""))
    )

    assert panel.resolve_save_path() == picked  # NOT project_dir/ddl/pr.recalc.sql
    assert not (project_dir / "ddl").exists()


# --- .pgtp working copy: linking, no-.bak, Deploy .pgtp (§18.2) -------------
_VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages/>
  </Presentation>
</Project>
"""


def test_opening_a_pgtp_with_a_project_active_links_it_as_the_working_copy(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(source))

    working_copy = project_dir / "source.pgtp"
    assert working_copy.exists()
    assert working_copy.read_text(encoding="utf-8") == _VALID_PGTP
    assert window._current_project_path == str(working_copy)
    linked = window._ddl_project_settings.pgtp
    assert linked.source_path == str(source)
    assert linked.working_copy_path == str(working_copy)


def test_opening_a_second_pgtp_does_not_relink_an_already_linked_project(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    first_source = tmp_path / "first.pgtp"
    first_source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(first_source))
    linked_after_first = window._ddl_project_settings.pgtp

    second_source = tmp_path / "second.pgtp"
    second_source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(second_source))

    assert window._ddl_project_settings.pgtp == linked_after_first
    assert window._current_project_path == str(second_source)  # opened normally, not linked


def test_opening_a_pgtp_with_no_project_open_does_not_link_anything(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(source))

    assert window._ddl_project_settings is None
    assert window._current_project_path == str(source)


def test_saving_the_linked_working_copy_writes_no_bak(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    working_copy = Path(window._current_project_path)

    window._doc_ui.save_project()  # re-save over the same (existing) working copy

    assert not Path(str(working_copy) + ".bak").exists()


def test_reopening_the_same_already_linked_source_stays_on_the_working_copy(qtbot, tmp_path):
    """Once a project's `.pgtp` is linked, re-opening that SAME sshfs-mounted
    source path a second time (e.g. via File > Open / Recent Files pointing
    at the source again) must stay repointed at the working copy -- not
    silently fall back to the source path, which would defeat the whole
    no-`.bak`/working-copy model on the very next Save (§18.2)."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    working_copy_after_first_open = window._current_project_path

    window.open_project_file(str(source))  # re-open the identical source path

    assert window._current_project_path == working_copy_after_first_open


def test_reopening_the_same_linked_source_then_saving_still_writes_no_bak(qtbot, tmp_path):
    """End-to-end consequence of the above: Save after re-opening the same
    already-linked source must still write the working copy with no `.bak`
    sidecar on the source -- the source is the sshfs-mounted truth pushed
    only by the explicit "Deploy .pgtp" gesture, never by an ordinary Save."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    window.open_project_file(str(source))  # re-open the identical source path

    window._doc_ui.save_project()

    assert not Path(str(source) + ".bak").exists()


def test_saving_a_no_project_pgtp_still_writes_bak_as_before(qtbot, tmp_path):
    """§18.2's no-.bak model is scoped to the working copy only -- a plain,
    project-less .pgtp save keeps today's .bak behavior exactly."""
    window = _window(qtbot, tmp_path)
    source = tmp_path / "plain.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))

    window._doc_ui.save_project()

    assert Path(str(source) + ".bak").exists()


# --- BUG-260810173246: a half-link is not a link -----------------------------
def _record_critical_boxes(monkeypatch) -> list[tuple]:
    """Captures `QMessageBox.critical` instead of letting a modal open -- the
    parse-error dialog is exactly what these tests must prove does NOT appear."""
    seen: list[tuple] = []

    def fake_critical(parent, title, text, *args, **kwargs):
        seen.append((title, text))
        return modals.QMessageBox.StandardButton.Ok

    monkeypatch.setattr(modals.QMessageBox, "critical", staticmethod(fake_critical))
    return seen


def _link_then_delete_working_copy(window, tmp_path, project_dir) -> tuple[Path, Path]:
    """Drives the app into the half-link state by the most common real route:
    link a `.pgtp` normally, then delete the working copy behind the app's back
    (also what a moved/copied project folder or an absent mount looks like)."""
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    working_copy = Path(window._current_project_path)
    working_copy.unlink()
    return source, working_copy


def test_a_missing_working_copy_does_not_redirect_the_open_of_the_source(qtbot, tmp_path):
    """The sharp edge: `resolve_pgtp_path` had no existence check, so an open of
    the real, healthy source was redirected at a file that is not there."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source, working_copy = _link_then_delete_working_copy(window, tmp_path, project_dir)

    assert window._ddl_project_settings.pgtp.working_copy_path == str(working_copy)
    assert window._ddl_project_ui.resolve_pgtp_path(str(source)) == str(source)


def test_opening_the_source_with_a_missing_working_copy_loads_it_not_a_parse_error(
    qtbot, tmp_path, monkeypatch
):
    """The misdiagnosis this bug is about: a missing file reported as malformed
    XML. Before the fix the open was redirected at the deleted working copy,
    `load_project`'s OSError came back as a `PgtpParseError`, and the user got a
    "Failed to Open Project" dialog naming a file they never asked to open."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source, working_copy = _link_then_delete_working_copy(window, tmp_path, project_dir)
    boxes = _record_critical_boxes(monkeypatch)

    window.open_project_file(str(source))

    assert boxes == []  # no parse-error dialog, for any file
    assert window._current_project is not None  # the real source really loaded


def test_opening_the_source_with_a_missing_working_copy_repairs_the_link(
    qtbot, tmp_path, monkeypatch
):
    """The recovery §18.2 promises ("attach the file later by opening it") was
    unavailable for exactly this state, because recording a path is what
    disabled the copier. Re-linking to the SAME source is repair, not the silent
    relink `link_pgtp_if_needed` forbids."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source, working_copy = _link_then_delete_working_copy(window, tmp_path, project_dir)
    _record_critical_boxes(monkeypatch)

    window.open_project_file(str(source))

    assert working_copy.exists()  # the copy is back
    assert working_copy.read_text(encoding="utf-8") == _VALID_PGTP
    assert window._current_project_path == str(working_copy)
    relinked = window._ddl_project_settings.pgtp
    assert relinked.source_path == str(source)
    assert relinked.working_copy_path == str(working_copy)
    assert load_settings(project_dir).pgtp == relinked  # persisted, not in-memory only


def test_a_missing_working_copy_is_never_silently_repointed_at_another_source(
    qtbot, tmp_path, monkeypatch
):
    """The half-way rule: the guard treats a missing working copy as unlinked so
    the SAME source can be re-copied -- but a link naming source A is never
    rewritten to source B behind the user's back, whole or not."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source, _working_copy = _link_then_delete_working_copy(window, tmp_path, project_dir)
    broken_link = window._ddl_project_settings.pgtp
    other = tmp_path / "other.pgtp"
    other.write_text(_VALID_PGTP, encoding="utf-8")
    _record_critical_boxes(monkeypatch)

    window.open_project_file(str(other))

    assert window._ddl_project_settings.pgtp == broken_link  # untouched
    assert not (project_dir / "other.pgtp").exists()  # nothing copied in
    assert window._current_project_path == str(other)  # opened plainly


def test_auto_open_falls_back_to_the_folder_scan_when_the_working_copy_is_missing(
    qtbot, tmp_path, monkeypatch
):
    """The `return` used to sit outside the `exists()` branch, so a missing
    working copy silently suppressed the single-candidate rescue and the project
    opened with nothing loaded and no explanation."""
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    leftover = project_dir / "renamed.pgtp"
    leftover.write_text(_VALID_PGTP, encoding="utf-8")
    save_settings(
        project_dir,
        ProjectSettings(
            pgtp=PgtpLink(
                source_path=str(tmp_path / "source.pgtp"),
                working_copy_path=str(project_dir / "gone.pgtp"),
            )
        ),
    )
    window = _window(qtbot, tmp_path)
    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )
    _record_critical_boxes(monkeypatch)

    window._ddl_project_ui.open_project()

    assert window._current_project_path == str(leftover)  # the rescue ran
    texts = window.activity_panel.row_texts()
    assert any(
        "[Project]" in t and "working copy is missing" in t.lower() for t in texts
    )


def test_a_legacy_source_only_link_opens_cleanly_and_self_heals(
    qtbot, tmp_path, monkeypatch
):
    """Migration pin for the on-disk artifact a pre-`caed134` build wrote:
    `source_path` set, the other two fields empty. It must open without a drift
    verdict and without the false "checksum recorded" line, and re-opening the
    source must complete the link."""
    from pgtp_editor.db.ddl_project import save_settings

    source = tmp_path / "legacy.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    project_dir = tmp_path / "proj"
    save_settings(project_dir, ProjectSettings(pgtp=PgtpLink(source_path=str(source))))
    window = _window(qtbot, tmp_path)
    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )
    _record_critical_boxes(monkeypatch)

    window._ddl_project_ui.open_project()

    texts = window.activity_panel.row_texts()
    assert not [t for t in texts if "[Project]" in t and "checksum" in t.lower()]
    assert not [t for t in texts if "[Project]" in t and "unchanged" in t.lower()]

    window.open_project_file(str(source))  # the promised recovery gesture

    healed = window._ddl_project_settings.pgtp
    assert healed.source_path == str(source)
    assert healed.working_copy_path == str(project_dir / "legacy.pgtp")
    assert Path(healed.working_copy_path).exists()


def test_drift_never_claims_a_checksum_it_did_not_write(qtbot, tmp_path, monkeypatch):
    """`report_project_drift` never calls `save_settings`, so its old "Source
    .pgtp checksum recorded" line was false every single time it appeared."""
    from pgtp_editor.db.ddl_project import save_settings

    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    project_dir = tmp_path / "proj"
    working_copy = _existing_working_copy(project_dir)
    save_settings(
        project_dir,
        ProjectSettings(
            pgtp=PgtpLink(
                source_path=str(source),
                working_copy_path=str(working_copy),
                last_known_source_checksum=None,  # never deployed yet
            )
        ),
    )
    window = _window(qtbot, tmp_path)
    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project()

    rows = [t for t in window.activity_panel.row_texts() if "[Project]" in t]
    assert not [t for t in rows if "source .pgtp checksum recorded" in t.lower()]
    assert [t for t in rows if "no .pgtp checksum recorded yet" in t.lower()]
    # And the claim stays honest: nothing was persisted by the open.
    assert load_settings(project_dir).pgtp.last_known_source_checksum is None


def test_deploy_pgtp_pushes_the_working_copy_back_to_the_source(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    working_copy = Path(window._current_project_path)
    edited_text = _VALID_PGTP.replace("<Pages/>", "<Pages><!--edited--></Pages>")
    working_copy.write_text(edited_text, encoding="utf-8")

    window._ddl_project_ui.deploy_pgtp()

    assert source.read_text(encoding="utf-8") == edited_text


def test_deploy_pgtp_updates_the_checksum_so_open_reports_unchanged_next_time(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    working_copy = Path(window._current_project_path)
    edited_text = _VALID_PGTP.replace("<Pages/>", "<Pages><!--edited--></Pages>")
    working_copy.write_text(edited_text, encoding="utf-8")

    window._ddl_project_ui.deploy_pgtp()

    from pgtp_editor.db.ddl_project import content_hash

    assert window._ddl_project_settings.pgtp.last_known_source_checksum == content_hash(edited_text)


def test_deploy_pgtp_with_no_project_is_a_status_message_not_a_crash(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_project_ui.deploy_pgtp()  # must not raise
    assert "no project" in window.statusBar().currentMessage().lower()


def test_deploy_pgtp_with_a_project_but_no_pgtp_linked_is_a_status_message(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)

    window._ddl_project_ui.deploy_pgtp()  # must not raise

    assert "no .pgtp" in window.statusBar().currentMessage().lower()


def test_close_project_offers_deploy_pgtp_when_working_copy_has_pending_changes(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    working_copy = Path(window._current_project_path)
    edited_text = _VALID_PGTP.replace("<Pages/>", "<Pages><!--edited--></Pages>")
    working_copy.write_text(edited_text, encoding="utf-8")
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox.question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )

    window._ddl_project_ui.close_project()

    assert source.read_text(encoding="utf-8") == edited_text  # deployed on close


def test_close_project_declining_the_deploy_prompt_still_closes_without_deploying(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    working_copy = Path(window._current_project_path)
    edited_text = _VALID_PGTP.replace("<Pages/>", "<Pages><!--edited--></Pages>")
    working_copy.write_text(edited_text, encoding="utf-8")
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox.question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )

    window._ddl_project_ui.close_project()

    assert source.read_text(encoding="utf-8") == _VALID_PGTP  # NOT deployed
    assert window._ddl_project_folder is None  # but still closed


def test_close_project_with_no_pending_pgtp_changes_never_prompts(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox.question",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not prompt"))),
    )

    window._ddl_project_ui.close_project()  # unchanged working copy -- nothing pending

    assert window._ddl_project_folder is None


def test_close_project_with_no_pgtp_linked_never_prompts(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox.question",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not prompt"))),
    )

    window._ddl_project_ui.close_project()

    assert window._ddl_project_folder is None


def test_close_project_reminds_about_pending_ddl_deploys(qtbot, tmp_path):
    from pgtp_editor.db.ddl_project import DeployedObject
    from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash="stale-hash")}
    )
    from pgtp_editor.db.ddl_project import save_settings

    save_settings(project_dir, settings)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    (project_dir / "ddl").mkdir()
    (project_dir / "ddl" / "pr.recalc.sql").write_text("-- hand-edited\n", encoding="utf-8")
    window.ddl_browser_panel._schema = DatabaseSchema(
        routines={"pr.recalc()": RoutineInfo(schema="pr", name="recalc", source="live def")}
    )

    window._ddl_project_ui.close_project()

    # FQ-028 routes `[Project]` narration into the Activity Log, and this
    # particular line is emitted DURING the close -- after which FQ-019's
    # project transition replaces the on-screen buffer with the (empty)
    # standalone one. The journal write is unchanged and still the durable
    # record: it lands in the CLOSING project's own file, which the transition
    # flushed.
    from pgtp_editor.db.activity_log import activity_path

    journal = activity_path(project_dir).read_text(encoding="utf-8")
    assert "[Project]" in journal and "pending a batch deploy" in journal


def test_the_close_time_reminder_is_still_readable_after_the_close(qtbot, tmp_path):
    """BUG-042: the reminder used to be told to a panel the same transition
    wiped, so the user was informed at the exact moment they could no longer
    read it. It now ALSO rides the Messages tab, which a project transition
    does not clear."""
    from pgtp_editor.db.ddl_project import DeployedObject, save_settings
    from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash="stale-hash")}
    )
    save_settings(project_dir, settings)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    (project_dir / "ddl").mkdir()
    (project_dir / "ddl" / "pr.recalc.sql").write_text("-- hand-edited\n", encoding="utf-8")
    window.ddl_browser_panel._schema = DatabaseSchema(
        routines={"pr.recalc()": RoutineInfo(schema="pr", name="recalc", source="live def")}
    )

    window._ddl_project_ui.close_project()

    # The project is gone and the journal panel has been swapped to the
    # standalone (empty) store -- and the reminder is STILL on screen.
    assert window._ddl_project_folder is None
    assert not any(
        "pending a batch deploy" in row for row in window.activity_panel.row_texts()
    )
    assert any(
        "pending a batch deploy" in row for row in window.results_panel.row_texts()
    )


def test_ordinary_project_narration_still_goes_only_to_the_journal(qtbot, tmp_path):
    """BUG-042 moved close-time `[Project]` rows only. An open-time line runs
    AFTER `project_changed` (FQ-019's store-switch-first ordering), survives on
    its own, and must not be duplicated onto the Messages tab."""
    window = _window(qtbot, tmp_path)
    window.audit_panel.addItem("[Project] Source .pgtp unchanged since last opened (x).")

    assert any("Source .pgtp unchanged" in row for row in window.activity_panel.row_texts())
    assert window.results_panel.row_texts() == []


def test_close_project_with_no_ddl_explorer_loaded_never_raises(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)

    window._ddl_project_ui.close_project()  # ddl_browser_panel._schema is still None

    assert window._ddl_project_folder is None


def test_deployment_menu_has_deploy_pgtp_action(qtbot, tmp_path):
    """FQ-020 MOVED `Deploy .pgtp` off the File menu's §18.2 project group (five
    -> four) onto the Editor bar's `Deployment` menu: it is meaningful only while
    the Raw XML tab is active, which is exactly what the move expresses."""
    window = _window(qtbot, tmp_path)
    assert find_action(find_top_menu(window, "File"), "Deploy .pgtp") is None
    action = find_action(find_top_menu(window, "Deployment"), "Deploy .pgtp")
    assert action is not None
    assert action.isVisible()  # Raw XML is the tab a fresh window opens on


# --- Window title shows the active project (owner request) -----------------
def test_window_title_shows_no_project_by_default(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert "Project:" not in window.windowTitle()


def test_window_title_shows_the_project_folder_name_once_active(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "my-project"
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(project_dir))

    window._ddl_project_ui.create_project(dialog)

    assert "Project: my-project" in window.windowTitle()


def test_window_title_drops_the_project_on_close(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "my-project"
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(project_dir))
    window._ddl_project_ui.create_project(dialog)

    window._ddl_project_ui.close_project()

    assert "Project:" not in window.windowTitle()


# --- Dialogs default to the active project's folder (owner request) --------
def test_open_pgtp_dialog_defaults_to_the_project_folder(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    captured = {}

    def fake_open(parent, caption, directory, filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getOpenFileName", fake_open)

    window._doc_ui.open_dialog()

    assert captured["directory"] == str(project_dir)


def test_save_project_as_dialog_defaults_to_the_project_folder(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    captured = {}

    def fake_save(parent, caption, directory, filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getSaveFileName", fake_save)

    window._doc_ui.save_as()

    assert captured["directory"] == str(project_dir)


def test_open_pgtp_dialog_defaults_to_empty_with_no_project(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    captured = {}

    def fake_open(parent, caption, directory, filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getOpenFileName", fake_open)

    window._doc_ui.open_dialog()

    assert captured["directory"] == ""


# --- The remaining ~5 threaded call sites (owner request) -------------------
# `_dialog_default_dir()` itself and the two entry points above are already
# covered; these close the gap on the other Open/Save-type dialogs the
# dispatch prompt says were also threaded: Export XSD, Import XSD, the
# Compare/Merge Two Files source+target pickers, Compare This Page/Detail
# With, and the "Save DDL Object" resolver.
def test_export_xsd_dialog_defaults_to_the_project_folder(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.schema_learning.storage import curated_xsd_path

    window = _window(qtbot, tmp_path)
    xsd_path = curated_xsd_path(window._schema_storage_dir)
    xsd_path.parent.mkdir(parents=True, exist_ok=True)
    xsd_path.write_text("<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'/>", encoding="utf-8")
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    captured = {}

    def fake_save(parent, caption, directory, filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getSaveFileName", fake_save)

    window._xsd_ui.export()

    assert captured["directory"] == str(project_dir / xsd_path.name)


def test_import_xsd_dialog_defaults_to_the_project_folder(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    captured = {}

    def fake_open(parent, caption, directory, filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getOpenFileName", fake_open)

    window._xsd_ui.import_()

    assert captured["directory"] == str(project_dir)


def test_compare_merge_two_files_dialogs_default_to_the_project_folder(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    captured = []

    def fake_open(parent, caption, directory, filter):
        captured.append(directory)
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getOpenFileName", fake_open)

    window._diff_ui.compare_two_files()

    # No `_current_project` is open, so the source picker runs first and
    # returning "" (cancelled) short-circuits before the target picker --
    # confirms the source picker defaults to the project folder.
    assert captured == [str(project_dir)]


def test_compare_merge_two_files_target_dialog_also_defaults_to_the_project_folder(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    source_pgtp = tmp_path / "source.pgtp"
    source_pgtp.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source_pgtp))
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    captured = {}

    def fake_open(parent, caption, directory, filter):
        # `_current_project` is already set, so only the target picker runs.
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getOpenFileName", fake_open)

    window._diff_ui.compare_two_files()

    assert captured["directory"] == str(project_dir)


_PGTP_WITH_ONE_PAGE = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_compare_page_with_dialog_defaults_to_the_project_folder(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    source_pgtp = tmp_path / "source.pgtp"
    source_pgtp.write_text(_PGTP_WITH_ONE_PAGE, encoding="utf-8")
    window.open_project_file(str(source_pgtp))
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    page_node = window._current_project.pages[0]
    captured = {}

    def fake_open(parent, caption, directory, filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getOpenFileName", fake_open)

    window._diff_ui.compare_page_with(page_node)

    assert captured["directory"] == str(project_dir)


def test_compare_detail_with_dialog_defaults_to_the_project_folder(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    source_pgtp = tmp_path / "source.pgtp"
    source_pgtp.write_text(_PGTP_WITH_ONE_PAGE, encoding="utf-8")
    window.open_project_file(str(source_pgtp))
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    # The dialog is consulted (and cancelled, below) before the detail_node/
    # source_path are ever used for real resolution, so a page stand-in is
    # sufficient here -- this test only cares about the `directory` arg.
    detail_node = window._current_project.pages[0]
    captured = {}

    def fake_open(parent, caption, directory, filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getOpenFileName", fake_open)

    window._diff_ui.compare_detail_with(detail_node, str(source_pgtp))

    assert captured["directory"] == str(project_dir)


def test_save_ddl_object_dialog_defaults_to_the_project_folder(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    captured = {}

    def fake_save(parent, caption, directory, filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getSaveFileName", fake_save)

    # `_edit_ddl_live` directly, not `_on_ddl_edit_requested`: since FQ-024 a
    # project being open sends the gesture down the checkout branch, which never
    # opens Save As… at all. The Save-As branch can still meet an open project --
    # a tab opened projectless keeps its resolver when a project opens later, and
    # creation always uses it -- and this pins the prefill for exactly that.
    window._edit_ddl_live(ref, "CREATE FUNCTION pr.recalc() ...")
    panel = window.center_stage.ddl_object_tab(ref.key)
    panel.resolve_save_path()

    assert captured["directory"] == str(project_dir / ref.default_file_name)


# --- File > Open's New Project/Open Project/Edit Standalone chooser --------
class _FakeChooserBox:
    """Mirrors `_require_ddl_project`'s test convention for the custom
    QMessageBox-with-addButton chooser (§18.2)."""

    ButtonRole = QMessageBox.ButtonRole
    _clicked_label = "Edit Standalone"

    def __init__(self, parent=None):
        self.buttons = {}

    def setWindowTitle(self, _title):
        pass

    def setText(self, _text):
        pass

    def addButton(self, label, role):
        button = object()
        self.buttons[label] = button
        return button

    def exec(self):
        return None

    def clickedButton(self):
        return self.buttons[self._clicked_label]


def test_open_with_no_project_prompts_and_new_project_choice_creates_one(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(source), ""),
    )

    class _FakeBox(_FakeChooserBox):
        _clicked_label = "New Project…"

    monkeypatch.setattr("pgtp_editor.ui.modals.QMessageBox", _FakeBox)

    window._doc_ui.open_dialog()

    project_dir = tmp_path / "new-proj"
    dialog = window._ddl_project_ui.new_project_dialog
    dialog._folder_edit.setText(str(project_dir))
    dialog.accepted.emit()

    assert window._ddl_project_folder == project_dir
    assert window._current_project_path is not None  # the .pgtp was opened too


def test_open_with_no_project_prompts_and_open_project_choice_links_it(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import ProjectSettings, save_settings

    window = _window(qtbot, tmp_path)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    existing_project = tmp_path / "existing-proj"
    save_settings(existing_project, ProjectSettings())
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(source), ""),
    )

    class _FakeBox(_FakeChooserBox):
        _clicked_label = "Open Project…"

    monkeypatch.setattr("pgtp_editor.ui.modals.QMessageBox", _FakeBox)
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(existing_project),
    )

    window._doc_ui.open_dialog()

    assert window._ddl_project_folder == existing_project
    assert window._current_project_path is not None


def test_open_with_no_project_edit_standalone_choice_opens_plainly(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(source), ""),
    )
    monkeypatch.setattr("pgtp_editor.ui.modals.QMessageBox", _FakeChooserBox)

    window._doc_ui.open_dialog()

    assert window._ddl_project_folder is None
    assert window._current_project_path == str(source)


def test_open_with_a_project_already_active_never_prompts(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "source.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(source), ""),
    )
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not prompt")),
    )

    window._doc_ui.open_dialog()

    assert window._current_project_path is not None


# --- Distinct from the .pgtp project concept --------------------------------
def test_ddl_project_state_is_independent_of_current_project(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))

    window._ddl_project_ui.create_project(dialog)

    assert window._current_project is None  # untouched -- no .pgtp opened
    assert window._ddl_project_folder is not None


# --- BUG-021: the `callable(on_ready)` guard itself ------------------------
def test_open_ddl_project_treats_a_non_callable_on_ready_as_absent(
    qtbot, tmp_path, monkeypatch
):
    """The hardened guard: `checked=False` (or any non-callable) must fall
    through to the plain-Open behaviour — auto-opening the linked `.pgtp` —
    instead of being invoked as a callback."""
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    working_copy = project_dir / "app.pgtp"
    project_dir.mkdir()
    working_copy.write_text(_VALID_PGTP, encoding="utf-8")
    save_settings(
        project_dir,
        ProjectSettings(pgtp=PgtpLink(working_copy_path=str(working_copy))),
    )
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._ddl_project_ui.open_project(on_ready=False)

    assert window._current_project_path == str(working_copy)


def test_new_ddl_project_treats_a_non_callable_on_ready_as_absent(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    created = []
    monkeypatch.setattr(
        DdlProjectController, "create_project",
        lambda self, dialog: created.append(dialog),
    )

    window._ddl_project_ui.new_project(on_ready=False)
    window._ddl_project_ui.new_project_dialog.accepted.emit()   # must not raise

    assert created == [window._ddl_project_ui.new_project_dialog]


def test_a_real_on_ready_callback_still_runs_on_open(qtbot, tmp_path, monkeypatch):
    """The other half of the guard: a genuine callable is still honoured (and
    suppresses the plain-Open auto-open, which is the caller's job then)."""
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    save_settings(project_dir, ProjectSettings())
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )
    ran = []
    window._ddl_project_ui.open_project(on_ready=lambda: ran.append(True))

    assert ran == [True]
    assert window._ddl_project_folder == project_dir


def test_close_project_action_signal_path_closes_the_project(qtbot, tmp_path):
    """The third project action is connected bare; triggering it must close
    the project rather than choke on `triggered`'s `checked` argument."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    window._ddl_project_ui.set_active_project(project_dir, ProjectSettings())
    assert window._ddl_project_ui.close_project_action.isEnabled() is True

    window._ddl_project_ui.close_project_action.trigger()

    assert window._ddl_project_folder is None
    assert window._ddl_project_ui.close_project_action.isEnabled() is False


# --- BUG-034: the `.pgtp`'s connection becomes the project's target ---------
_PGTP_WITH_CONNECTION = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <ConnectionOptions host="dbhost" port="5433" login="erp" database="erpdb" password="xx"/>
  <Presentation>
    <Pages/>
  </Presentation>
</Project>
"""


def test_opening_a_pgtp_imports_its_connection_options_into_the_project_target(
    qtbot, tmp_path
):
    """The reported symptom: Project Settings showed empty target fields for a
    project the app was happily connecting to. Nothing ever copied the
    `.pgtp`'s `<ConnectionOptions>` into `ProjectSettings.target`."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "erp.pgtp"
    source.write_text(_PGTP_WITH_CONNECTION, encoding="utf-8")

    window.open_project_file(str(source))

    target = window._ddl_project_settings.target
    assert (target.host, target.port, target.database, target.user) == (
        "dbhost", "5433", "erpdb", "erp"
    )
    # …and it is PERSISTED, not just held in memory.
    assert load_settings(project_dir).target.host == "dbhost"


def test_the_imported_target_never_carries_a_password_from_the_xml(qtbot, tmp_path):
    """§17: the password is never read from the XML (it is obfuscated there).
    It is prompted for at first connect instead."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "erp.pgtp"
    source.write_text(_PGTP_WITH_CONNECTION, encoding="utf-8")

    window.open_project_file(str(source))

    assert window._ddl_project_settings.target.password == ""


def test_importing_the_target_never_clobbers_one_the_user_already_set(qtbot, tmp_path):
    """"Saved wins" -- the same precedence `seed_params` encodes. A host the
    user corrected in Project Settings must survive reopening the project."""
    from pgtp_editor.db.ddl_project import save_settings

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    edited = ProjectSettings(
        target=ConnectionParams(
            host="127.0.0.1", port="5432", database="mine", user="me", password="pw"
        )
    )
    save_settings(project_dir, edited)
    window._ddl_project_ui.set_active_project(project_dir, edited)
    source = tmp_path / "erp.pgtp"
    source.write_text(_PGTP_WITH_CONNECTION, encoding="utf-8")

    window.open_project_file(str(source))

    assert window._ddl_project_settings.target.host == "127.0.0.1"
    assert window._ddl_project_settings.target.password == "pw"


def test_importing_the_target_never_seeds_the_sandbox(qtbot, tmp_path):
    """§17: `<ConnectionOptions>` is the TARGET. Seeding a sandbox from it is
    how a sandbox ends up pointed at production."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "erp.pgtp"
    source.write_text(_PGTP_WITH_CONNECTION, encoding="utf-8")

    window.open_project_file(str(source))

    assert window._ddl_project_settings.sandbox.host == ""


def test_a_pgtp_without_connection_options_leaves_the_target_alone(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    source = tmp_path / "plain.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(source))

    assert window._ddl_project_settings.target.host == ""


def test_a_pgtp_opened_with_no_project_open_imports_nothing(qtbot, tmp_path):
    """Projectless there is no `settings.json` to import into; the app-level
    `seed_params` path is unchanged there (BUG-024 keeps Connection Setup…
    projectless-only for exactly this split)."""
    window = _window(qtbot, tmp_path)
    source = tmp_path / "erp.pgtp"
    source.write_text(_PGTP_WITH_CONNECTION, encoding="utf-8")

    window.open_project_file(str(source))  # must not raise

    assert window._ddl_project_settings is None


def test_linking_a_pgtp_does_not_reset_the_recorded_sandbox_mode(qtbot, tmp_path):
    """The link step rebuilt `ProjectSettings` field-by-field and silently
    dropped `sandbox_mode`, quietly turning a "with data" project into a
    schema-only one."""
    from pgtp_editor.db.ddl_project import save_settings
    from pgtp_editor.db.sandbox import SandboxMode

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(sandbox_mode=SandboxMode.WITH_DATA)
    save_settings(project_dir, settings)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    source = tmp_path / "erp.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(source))

    assert window._ddl_project_settings.sandbox_mode is SandboxMode.WITH_DATA
    assert load_settings(project_dir).sandbox_mode is SandboxMode.WITH_DATA


# --- BUG-034: one source of truth for "the target connection" ---------------
def test_active_target_params_prefers_the_project_profile_over_app_settings(
    qtbot, tmp_path
):
    from pgtp_editor.db.config import save_connection

    window = _window(qtbot, tmp_path)
    save_connection(
        window._settings,
        ConnectionParams(host="app-level", port="1", database="a", user="a", password="a"),
    )
    window._ddl_project_ui.set_active_project(
        tmp_path / "proj", ProjectSettings(target=ConnectionParams(host="project-level"))
    )

    assert window.active_target_params().host == "project-level"


def test_active_target_params_falls_back_to_seed_params_projectless(qtbot, tmp_path):
    from pgtp_editor.db.config import save_connection

    window = _window(qtbot, tmp_path)
    save_connection(
        window._settings,
        ConnectionParams(host="app-level", port="1", database="a", user="a", password="a"),
    )

    assert window.active_target_params().host == "app-level"


def test_a_fresh_no_target_project_reads_as_not_configured(qtbot, tmp_path):
    """FQ-007: New Project collects no target at all, so an empty target is
    legitimate -- and must read as "not configured" rather than be silently
    backfilled from the app-level connection."""
    from pgtp_editor.db.config import save_connection

    window = _window(qtbot, tmp_path)
    save_connection(
        window._settings,
        ConnectionParams(host="app-level", port="1", database="a", user="a", password="a"),
    )
    window._ddl_project_ui.set_active_project(tmp_path / "proj", ProjectSettings())

    target = window.active_target_params()
    assert target.host == ""  # NOT backfilled from the app-level connection
    assert window._target_is_configured(target) is False
    assert window._connection_summary_for(target) == "Not configured."


def test_the_target_password_is_prompted_once_and_persisted(qtbot, tmp_path):
    """The report: "password is requested, then saved in the json"."""
    from pgtp_editor.db.ddl_project import save_settings

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        target=ConnectionParams(host="dbhost", port="5433", database="erpdb", user="erp")
    )
    save_settings(project_dir, settings)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    asked = []
    window._prompt_target_password = lambda params: asked.append(params) or "s3cret"

    first = window._target_params_for_fetch()

    assert first.password == "s3cret"
    assert load_settings(project_dir).target.password == "s3cret"
    # Asked ONCE: the persisted password short-circuits every later gesture.
    assert window._target_params_for_fetch().password == "s3cret"
    assert len(asked) == 1


def test_cancelling_the_password_prompt_persists_nothing(qtbot, tmp_path):
    from pgtp_editor.db.ddl_project import save_settings

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(target=ConnectionParams(host="dbhost", user="erp"))
    save_settings(project_dir, settings)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    window._prompt_target_password = lambda params: None

    params = window._target_params_for_fetch()

    assert params.password == ""
    assert load_settings(project_dir).target.password == ""


def test_no_password_prompt_projectless_or_without_a_host(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    asked = []
    window._prompt_target_password = lambda params: asked.append(params) or "x"

    window._target_params_for_fetch()  # projectless
    window._ddl_project_ui.set_active_project(tmp_path / "proj", ProjectSettings())
    window._target_params_for_fetch()  # project open, no host configured

    assert asked == []


# --- FQ-035: creation records the attached `.pgtp` and its quality target ----
_ATTACHED_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <ConnectionOptions host="quality" port="1111" login="app_user" database="erp" password="xx"/>
  <ScriptConnectionOptions host="script" port="5579" login="s" database="s" password="xx"/>
  <Presentation>
    <Pages/>
  </Presentation>
</Project>
"""


def _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch):
    """A New Project dialog with a folder and an attached `.pgtp`. The controller
    now probes a configured target on `set_active_project`, so the real
    `test_connection` is stubbed out -- no test may reach a network."""
    monkeypatch.setattr(
        "pgtp_editor.ui.ddl_project_controller.db_test_connection",
        lambda params: (True, "Connected."),
    )
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(project_dir))
    dialog.set_pgtp_path(str(source))
    return dialog


def test_creating_a_project_records_the_attached_pgtp_source_path(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)

    window._ddl_project_ui.create_project(dialog)

    link = load_settings(project_dir).pgtp
    assert link.source_path == str(source)


def test_creating_a_project_records_the_quality_target_from_the_attached_pgtp(
    qtbot, tmp_path, monkeypatch
):
    """The point of FQ-035: `target` stops being an empty default that only
    first-open fills in."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)
    dialog._quality_password_edit.setText("secret")

    window._ddl_project_ui.create_project(dialog)

    target = load_settings(project_dir).target
    assert (target.host, target.port, target.database, target.user, target.password) == (
        "quality", "1111", "erp", "app_user", "secret",
    )


def test_creating_a_project_with_a_pgtp_leaves_the_sandbox_untouched(
    qtbot, tmp_path, monkeypatch
):
    """Never seed the sandbox from `<ConnectionOptions>` -- that is how a sandbox
    ends up pointed at production."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)

    window._ddl_project_ui.create_project(dialog)

    assert load_settings(project_dir).sandbox == ConnectionParams()


def test_creating_a_project_without_a_pgtp_is_byte_for_byte_todays_behaviour(
    qtbot, tmp_path
):
    """Ignoring the optional field must change nothing: no link, no target."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(project_dir))

    window._ddl_project_ui.create_project(dialog)

    loaded = load_settings(project_dir)
    assert loaded.pgtp == PgtpLink()
    assert loaded.target == ConnectionParams()


def test_creation_checks_the_pgtp_out_into_the_project_folder(
    qtbot, tmp_path, monkeypatch
):
    """DEC-260810134914: the copy happens AT ACCEPT, so creation produces the
    same three-field link the open-time path produces -- never a recorded
    identity pointing at nothing."""
    from pgtp_editor.db.ddl_project import content_hash

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)

    window._ddl_project_ui.create_project(dialog)

    working_copy = project_dir / "erp.pgtp"
    link = load_settings(project_dir).pgtp
    assert link.source_path == str(source)
    assert link.working_copy_path == str(working_copy)
    assert link.last_known_source_checksum == content_hash(_ATTACHED_PGTP)
    assert working_copy.read_text(encoding="utf-8") == _ATTACHED_PGTP


def test_creation_and_the_open_time_linker_share_ONE_copier(
    qtbot, tmp_path, monkeypatch
):
    """§18.2 requires one definition of linking. Both entry points call
    `check_out_pgtp`, so a stub on it starves both."""
    from pgtp_editor.ui import ddl_project_controller as controller_module

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)
    calls = []
    real = controller_module.check_out_pgtp
    monkeypatch.setattr(
        controller_module, "check_out_pgtp",
        lambda folder, path: calls.append((folder, path)) or real(folder, path),
    )

    window._ddl_project_ui.create_project(dialog)

    assert calls == [(project_dir, source)]
    # The open-time entry point is now a no-op for this project (the guard), and
    # opening the source resolves straight to the working copy.
    window.open_project_file(str(source))
    assert calls == [(project_dir, source)]
    assert window._current_project_path == str(project_dir / "erp.pgtp")


def test_an_unreadable_source_costs_the_link_not_the_project(
    qtbot, tmp_path, monkeypatch
):
    """The creation path deliberately does NOT inherit the open-time copier's
    silent no-op: the project is created with NO link, the failure is reported,
    and the file can still be attached later by opening it."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "gone.pgtp"  # never written -- unreadable
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)
    before = len(window.activity_panel.row_texts())

    window._ddl_project_ui.create_project(dialog)

    assert window._ddl_project_folder == project_dir  # the project still exists
    assert load_settings(project_dir).pgtp == PgtpLink()  # no half-link at all
    rows = _journal_rows(window, before)
    assert any("Could not copy the attached .pgtp" in row for row in rows)

    # ... and the open-time path is still free to link it once it is readable.
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    window.open_project_file(str(source))
    assert load_settings(project_dir).pgtp.working_copy_path == str(
        project_dir / "gone.pgtp"
    )


def test_an_existing_destination_is_adopted_never_overwritten(
    qtbot, tmp_path, monkeypatch
):
    """Matched, not tightened, from the open-time copier: an existing file at the
    destination is left alone. The link is still whole -- three fields, all
    true -- so no forbidden state is reachable this way."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "erp.pgtp").write_text("<Project>local edits</Project>", encoding="utf-8")
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)

    window._ddl_project_ui.create_project(dialog)

    assert (project_dir / "erp.pgtp").read_text(encoding="utf-8") == (
        "<Project>local edits</Project>"
    )
    link = load_settings(project_dir).pgtp
    assert link.working_copy_path == str(project_dir / "erp.pgtp")
    assert link.last_known_source_checksum is not None


def test_opening_a_project_created_with_a_pgtp_reports_no_false_drift(
    qtbot, tmp_path, monkeypatch
):
    """`report_project_drift` keys on `source_path` alone -- with the checksum
    now written at creation it reports "unchanged", not phantom drift."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)
    window._ddl_project_ui.create_project(dialog)
    before = len(window.activity_panel.row_texts())

    settings = load_settings(project_dir)
    window._ddl_project_ui.report_project_drift(project_dir, settings)

    rows = _journal_rows(window, before)
    assert any("unchanged since last opened" in row for row in rows)


def test_auto_open_loads_the_working_copy_written_at_creation(
    qtbot, tmp_path, monkeypatch
):
    """`auto_open_linked_pgtp` returns early on a set `working_copy_path`; the
    file it points at now always exists, so the early return opens something."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)
    window._ddl_project_ui.create_project(dialog)

    window._ddl_project_ui.auto_open_linked_pgtp(project_dir, load_settings(project_dir))

    assert window._current_project_path == str(project_dir / "erp.pgtp")


# --- BUG-260810174459: New Project auto-opens the checked-out working copy ----
def _accept_new_project(window, tmp_path, monkeypatch, *, source=None, on_ready=None):
    """Drive the real File ▸ New Project path end to end: `new_project()` builds
    the dialog and connects its accepted handler, so the dialog the test fills in
    has to be THAT one -- a separately constructed dialog is connected to nothing.
    Returns the project folder."""
    monkeypatch.setattr(
        "pgtp_editor.ui.ddl_project_controller.db_test_connection",
        lambda params: (True, "Connected."),
    )
    project_dir = tmp_path / "proj"
    window._ddl_project_ui.new_project(on_ready=on_ready)
    dialog = window._ddl_project_ui.new_project_dialog
    dialog._folder_edit.setText(str(project_dir))
    if source is not None:
        dialog.set_pgtp_path(str(source))
    dialog.accepted.emit()
    return project_dir


def test_creating_a_project_with_an_attached_pgtp_opens_it(
    qtbot, tmp_path, monkeypatch
):
    """The reported defect: the file was copied and linked, and the editor stayed
    empty. No manual `auto_open_linked_pgtp` call here -- that is the point."""
    window = _window(qtbot, tmp_path)
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")

    project_dir = _accept_new_project(window, tmp_path, monkeypatch, source=source)

    assert window._current_project_path == str(project_dir / "erp.pgtp")


def test_create_with_an_on_ready_does_not_auto_open_the_linked_copy(
    qtbot, tmp_path, monkeypatch
):
    """The `require_project` shape: the caller has its own `.pgtp` to load next,
    so auto-opening here too would be BUG-021's silent double load."""
    window = _window(qtbot, tmp_path)
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    opened = []
    window._ddl_project_ui._open_pgtp_file = lambda path: opened.append(path)
    ready = []

    _accept_new_project(
        window, tmp_path, monkeypatch,
        source=source, on_ready=lambda: ready.append(True),
    )

    assert ready == [True]
    assert opened == []


def test_creating_a_project_without_a_pgtp_opens_nothing(qtbot, tmp_path, monkeypatch):
    """A sandbox-only project has nothing to open, and the folder scan finds no
    candidate -- silence, not an error."""
    window = _window(qtbot, tmp_path)
    opened = []
    window._ddl_project_ui._open_pgtp_file = lambda path: opened.append(path)

    _accept_new_project(window, tmp_path, monkeypatch)

    assert opened == []


# --- DEC-260810134915: no gate, one accept-time advisory ----------------------
def _journal_rows(window, before: int) -> list[str]:
    """`[Project]` narration is routed to the Activity Log, not the Messages
    tab -- so that is where a creation-time notice has to be looked for."""
    return list(window.activity_panel.row_texts()[before:])


def test_a_blank_quality_connection_is_reported_once_and_never_gates(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)
    dialog._quality_host_edit.setText("")
    before = len(window.activity_panel.row_texts())

    window._ddl_project_ui.create_project(dialog)

    assert window._ddl_project_folder == project_dir  # accepted, never refused
    rows = _journal_rows(window, before)
    matches = [row for row in rows if "no quality (target) server" in row]
    assert len(matches) == 1
    assert "[Project]" in matches[0]  # journalled with its provenance prefix


def test_an_untested_quality_connection_is_reported_once(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)
    before = len(window.activity_panel.row_texts())

    window._ddl_project_ui.create_project(dialog)

    rows = _journal_rows(window, before)
    assert len([row for row in rows if "was never tested" in row]) == 1


def test_a_tested_quality_connection_says_nothing_and_neither_does_no_pgtp(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    tested_dir = tmp_path / "tested"
    dialog = _new_project_dialog_with_pgtp(qtbot, window, tested_dir, source, monkeypatch)
    dialog._run_async = lambda work, on_result, on_error=None: on_result(work())
    dialog._tester = lambda params: (True, "Connected.")
    dialog.test_quality()
    before = len(window.activity_panel.row_texts())

    window._ddl_project_ui.create_project(dialog)

    assert not [
        row for row in _journal_rows(window, before)
        if "quality (target)" in row
    ]

    # And a project with no `.pgtp` at all is created as silently as before.
    plain_dir = tmp_path / "plain"
    plain = NewProjectDialog(parent=window)
    qtbot.addWidget(plain)
    plain._folder_edit.setText(str(plain_dir))
    before = len(window.activity_panel.row_texts())

    window._ddl_project_ui.create_project(plain)

    assert _journal_rows(window, before) == []


def test_a_target_supplied_at_creation_is_not_overwritten_on_first_open(
    qtbot, tmp_path, monkeypatch
):
    """`_import_pgtp_connection_into_target` fires only when `target.host` is
    still empty. That guard is vacuous at creation today and becomes
    load-bearing the moment FQ-035 ships -- so it must not be relaxed."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    source = tmp_path / "erp.pgtp"
    source.write_text(_ATTACHED_PGTP, encoding="utf-8")
    dialog = _new_project_dialog_with_pgtp(qtbot, window, project_dir, source, monkeypatch)
    dialog._quality_host_edit.setText("corrected-host")
    dialog._quality_password_edit.setText("secret")

    window._ddl_project_ui.create_project(dialog)
    window.open_project_file(str(source))

    target = load_settings(project_dir).target
    assert target.host == "corrected-host"
    assert target.password == "secret"
