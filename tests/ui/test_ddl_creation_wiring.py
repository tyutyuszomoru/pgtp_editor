# tests/ui/test_ddl_creation_wiring.py
"""MainWindow wiring for FQ-002 (creating a brand-new trigger/function/
procedure from the DDL Explorer) and for §18.8's Project Status entry point.

No live DB and no modal calls: both creation dialogs are shown non-modally,
and the tab-opening path is driven through the same seam Edit… uses.
"""
from PySide6.QtCore import QSettings

from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo, TableInfo
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.new_routine_dialog import NewRoutineDialog
from pgtp_editor.ui.new_trigger_dialog import NewTriggerDialog

from ._menu_helpers import action_labels, find_action, find_top_menu


def _schema():
    return DatabaseSchema(
        tables={"pr.orders": TableInfo(name="pr.orders", kind="table", columns=[])},
        routines={
            "pr.audit_fn()": RoutineInfo(
                schema="pr", name="audit_fn", arg_types=[], return_type="trigger",
                language="plpgsql", source="...", kind="function",
            ),
            "pr.total(integer)": RoutineInfo(
                schema="pr", name="total", arg_types=["integer"], return_type="numeric",
                language="plpgsql", source="...", kind="function",
            ),
        },
    )


def _window(qtbot, tmp_path):
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    window._ddl_schema = _schema()
    return window


# --- the trigger-function candidate filter ---------------------------------
def test_only_trigger_returning_routines_are_offered_as_trigger_functions(qtbot, tmp_path):
    """A trigger can only attach to a function that RETURNS trigger, so a
    numeric-returning routine must not appear in the chooser."""
    window = _window(qtbot, tmp_path)

    assert window._trigger_function_candidates() == ["pr.audit_fn"]


def test_trigger_function_candidates_without_a_schema_is_empty_not_an_error(qtbot, tmp_path):
    """Right-clicking before any Explorer fetch must not raise."""
    window = _window(qtbot, tmp_path)
    window._ddl_schema = None

    assert window._trigger_function_candidates() == []


# --- ref construction ------------------------------------------------------
def test_created_trigger_ref_takes_its_schema_from_the_table(qtbot, tmp_path):
    """pg_trigger gives a trigger no namespace of its own -- it lives in its
    table's schema, so an unqualified trigger name must not become `public`."""
    window = _window(qtbot, tmp_path)
    dialog = NewTriggerDialog("pr.orders", ["pr.audit_fn"], parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("audit_orders")

    ref = window._ref_for_created_object(dialog)

    assert (ref.kind, ref.schema, ref.name, ref.table) == (
        "trigger", "pr", "audit_orders", "orders",
    )


def test_created_routine_ref_uses_the_dialogs_kind(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    dialog = NewRoutineDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("pr.recalc")
    dialog._kind_combo.setCurrentText("Procedure")

    ref = window._ref_for_created_object(dialog)

    assert (ref.kind, ref.schema, ref.name) == ("procedure", "pr", "recalc")


def test_an_unqualified_routine_name_defaults_to_public(qtbot, tmp_path):
    """The same default Postgres itself would apply."""
    window = _window(qtbot, tmp_path)
    dialog = NewRoutineDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("recalc")

    assert window._ref_for_created_object(dialog).schema == "public"


# --- the tab opens on the skeleton -----------------------------------------
def test_accepting_the_routine_dialog_opens_a_tab_holding_the_skeleton(qtbot, tmp_path):
    """Creation reuses Edit…'s tab path, so the new object arrives as an
    ordinary editable DDL tab -- just seeded with generated text."""
    window = _window(qtbot, tmp_path)
    dialog = NewRoutineDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("recalc")

    window._open_created_ddl_object(dialog)

    panel = window.center_stage.ddl_object_tab(("function", "public", "recalc", None, ()))
    assert panel is not None
    assert "CREATE OR REPLACE FUNCTION" in panel.editor.toPlainText()


# --- deploy-manifest registration ------------------------------------------
def test_creating_an_object_registers_it_in_the_deploy_manifest(qtbot, tmp_path):
    """Without this the object is invisible to §18.3: compute_drift_markers
    iterates settings.deployed alone, so a never-checked-out local file would
    never surface as a pending change."""
    window = _window(qtbot, tmp_path)
    folder = tmp_path / "proj"
    folder.mkdir()
    settings = ProjectSettings(name="p")
    save_settings(folder, settings)
    window._ddl_project_folder = folder
    window._ddl_project_settings = settings
    dialog = NewRoutineDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("pr.recalc")

    window._open_created_ddl_object(dialog)

    entries = window._ddl_project_settings.deployed
    assert len(entries) == 1
    relpath, entry = next(iter(entries.items()))
    assert relpath.endswith(".sql")
    # The "local exists, never deployed" sentinel: an empty hash renders as
    # *-only through compute_drift_markers with no special-casing.
    assert entry.content_hash == ""


def test_creating_an_object_without_a_project_writes_no_manifest(qtbot, tmp_path):
    """Projectless creation is a supported, unversioned flow -- not an error."""
    window = _window(qtbot, tmp_path)
    dialog = NewRoutineDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("recalc")

    window._open_created_ddl_object(dialog)  # must not raise

    assert window._ddl_project_settings is None


# --- menu entries ----------------------------------------------------------
def test_database_menu_offers_new_function_procedure_and_project_status(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    labels = action_labels(find_top_menu(window, "Database"))

    assert "New Function/Procedure…" in labels
    assert "Project Status…" in labels


def test_new_function_procedure_menu_entry_opens_the_dialog(qtbot, tmp_path):
    """Driven through the real signal: FQ-002's action slot takes no
    arguments, and BUG-021 showed a direct call cannot catch a triggered()
    wiring mistake."""
    window = _window(qtbot, tmp_path)
    opened = []
    window._on_ddl_new_routine_requested = lambda: opened.append(True)
    window._build_database_menu()  # rebuild so the lambda is captured

    find_action(find_top_menu(window, "Database"), "New Function/Procedure…").trigger()

    assert opened == [True]


# --- §18.8 entry point -----------------------------------------------------
def test_opening_project_status_probes_first(qtbot, tmp_path):
    """§18.8: opening the window is itself a probe trigger, never a passive
    read of a cached result -- a sandbox that died since project-open must
    show as offline."""
    window = _window(qtbot, tmp_path)
    probes = []
    window.refresh_project_capability_status = lambda: probes.append(True)

    window._open_project_status()

    assert probes == [True]
    assert window._project_status_window is not None


def test_reopening_project_status_reuses_the_same_window(qtbot, tmp_path):
    """Re-invoking the menu entry must raise the existing window rather than
    stacking duplicates."""
    window = _window(qtbot, tmp_path)

    window._open_project_status()
    first = window._project_status_window
    window._open_project_status()

    assert window._project_status_window is first
