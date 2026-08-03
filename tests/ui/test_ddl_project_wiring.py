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


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _window(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    return window


# --- Menu ---------------------------------------------------------------
def test_database_menu_has_new_open_close_project_actions(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    menu = find_top_menu(window, "Database")
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
    import pgtp_editor.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._open_ddl_project()

    assert window._ddl_project_settings.name == "Prior work"
    assert window._ddl_project_folder == project_dir
    assert window._close_ddl_project_action.isEnabled() is True


def test_open_ddl_project_cancelled_picker_does_nothing(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    import pgtp_editor.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: ""),  # Cancel
    )

    window._open_ddl_project()

    assert window._ddl_project_folder is None
    assert window._close_ddl_project_action.isEnabled() is False


def test_open_ddl_project_on_a_brand_new_folder_gets_default_settings(qtbot, tmp_path, monkeypatch):
    project_dir = tmp_path / "brand-new"
    project_dir.mkdir()
    window = _window(qtbot, tmp_path)
    import pgtp_editor.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(project_dir)),
    )

    window._open_ddl_project()

    assert window._ddl_project_settings == ProjectSettings()


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
    import pgtp_editor.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getExistingDirectory",
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
    import pgtp_editor.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getExistingDirectory",
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
    import pgtp_editor.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getExistingDirectory",
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
    import pgtp_editor.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getExistingDirectory",
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
    menu = find_top_menu(window, "Database")
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

    monkeypatch.setattr("pgtp_editor.ui.main_window.QMessageBox", _FakeBox)
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

    monkeypatch.setattr("pgtp_editor.ui.main_window.QMessageBox", _FakeBox)
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
        "pgtp_editor.ui.main_window.QMessageBox",
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

    monkeypatch.setattr("pgtp_editor.ui.main_window.QMessageBox", _FakeBox)

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
        "pgtp_editor.ui.main_window.QMessageBox.question",
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
        "pgtp_editor.ui.main_window.QMessageBox.question",
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
        "pgtp_editor.ui.main_window.QMessageBox.question",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not prompt"))),
    )

    window._close_ddl_project()  # unchanged working copy -- nothing pending

    assert window._ddl_project_folder is None


def test_close_project_with_no_pgtp_linked_never_prompts(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    project_dir = tmp_path / "proj"
    _open_project(window, project_dir)
    monkeypatch.setattr(
        "pgtp_editor.ui.main_window.QMessageBox.question",
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
    menu = find_top_menu(window, "Database")
    assert find_action(menu, "Deploy .pgtp") is not None


# --- Distinct from the .pgtp project concept --------------------------------
def test_ddl_project_state_is_independent_of_current_project(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewProjectDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))

    window._create_ddl_project(dialog)

    assert window._current_project is None  # untouched -- no .pgtp opened
    assert window._ddl_project_folder is not None
