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
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.new_project_dialog import NewProjectDialog
from pgtp_editor.ui.project_settings_dialog import ProjectSettingsDialog

from ._menu_helpers import find_action, find_top_menu
from ._sandbox_stubs import stub_sandbox_provisioning
from pgtp_editor.ui import modals


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _window(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
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
    assert window._close_ddl_project_action.isEnabled() is False


# --- New Project ----------------------------------------------------------
def test_new_ddl_project_creates_the_folder_and_settings_file(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "my-project"
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("ERP overhaul")
    dialog._folder_edit.setText(str(project_dir))
    dialog._sandbox_host_edit.setText("localhost")

    window._create_ddl_project(dialog)

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

    window._create_ddl_project(dialog)

    assert window._ddl_project_folder == project_dir
    assert window._ddl_project_settings is not None
    assert window._close_ddl_project_action.isEnabled() is True


def test_new_ddl_project_captures_git_config_inert(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "my-project"
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(project_dir))
    dialog._git_server_edit.setText("git.example.com")
    dialog._git_branch_edit.setText("feature/x")

    window._create_ddl_project(dialog)

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

    window._create_ddl_project(dialog)

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

    window._open_ddl_project()

    assert window._ddl_project_settings.name == "Prior work"
    assert window._ddl_project_folder == project_dir
    assert window._close_ddl_project_action.isEnabled() is True


def test_open_ddl_project_cancelled_picker_does_nothing(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: ""),  # Cancel
    )

    window._open_ddl_project()

    assert window._ddl_project_folder is None
    assert window._close_ddl_project_action.isEnabled() is False


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

    window._open_ddl_project()

    assert window._ddl_project_folder is None
    assert window._ddl_project_settings is None
    assert window._close_ddl_project_action.isEnabled() is False


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

    window._open_ddl_project()

    assert window._ddl_project_settings == ProjectSettings()
    assert window._ddl_project_folder == project_dir
    assert window._close_ddl_project_action.isEnabled() is True


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

    window._open_ddl_project()

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

    window._open_ddl_project()

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
    """BUG-021, parallel latent defect: `_new_ddl_project` is wired the same
    way, so the dialog's accepted handler would call `False()` (TypeError)."""
    window = _window(qtbot, tmp_path)
    created = []
    monkeypatch.setattr(
        MainWindow, "_create_ddl_project", lambda self, dialog: created.append(dialog)
    )

    action = find_action(find_top_menu(window, "File"), "New Project…")
    assert action is not None
    action.trigger()

    dialog = window._new_project_dialog
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

    window._open_ddl_project()  # must not raise

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

    window._open_ddl_project()

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

    window._open_ddl_project()

    assert window._current_project is None  # never guessed which one
    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any(
        t.startswith("[Project]") and "multiple" in t.lower() for t in texts
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
    window._open_ddl_project(on_ready=lambda: window.open_project_file(str(source)))

    # Only the caller's own path was opened -- never the linked working copy.
    assert opened == [str(source)]


# --- .pgtp checksum drift report on open ------------------------------------
def test_open_reports_unchanged_source_pgtp(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import content_hash, save_settings

    source = tmp_path / "source.pgtp"
    source.write_text("<Project/>", encoding="utf-8")
    project_dir = tmp_path / "proj"
    save_settings(
        project_dir,
        ProjectSettings(
            pgtp=PgtpLink(
                source_path=str(source),
                last_known_source_checksum=content_hash("<Project/>"),
            )
        ),
    )
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._open_ddl_project()

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any("unchanged" in t.lower() for t in texts if t.startswith("[Project]"))


def test_open_reports_drifted_source_pgtp(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import content_hash, save_settings

    source = tmp_path / "source.pgtp"
    source.write_text("<Project><Changed/></Project>", encoding="utf-8")
    project_dir = tmp_path / "proj"
    save_settings(
        project_dir,
        ProjectSettings(
            pgtp=PgtpLink(
                source_path=str(source),
                last_known_source_checksum=content_hash("<Project/>"),  # stale
            )
        ),
    )
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._open_ddl_project()

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any(
        t.startswith("[Project]") and "changed" in t.lower() for t in texts
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

    window._open_ddl_project()

    assert window.audit_panel.count() == before


def test_open_reports_unreadable_source_pgtp_gracefully(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.db.ddl_project import save_settings

    project_dir = tmp_path / "proj"
    save_settings(
        project_dir,
        ProjectSettings(pgtp=PgtpLink(source_path=str(tmp_path / "does-not-exist.pgtp"))),
    )
    window = _window(qtbot, tmp_path)

    monkeypatch.setattr(
        modals.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._open_ddl_project()  # must not raise

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any("could not read" in t.lower() for t in texts)


# --- Close Project -----------------------------------------------------------
def test_close_ddl_project_clears_state_and_disables_action(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    window._create_ddl_project(dialog)

    window._close_ddl_project()

    assert window._ddl_project_folder is None
    assert window._ddl_project_settings is None
    assert window._close_ddl_project_action.isEnabled() is False


def test_close_ddl_project_when_none_open_is_a_no_op(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._close_ddl_project()  # must not raise
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
    window._create_ddl_project(dialog)

    window._open_ddl_project_settings()

    assert isinstance(window._project_settings_dialog, ProjectSettingsDialog)
    assert window._project_settings_dialog.settings() == window._ddl_project_settings


def test_saving_project_settings_writes_to_disk_and_updates_state(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "p"
    new_project_dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(new_project_dialog)
    new_project_dialog._folder_edit.setText(str(project_dir))
    window._create_ddl_project(new_project_dialog)

    window._open_ddl_project_settings()
    settings_dialog = window._project_settings_dialog
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

    window._require_ddl_project(lambda: got.append(True))

    # The Create… path opened NewProjectDialog; complete it as the user would.
    dialog = window._new_project_dialog
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

    window._require_ddl_project(lambda: got.append(True))

    assert got == []
    assert window._ddl_project_folder is None


def test_project_required_skips_the_dialog_entirely_when_already_open(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    window._create_ddl_project(dialog)
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not prompt")),
    )
    got = []

    window._require_ddl_project(lambda: got.append(True))

    assert got == [True]


# --- Check Out for Versioning (§18.2) ---------------------------------------
def _open_project(window, folder):
    from pgtp_editor.db.ddl_project import ProjectSettings, save_settings

    save_settings(folder, ProjectSettings())
    window._set_active_ddl_project(folder, ProjectSettings())


def test_checkout_seeds_the_file_when_absent(qtbot, tmp_path):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

    window._checkout_and_edit(ref, "CREATE FUNCTION pr.recalc() ...")

    ddl_path = project_dir / "ddl" / "pr.recalc.sql"
    assert ddl_path.read_text(encoding="utf-8") == "CREATE FUNCTION pr.recalc() ..."


def test_checkout_opens_a_tab_pointed_at_the_checked_out_file(qtbot, tmp_path):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

    window._checkout_and_edit(ref, "CREATE FUNCTION pr.recalc() ...")

    ddl_path = (project_dir / "ddl" / "pr.recalc.sql").resolve()
    panel = window.center_stage.ddl_object_tab(str(ddl_path))
    assert panel is not None
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

    window._checkout_and_edit(ref, "CREATE FUNCTION pr.recalc() ... -- stale live def")

    resolved_key = str(ddl_path.resolve())
    panel = window.center_stage.ddl_object_tab(resolved_key)
    assert panel.text() == "-- hand-edited local truth\n"
    assert ddl_path.read_text(encoding="utf-8") == "-- hand-edited local truth\n"  # untouched


def test_re_invoking_checkout_focuses_the_existing_tab(qtbot, tmp_path):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    window._checkout_and_edit(ref, "text")
    ddl_path = (project_dir / "ddl" / "pr.recalc.sql").resolve()
    first = window.center_stage.ddl_object_tab(str(ddl_path))
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    window._checkout_and_edit(ref, "ignored -- already checked out")

    second = window.center_stage.ddl_object_tab(str(ddl_path))
    assert second is first
    assert window.center_stage.currentWidget() is first


def test_checkout_of_a_trigger_uses_the_table_qualified_path(qtbot, tmp_path):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    ref = DdlObjectRef(kind="trigger", schema="pr", name="trg_audit", table="orders")

    window._checkout_and_edit(ref, "CREATE TRIGGER trg_audit ...")

    ddl_path = project_dir / "ddl" / "pr.orders.trg_audit.sql"
    assert ddl_path.exists()


def test_checkout_requires_a_project_and_offers_create_open_cancel(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

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

    window._on_ddl_checkout_requested(ref, "text")  # must not raise, no project created

    assert window._ddl_project_folder is None


def test_checkout_reports_drift_from_the_last_deployed_reference(qtbot, tmp_path):
    from pgtp_editor.db.ddl_project import DeployedObject, ProjectSettings, save_settings
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash="stale-hash")}
    )
    save_settings(project_dir, settings)
    window._set_active_ddl_project(project_dir, settings)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")

    window._checkout_and_edit(ref, "CREATE FUNCTION pr.recalc() ... -- drifted")

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any(t.startswith("[Project]") and "drifted" in t.lower() for t in texts)


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
    window._set_active_ddl_project(project_dir, settings)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    before = window.audit_panel.count()

    window._checkout_and_edit(ref, live_source)

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

    window._checkout_and_edit(ref, "CREATE FUNCTION pr.fmt(a text) ...")

    # "text" sorts after "integer" -- the second overload, so it gets _1.
    assert (project_dir / "ddl" / "pr.fmt_1.sql").exists()


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

    window._save_project()  # re-save over the same (existing) working copy

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

    window._save_project()

    assert not Path(str(source) + ".bak").exists()


def test_saving_a_no_project_pgtp_still_writes_bak_as_before(qtbot, tmp_path):
    """§18.2's no-.bak model is scoped to the working copy only -- a plain,
    project-less .pgtp save keeps today's .bak behavior exactly."""
    window = _window(qtbot, tmp_path)
    source = tmp_path / "plain.pgtp"
    source.write_text(_VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(source))

    window._save_project()

    assert Path(str(source) + ".bak").exists()


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

    window._deploy_pgtp()

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

    window._deploy_pgtp()

    from pgtp_editor.db.ddl_project import content_hash

    assert window._ddl_project_settings.pgtp.last_known_source_checksum == content_hash(edited_text)


def test_deploy_pgtp_with_no_project_is_a_status_message_not_a_crash(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._deploy_pgtp()  # must not raise
    assert "no project" in window.statusBar().currentMessage().lower()


def test_deploy_pgtp_with_a_project_but_no_pgtp_linked_is_a_status_message(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)

    window._deploy_pgtp()  # must not raise

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

    window._close_ddl_project()

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

    window._close_ddl_project()

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

    window._close_ddl_project()  # unchanged working copy -- nothing pending

    assert window._ddl_project_folder is None


def test_close_project_with_no_pgtp_linked_never_prompts(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    monkeypatch.setattr(
        "pgtp_editor.ui.modals.QMessageBox.question",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not prompt"))),
    )

    window._close_ddl_project()

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
    window._set_active_ddl_project(project_dir, settings)
    (project_dir / "ddl").mkdir()
    (project_dir / "ddl" / "pr.recalc.sql").write_text("-- hand-edited\n", encoding="utf-8")
    window.ddl_browser_panel._schema = DatabaseSchema(
        routines={"pr.recalc()": RoutineInfo(schema="pr", name="recalc", source="live def")}
    )

    window._close_ddl_project()

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert any(
        t.startswith("[Project]") and "pending a batch deploy" in t for t in texts
    )


def test_close_project_with_no_ddl_explorer_loaded_never_raises(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)

    window._close_ddl_project()  # ddl_browser_panel._schema is still None

    assert window._ddl_project_folder is None


def test_database_menu_has_deploy_pgtp_action(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    menu = find_top_menu(window, "File")
    assert find_action(menu, "Deploy .pgtp") is not None


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

    window._create_ddl_project(dialog)

    assert "Project: my-project" in window.windowTitle()


def test_window_title_drops_the_project_on_close(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "my-project"
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(project_dir))
    window._create_ddl_project(dialog)

    window._close_ddl_project()

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

    window._open_project()

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

    window._save_project_as()

    assert captured["directory"] == str(project_dir)


def test_open_pgtp_dialog_defaults_to_empty_with_no_project(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    captured = {}

    def fake_open(parent, caption, directory, filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr("pgtp_editor.ui.modals.QFileDialog.getOpenFileName", fake_open)

    window._open_project()

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

    window._on_ddl_edit_requested(ref, "CREATE FUNCTION pr.recalc() ...")
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

    window._open_project()

    project_dir = tmp_path / "new-proj"
    dialog = window._new_project_dialog
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

    window._open_project()

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

    window._open_project()

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

    window._open_project()

    assert window._current_project_path is not None


# --- Distinct from the .pgtp project concept --------------------------------
def test_ddl_project_state_is_independent_of_current_project(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))

    window._create_ddl_project(dialog)

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

    window._open_ddl_project(on_ready=False)

    assert window._current_project_path == str(working_copy)


def test_new_ddl_project_treats_a_non_callable_on_ready_as_absent(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    created = []
    monkeypatch.setattr(
        MainWindow, "_create_ddl_project", lambda self, dialog: created.append(dialog)
    )

    window._new_ddl_project(on_ready=False)
    window._new_project_dialog.accepted.emit()   # must not raise

    assert created == [window._new_project_dialog]


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
    window._open_ddl_project(on_ready=lambda: ran.append(True))

    assert ran == [True]
    assert window._ddl_project_folder == project_dir


def test_close_project_action_signal_path_closes_the_project(qtbot, tmp_path):
    """The third project action is connected bare; triggering it must close
    the project rather than choke on `triggered`'s `checked` argument."""
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    window._set_active_ddl_project(project_dir, ProjectSettings())
    assert window._close_ddl_project_action.isEnabled() is True

    window._close_ddl_project_action.trigger()

    assert window._ddl_project_folder is None
    assert window._close_ddl_project_action.isEnabled() is False


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
    window._set_active_ddl_project(project_dir, edited)
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
    window._set_active_ddl_project(project_dir, settings)
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
    window._set_active_ddl_project(
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
    window._set_active_ddl_project(tmp_path / "proj", ProjectSettings())

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
    window._set_active_ddl_project(project_dir, settings)
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
    window._set_active_ddl_project(project_dir, settings)
    window._prompt_target_password = lambda params: None

    params = window._target_params_for_fetch()

    assert params.password == ""
    assert load_settings(project_dir).target.password == ""


def test_no_password_prompt_projectless_or_without_a_host(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    asked = []
    window._prompt_target_password = lambda params: asked.append(params) or "x"

    window._target_params_for_fetch()  # projectless
    window._set_active_ddl_project(tmp_path / "proj", ProjectSettings())
    window._target_params_for_fetch()  # project open, no host configured

    assert asked == []
