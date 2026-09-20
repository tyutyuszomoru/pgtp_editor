# tests/ui/test_ddl_creation_wiring.py
"""MainWindow wiring for FQ-002 (creating a brand-new trigger/function/
procedure from the DDL Explorer) and for §18.8's Project Status entry point.

No live DB and no modal calls: both creation dialogs are shown non-modally,
and the tab-opening path is driven through the same seam Edit… uses.
"""
from dataclasses import replace

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_check import CheckRequest, build_ladder
from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.sandbox import SandboxCapabilities
from pgtp_editor.db.ddl_skeleton import (
    ColumnSpec,
    add_column_skeleton,
    add_constraint_skeleton,
    add_foreign_key_skeleton,
    create_index_skeleton,
    create_table_skeleton,
    drop_column_skeleton,
    drop_constraint_skeleton,
    drop_index_skeleton,
    drop_table_skeleton,
    rename_constraint_skeleton,
    set_column_comment_skeleton,
    set_table_comment_skeleton,
)
from pgtp_editor.db.introspect import (
    ColumnInfo,
    ConstraintInfo,
    DatabaseSchema,
    IndexInfo,
    RoutineInfo,
    TableInfo,
    fetch_schema,
)
from pgtp_editor.ui.alter_column_dialogs import (
    AddColumnDialog,
    ChangeColumnTypeDialog,
    ColumnActionDialog,
    RenameColumnDialog,
    SetColumnDefaultDialog,
)
from pgtp_editor.ui.constraint_dialogs import (
    AddConstraintDialog,
    AddForeignKeyDialog,
    DropConstraintDialog,
    RenameConstraintDialog,
)
from pgtp_editor.ui.ddl_buffer_panel import (
    ALTER_TABLE_COLUMN_ACTIONS,
    ALTER_TABLE_CONSTRAINT_ACTIONS,
)
from pgtp_editor.ui.table_dialogs import (
    OP_COLUMN_COMMENT,
    OP_TABLE_COMMENT,
    CreateIndexDialog,
    CreateTableDialog,
    DropIndexDialog,
    DropTableDialog,
    SetCommentDialog,
)
from pgtp_editor.ui import toolbar_registry
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


def test_creating_an_object_with_a_project_open_does_not_check_it_out(qtbot, tmp_path):
    """FQ-024's trap. Creation shares the `Edit DDL` tab path, and that path now
    dispatches on project state -- so creation must select the non-checkout
    branch EXPLICITLY. Falling through the project test would seed
    `ddl/pr.recalc.sql` from the SKELETON and register the hash of that skeleton
    as the last-deployed reference, claiming an object no database has ever held
    is deployed."""
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

    # No checked-out file at all, and the manifest carries FQ-002's
    # never-deployed sentinel rather than checkout's live-source hash.
    assert not (folder / "ddl").exists()
    assert window._ddl_project_settings.deployed["ddl/pr.recalc.sql"].content_hash == ""


def test_creating_an_object_without_a_project_writes_no_manifest(qtbot, tmp_path):
    """Projectless creation is a supported, unversioned flow -- not an error."""
    window = _window(qtbot, tmp_path)
    dialog = NewRoutineDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("recalc")

    window._open_created_ddl_object(dialog)  # must not raise

    assert window._ddl_project_settings is None


# --- menu entries ----------------------------------------------------------
def test_database_menu_offers_new_function_procedure(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    labels = action_labels(find_top_menu(window, "Database"))

    assert "New Function/Procedure…" in labels


def test_project_status_is_on_the_file_menu_not_the_database_menu(qtbot, tmp_path):
    """BUG-058: §18.8's status screen MOVED to `File`, directly below
    `Project Settings…` — the two concerns no longer share a menu, so this is a
    separate case from `New Function/Procedure…` above."""
    window = _window(qtbot, tmp_path)

    assert "Project Status…" not in action_labels(find_top_menu(window, "Database"))
    file_labels = action_labels(find_top_menu(window, "File"))
    assert "Project Status…" in file_labels
    assert file_labels.index("Project Status…") == (
        file_labels.index("Project Settings…") + 1
    )


def test_the_file_menu_entry_opens_the_project_status_window(qtbot, tmp_path):
    """Driven through the real `triggered` signal (the BUG-021 lesson): a direct
    call to `_open_project_status` would pass a broken connect."""
    window = _window(qtbot, tmp_path)
    opened = []
    window._open_project_status = lambda: opened.append(True)

    find_action(find_top_menu(window, "File"), "Project Status…").trigger()

    assert opened == [True]


def test_project_status_is_not_gated_in_its_new_home(qtbot, tmp_path):
    """It was a plain always-enabled Database item and stays one on File:
    `_open_project_status` handles the projectless case itself, so the move must
    not introduce (or lose) an enablement gate."""
    window = _window(qtbot, tmp_path)
    action = find_action(find_top_menu(window, "File"), "Project Status…")
    assert window._ddl_project_folder is None
    assert action.isEnabled() is True
    assert action.isVisible() is True


def test_a_toolbar_pinned_before_the_move_still_resolves(qtbot, tmp_path):
    """BUG-058 changes the command's menu-path id, so a pinned button survives
    only via `RENAMED_ID_ALIASES` — and the row must be in THAT table, never
    `LEGACY_ID_ALIASES` (which is inverted into `ICON_ID_BY_COMMAND`)."""
    assert toolbar_registry.RENAMED_ID_ALIASES["database.project-status"] == (
        "file.project-status"
    )
    assert "database.project-status" not in toolbar_registry.LEGACY_ID_ALIASES

    window = _window(qtbot, tmp_path)
    known = dict(window._toolbar_ui.collect_menu_commands())
    assert "file.project-status" in known
    assert "database.project-status" not in known
    assert toolbar_registry.resolve_ids(["database.project-status"], known) == [
        "file.project-status"
    ]


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
    window._ddl_project_ui.refresh_capability_status = lambda: probes.append(True)

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


def test_project_status_can_be_reopened_after_being_closed(qtbot, tmp_path):
    """BUG-031 regression lock: closing the window only hides it (there is no
    WA_DeleteOnClose, so `destroyed` never fires and the cached instance is
    never reset), and raise_()/activateWindow() on a hidden window are silent
    no-ops -- so without an explicit re-show the menu entry appeared dead for
    the rest of the session."""
    window = _window(qtbot, tmp_path)
    window.show()

    window._open_project_status()
    panel = window._project_status_window
    assert panel is not None
    assert panel.isVisible()

    panel.close()
    assert not panel.isVisible()
    # Documents *why* the re-show is needed: the close did not destroy it, so
    # the cache still points at the hidden panel and the reuse branch runs.
    assert window._project_status_window is panel

    window._open_project_status()

    assert window._project_status_window is panel  # same instance, not a stack
    assert panel.isVisible()
    assert not panel.windowState() & Qt.WindowState.WindowMinimized


def test_reopening_after_a_close_reprobes_and_rerenders(qtbot, tmp_path):
    """The reuse branch's re-probe is load-bearing and must survive BUG-031's
    re-show fix: `ProjectStatusPanel.showEvent` only probes on the *first* show
    (its `_refreshed_on_show` guard), so a window reopened after the sandbox or
    target died would otherwise come back showing stale state."""
    window = _window(qtbot, tmp_path)
    window.show()
    window._open_project_status()
    panel = window._project_status_window
    probes = []
    window._ddl_project_ui.refresh_capability_status = lambda: probes.append(True)
    pushed = []
    panel.set_diagram = lambda diagram: pushed.append(diagram)

    panel.close()
    window._open_project_status()

    assert probes == [True]
    assert len(pushed) == 1
    assert pushed[0] is not None


# --- FQ-025 slice 1: the Alter Table ▸ column operations --------------------
#
# Same division of labour as FQ-002 above: the tree emits what was clicked, the
# window builds the dialog with the schema data injected, and the accepted
# dialog's rendered skeleton opens as an editable tab. Nothing here executes.


def _alter_schema():
    return DatabaseSchema(
        tables={
            "pr.orders": TableInfo(
                name="pr.orders",
                kind="table",
                columns=[
                    ColumnInfo(
                        name="id", data_type="integer", is_pk=True, is_fk=False,
                        is_nullable=False, default=None,
                    ),
                    ColumnInfo(
                        name="note", data_type="text", is_pk=False, is_fk=False,
                        is_nullable=True, default=None,
                    ),
                ],
            ),
            "pr.v_orders": TableInfo(name="pr.v_orders", kind="view", columns=[]),
        }
    )


def _alter_window(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_schema = _alter_schema()
    return window


def _orders(window):
    return window._ddl_schema.tables["pr.orders"]


def _alter_tabs(window):
    """Every open ALTER tab, newest last."""
    return [
        panel
        for panel in window.center_stage.ddl_object_panels()
        if panel.ref.kind == "alter"
    ]


def test_each_operation_opens_the_dialog_that_collects_its_fields(qtbot, tmp_path):
    """One mapping decides which id opens which dialog -- four operations share
    `ColumnActionDialog` because they collect nothing but table+column."""
    window = _alter_window(qtbot, tmp_path)

    built = {
        operation: type(window._alter_column_dialog(operation, _orders(window), "note"))
        for operation, _label in ALTER_TABLE_COLUMN_ACTIONS
    }

    assert built == {
        "add_column": AddColumnDialog,
        "rename_column": RenameColumnDialog,
        "change_column_type": ChangeColumnTypeDialog,
        "set_default": SetColumnDefaultDialog,
        "drop_column": ColumnActionDialog,
        "set_not_null": ColumnActionDialog,
        "drop_not_null": ColumnActionDialog,
        "drop_default": ColumnActionDialog,
    }


def test_the_dialogs_data_is_injected_from_the_already_fetched_schema(qtbot, tmp_path):
    """The dialog never reaches a database: its dropdowns are filled from the
    `DatabaseSchema` the Explorer already holds. Views are excluded -- every
    operation emits ALTER TABLE, which a view cannot take."""
    window = _alter_window(qtbot, tmp_path)

    dialog = window._alter_column_dialog("drop_column", _orders(window), "note")
    qtbot.addWidget(dialog)

    assert dialog.available_tables() == ["pr.orders"]
    assert dialog.available_columns() == ["id", "note"]


def test_a_column_click_pre_selects_that_column_and_a_table_click_does_not(qtbot, tmp_path):
    window = _alter_window(qtbot, tmp_path)

    from_column = window._alter_column_dialog("drop_column", _orders(window), "note")
    from_table = window._alter_column_dialog("drop_column", _orders(window), "")
    qtbot.addWidget(from_column)
    qtbot.addWidget(from_table)

    assert (from_column.table(), from_column.column()) == ("pr.orders", "note")
    assert from_column.context_column() == "note"
    # From the table node the same operation is offered with no column
    # pre-selected -- the dropdown simply starts at the first column.
    assert (from_table.table(), from_table.column()) == ("pr.orders", "id")
    assert from_table.context_column() == ""


def test_the_dialog_is_shown_non_modally_and_never_exec_d(qtbot, tmp_path, monkeypatch):
    """§30's rule: a test must never reach an un-patched modal call, which holds
    because the gesture uses `show()`, exactly as FQ-002's dialogs do."""
    monkeypatch.setattr(
        QDialog, "exec", lambda self: pytest.fail("the dialog was exec()'d")
    )
    window = _alter_window(qtbot, tmp_path)

    window._on_ddl_alter_column_requested("drop_column", _orders(window), "note")

    assert _alter_tabs(window) == []  # nothing is generated until it is accepted


def test_accepting_opens_a_tab_holding_the_emitters_own_output(qtbot, tmp_path):
    window = _alter_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_column", _orders(window), "note")
    dialog = window.findChild(ColumnActionDialog)

    dialog.accept()

    tabs = _alter_tabs(window)
    assert len(tabs) == 1
    # Byte-identical to the pure emitter: no SQL is assembled in the UI layer.
    assert tabs[0].editor.toPlainText() == drop_column_skeleton(
        table="pr.orders", column="note"
    )


def test_a_cancelled_dialog_opens_nothing(qtbot, tmp_path):
    window = _alter_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_column", _orders(window), "note")
    dialog = window.findChild(ColumnActionDialog)

    dialog.reject()

    assert _alter_tabs(window) == []


def test_add_column_with_a_comment_reaches_the_tab_as_two_statements(qtbot, tmp_path):
    """`add_column_skeleton` emits `ALTER TABLE …;` AND `COMMENT ON COLUMN …;`.
    The tab must carry both, verbatim -- the whole buffer is handed to
    `db/apply.py::apply_ddl` as ONE element of a statement Sequence, so
    multi-statement text survives to the server intact."""
    window = _alter_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("add_column", _orders(window), "")
    dialog = window.findChild(AddColumnDialog)
    dialog._name_edit.setText("memo")
    dialog._comment_edit.setText("free text")

    dialog.accept()

    text = _alter_tabs(window)[0].editor.toPlainText()
    assert text == add_column_skeleton(
        table="pr.orders", column="memo", datatype=dialog.datatype(),
        nullable=True, comment="free text",
    )
    assert "ALTER TABLE" in text and "COMMENT ON COLUMN" in text
    assert text.count(";") == 2


def test_the_alter_tab_identifies_itself_as_an_alter_not_an_object(qtbot, tmp_path):
    """An ALTER is a mutation, not an object: it gets a ref of its own so no
    confirmation ever spells a table as a zero-argument routine."""
    window = _alter_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_column", _orders(window), "note")
    window.findChild(ColumnActionDialog).accept()

    ref = _alter_tabs(window)[0].ref

    assert ref.kind == "alter"
    assert ref.qualified == "ALTER TABLE pr.orders"
    assert ref.short_title == "ALTER TABLE orders"
    # Empty by design: `CheckRequest.checked_name` derives from it, and an ALTER
    # creates no function for tier 3's plpgsql_check to analyse.
    assert ref.name == ""
    # ...and BUG-044's identity lives BESIDE it, never in it: `working_set_name`
    # fills the `applied` key's `object_name` slot and nothing else.
    from pgtp_editor.db.sandbox import text_sha1

    assert ref.working_set_name("ALTER TABLE pr.orders ...") == text_sha1(
        "ALTER TABLE pr.orders ..."
    )
    assert CheckRequest.from_ref(ref, "ALTER TABLE pr.orders ...").checked_name == ""


def test_two_alters_on_one_table_never_share_a_bookkeeping_row(qtbot, tmp_path):
    """BUG-044, at the real ref: two `Drop Column…` generations on DIFFERENT
    columns of one table are two statements, and each must get its own row in
    the sandbox's `applied` table. They used to key as `("alter", "pr", "",
    "orders")` alike, so the second apply silently overwrote the first's row
    and `Check Object in Sandbox` then answered about the wrong statement.
    """
    window = _alter_window(qtbot, tmp_path)
    for column in ("id", "note"):
        window._on_ddl_alter_column_requested("drop_column", _orders(window), column)
        window.findChildren(ColumnActionDialog)[-1].accept()

    panels = _alter_tabs(window)
    keys = [
        CheckRequest.from_ref(panel.ref, panel.editor.toPlainText()).working_set_ref
        for panel in panels
    ]

    assert len(keys) == 2
    assert keys[0] != keys[1]
    # Same table, same kind -- only the identity slot differs.
    assert keys[0][0] == keys[1][0] == "alter"
    assert keys[0][3] == keys[1][3] == "orders"
    # And no alter key is ever the pre-fix empty-name shape the cleanup deletes.
    assert all(key[2] for key in keys)


def test_the_alter_bookkeeping_identity_never_turns_plpgsql_check_on(qtbot, tmp_path):
    """The fix's central gotcha, on the real ref: giving an ALTER an identity
    must not give it a routine NAME, or `build_ladder` would run tier 3's
    `plpgsql_check` on a function that does not exist."""
    window = _alter_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_column", _orders(window), "note")
    window.findChild(ColumnActionDialog).accept()

    panel = _alter_tabs(window)[0]
    text = panel.editor.toPlainText()
    request = CheckRequest.from_ref(panel.ref, text)
    # `plpgsql_check` INSTALLED, so tier 3 is off only because the request says
    # there is nothing to check -- never because the server could not run it.
    caps = SandboxCapabilities(installed_extensions=frozenset({"plpgsql_check"}))
    assert caps.plpgsql_check_state == "installed"
    plan = build_ladder(request, caps, text, record_applied=True)

    assert request.working_set_name
    assert plan.check_index is None
    assert not any("plpgsql_check" in sql for sql in plan.statements)


def test_two_generations_get_two_tabs_never_one_silently_reused(qtbot, tmp_path):
    """`open_ddl_object_tab` focuses an existing tab for a repeated key and
    DISCARDS the new text -- two ALTERs are two statements, so they must not
    share a key."""
    window = _alter_window(qtbot, tmp_path)
    for column in ("id", "note"):
        window._on_ddl_alter_column_requested("drop_column", _orders(window), column)
        # The newest dialog: the first one is still alive (non-modal, and its
        # parent is the window), so `findChild` would keep handing it back.
        window.findChildren(ColumnActionDialog)[-1].accept()

    texts = [panel.editor.toPlainText() for panel in _alter_tabs(window)]

    assert len(texts) == 2
    assert texts[0] != texts[1]


def test_an_alter_tab_never_writes_a_ddl_object_file_or_a_manifest_entry(qtbot, tmp_path):
    """Save-to-object is suppressed structurally: with a project OPEN, an ALTER
    still takes the projectless tab path, so nothing seeds `ddl/<object>.sql`
    and nothing claims a deploy baseline for a mutation."""
    window = _alter_window(qtbot, tmp_path)
    folder = tmp_path / "proj"
    (folder / "ddl").mkdir(parents=True)
    save_settings(folder, ProjectSettings())
    window._ddl_project_folder = folder
    window._ddl_project_settings = ProjectSettings()

    window._on_ddl_alter_column_requested("drop_column", _orders(window), "note")
    window.findChild(ColumnActionDialog).accept()

    assert list((folder / "ddl").iterdir()) == []
    assert window._ddl_project_settings.deployed == {}
    assert _alter_tabs(window)[0].save_path is None


def test_the_ladder_hands_multi_statement_alter_text_over_as_one_element(qtbot, tmp_path):
    """The apply path's end: `db/apply.py::apply_ddl` takes a **Sequence of
    statements** and raises `TypeError` on a bare string, so what matters is
    that the ladder puts the whole buffer in as ONE element rather than
    splitting or stringifying it. Two statements in that element are executed
    together, in the ladder's single transaction."""
    window = _alter_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("add_column", _orders(window), "")
    dialog = window.findChildren(AddColumnDialog)[-1]
    dialog._name_edit.setText("memo")
    dialog._comment_edit.setText("free text")
    dialog.accept()
    panel = _alter_tabs(window)[0]
    text = panel.editor.toPlainText()

    request = CheckRequest.from_ref(panel.ref, text)
    plan = build_ladder(request, SandboxCapabilities(), text, record_applied=True)

    assert plan.statements[plan.ddl_index] == text
    # Tier 3 is not merely skipped by accident: an ALTER creates no function for
    # `plpgsql_check` to analyse, and the empty ref name says so.
    assert plan.check_index is None


# --- FQ-025 slice 2: the Alter Table ▸ constraint operations -----------------
#
# The dialogs and emitters shipped a slice earlier as dead code; what is tested
# here is the wiring that reaches them -- which id opens which dialog, and what
# data the host injects. The dialogs still never touch a database: the existing
# constraints and the referenced table's columns both arrive from the
# `DatabaseSchema` the Explorer already holds.


def _constraint_schema():
    """Two real tables -- a foreign key needs somewhere to point -- and one
    view, which must stay out of both dropdowns."""
    return DatabaseSchema(
        tables={
            "pr.orders": TableInfo(
                name="pr.orders",
                kind="table",
                columns=[
                    ColumnInfo(
                        name="id", data_type="integer", is_pk=True, is_fk=False,
                        is_nullable=False, default=None,
                    ),
                    ColumnInfo(
                        name="customer_id", data_type="integer", is_pk=False,
                        is_fk=True, is_nullable=True, default=None,
                    ),
                ],
            ),
            "pr.customer": TableInfo(
                name="pr.customer",
                kind="table",
                columns=[
                    ColumnInfo(
                        name="cust_id", data_type="integer", is_pk=True, is_fk=False,
                        is_nullable=False, default=None,
                    ),
                    ColumnInfo(
                        name="email", data_type="text", is_pk=False, is_fk=False,
                        is_nullable=True, default=None,
                    ),
                ],
            ),
            "pr.v_orders": TableInfo(name="pr.v_orders", kind="view", columns=[]),
        },
        constraints={
            "pr.orders.orders_pkey": ConstraintInfo(
                schema="pr", table="orders", name="orders_pkey",
                kind="primary key", columns=["id"],
                definition="PRIMARY KEY (id)",
            ),
            "pr.orders.orders_qty_check": ConstraintInfo(
                schema="pr", table="orders", name="orders_qty_check",
                kind="check", columns=[], definition="CHECK ((qty > 0))",
            ),
            # Another table's constraint: it must never appear under pr.orders.
            "pr.customer.customer_pkey": ConstraintInfo(
                schema="pr", table="customer", name="customer_pkey",
                kind="primary key", columns=["cust_id"],
                definition="PRIMARY KEY (cust_id)",
            ),
        },
    )


def _constraint_window(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_schema = _constraint_schema()
    return window


def test_the_four_constraint_operations_open_their_own_dialogs(qtbot, tmp_path):
    """The same one mapping as slice 1's eight -- there is no second table and
    no second signal, so a menu entry cannot come to open the wrong dialog."""
    window = _constraint_window(qtbot, tmp_path)
    table_info = window._ddl_schema.tables["pr.orders"]

    built = {
        operation: type(window._alter_column_dialog(operation, table_info, "customer_id"))
        for operation, _label in ALTER_TABLE_CONSTRAINT_ACTIONS
    }

    assert built == {
        "add_constraint": AddConstraintDialog,
        "add_foreign_key": AddForeignKeyDialog,
        "drop_constraint": DropConstraintDialog,
        "rename_constraint": RenameConstraintDialog,
    }


@pytest.mark.parametrize("operation", ["drop_constraint", "rename_constraint"])
def test_the_existing_constraints_reach_the_picker_with_their_types_shown(
    qtbot, tmp_path, operation
):
    """`DROP CONSTRAINT` is the identical statement for every type, so the
    picker's labels are the only place a FK is distinguishable from a CHECK
    before it is dropped. The list is this table's alone."""
    window = _constraint_window(qtbot, tmp_path)

    dialog = window._alter_column_dialog(
        operation, window._ddl_schema.tables["pr.orders"], "customer_id"
    )
    qtbot.addWidget(dialog)

    assert dialog.available_constraints() == ["orders_pkey", "orders_qty_check"]
    assert dialog.constraint_labels() == [
        "orders_pkey — PRIMARY KEY (id)",
        # No columns (a table-level CHECK has a NULL conkey), so its definition
        # stands in rather than an empty pair of parentheses.
        "orders_qty_check — CHECK — CHECK ((qty > 0))",
    ]


def test_the_constraint_list_follows_the_table_dropdown(qtbot, tmp_path):
    """Injected as a CALLABLE, not a snapshot: re-picking a table reads the
    current schema, and a constraint name is only meaningful against its
    table."""
    window = _constraint_window(qtbot, tmp_path)
    dialog = window._alter_column_dialog(
        "drop_constraint", window._ddl_schema.tables["pr.orders"], ""
    )
    qtbot.addWidget(dialog)

    dialog._table_combo.setCurrentText("pr.customer")

    assert dialog.available_constraints() == ["customer_pkey"]


def test_dropping_a_primary_key_states_its_consequence_without_refusing(qtbot, tmp_path):
    """It generates text into a tab; Postgres answers authoritatively when the
    tab is run. So the note is a note, never a block."""
    window = _constraint_window(qtbot, tmp_path)
    dialog = window._alter_column_dialog(
        "drop_constraint", window._ddl_schema.tables["pr.orders"], ""
    )
    qtbot.addWidget(dialog)

    assert dialog.constraint_kind() == "primary key"
    assert "PRIMARY KEY" in dialog.note()
    ok_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button.isEnabled()


def test_the_foreign_key_dialog_repopulates_on_the_referenced_table(qtbot, tmp_path):
    """The whole reason the target-table→column mapping is injected as the same
    callable: picking a referenced table must offer THAT table's columns."""
    window = _constraint_window(qtbot, tmp_path)
    dialog = window._alter_column_dialog(
        "add_foreign_key", window._ddl_schema.tables["pr.orders"], "customer_id"
    )
    qtbot.addWidget(dialog)

    # The local side is this table's; views are in neither list.
    assert dialog.available_tables() == ["pr.customer", "pr.orders"]
    assert dialog.column_picker().available_columns() == ["id", "customer_id"]

    dialog._ref_table_combo.setCurrentText("pr.customer")

    assert dialog.ref_table() == "pr.customer"
    assert dialog.available_ref_columns() == ["cust_id", "email"]


def test_a_constraint_dialog_is_shown_non_modally_and_opens_nothing_until_accepted(
    qtbot, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        QDialog, "exec", lambda self: pytest.fail("the dialog was exec()'d")
    )
    window = _constraint_window(qtbot, tmp_path)

    window._on_ddl_alter_column_requested(
        "drop_constraint", window._ddl_schema.tables["pr.orders"], ""
    )

    assert _alter_tabs(window) == []


def test_accepting_a_drop_constraint_opens_a_tab_with_the_emitters_own_text(
    qtbot, tmp_path
):
    window = _constraint_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested(
        "drop_constraint", window._ddl_schema.tables["pr.orders"], ""
    )
    dialog = window.findChild(DropConstraintDialog)

    dialog.accept()

    tabs = _alter_tabs(window)
    assert len(tabs) == 1
    assert tabs[0].editor.toPlainText() == drop_constraint_skeleton(
        table="pr.orders", name="orders_pkey"
    )
    assert tabs[0].ref.kind == "alter"


def test_accepting_a_rename_constraint_opens_a_tab_with_the_emitters_own_text(
    qtbot, tmp_path
):
    window = _constraint_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested(
        "rename_constraint", window._ddl_schema.tables["pr.orders"], ""
    )
    dialog = window.findChild(RenameConstraintDialog)
    dialog._new_name_edit.setText("orders_pk")

    dialog.accept()

    assert _alter_tabs(window)[0].editor.toPlainText() == rename_constraint_skeleton(
        table="pr.orders", name="orders_pkey", new_name="orders_pk"
    )


def test_accepting_an_add_foreign_key_opens_a_tab_with_the_emitters_own_text(
    qtbot, tmp_path
):
    window = _constraint_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested(
        "add_foreign_key", window._ddl_schema.tables["pr.orders"], "customer_id"
    )
    dialog = window.findChild(AddForeignKeyDialog)
    dialog._name_edit.setText("fk_customer")
    dialog._ref_table_combo.setCurrentText("pr.customer")

    dialog.accept()

    assert _alter_tabs(window)[0].editor.toPlainText() == add_foreign_key_skeleton(
        table="pr.orders",
        name="fk_customer",
        columns=["customer_id"],
        ref_table="pr.customer",
        ref_columns=["cust_id"],
        on_delete=None,
        on_update=None,
    )


def test_accepting_an_add_constraint_opens_a_tab_with_the_emitters_own_text(
    qtbot, tmp_path
):
    window = _constraint_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested(
        "add_constraint", window._ddl_schema.tables["pr.orders"], "id"
    )
    dialog = window.findChild(AddConstraintDialog)
    dialog._name_edit.setText("orders_id_uq")
    dialog._type_combo.setCurrentText("UNIQUE")

    dialog.accept()

    assert _alter_tabs(window)[0].editor.toPlainText() == add_constraint_skeleton(
        table="pr.orders",
        name="orders_id_uq",
        constraint_type="UNIQUE",
        columns=["id"],
    )


def test_a_cancelled_constraint_dialog_opens_nothing(qtbot, tmp_path):
    window = _constraint_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested(
        "drop_constraint", window._ddl_schema.tables["pr.orders"], ""
    )

    window.findChild(DropConstraintDialog).reject()

    assert _alter_tabs(window) == []


def test_each_constraint_generation_gets_its_own_tab(qtbot, tmp_path):
    """The serial counter again: `open_ddl_object_tab` focuses an existing tab
    for a repeated key and DISCARDS the new text, and two drops on one table are
    two different statements."""
    window = _constraint_window(qtbot, tmp_path)
    for name in ("orders_pkey", "orders_qty_check"):
        window._on_ddl_alter_column_requested(
            "drop_constraint", window._ddl_schema.tables["pr.orders"], ""
        )
        dialog = window.findChildren(DropConstraintDialog)[-1]
        dialog._constraint_combo.setCurrentIndex(
            dialog.available_constraints().index(name)
        )
        dialog.accept()

    texts = [panel.editor.toPlainText() for panel in _alter_tabs(window)]

    assert len(texts) == 2
    assert texts[0] != texts[1]


# --- FQ-025 slice 3: indexes, comments, whole-table --------------------------
# The same host, the same one signal (except `Create Table…`, which has no table
# to carry), the same injected-data rule -- and one new injected source, the
# table's existing indexes, whose provenance is the slice's one trap.


def _index_schema():
    """`_constraint_schema` plus indexes: one droppable, one owned by the
    primary key constraint, and one on ANOTHER table."""
    schema = _constraint_schema()
    return replace(
        schema,
        tables={
            **schema.tables,
            "pr.orders": replace(
                schema.tables["pr.orders"],
                # The whole-relation `pg_description` row (`objsubid = 0`).
                # It is what `Set Table Comment…` must open on -- see
                # `test_a_table_comment_opens_on_the_existing_comment`.
                comment="ordering, one row per order",
                columns=[
                    *schema.tables["pr.orders"].columns,
                    ColumnInfo(
                        name="code", data_type="text", is_pk=False, is_fk=False,
                        is_nullable=True, default=None,
                        comment="the customer-facing order code",
                    ),
                ],
            ),
        },
        indexes={
            "pr.idx_orders_code": IndexInfo(
                schema="pr", table="orders", name="idx_orders_code",
                columns=["code"], is_unique=True, method="btree",
            ),
            # PostgreSQL refuses `DROP INDEX` on this one -- the constraint
            # owns it -- so the picker must hide it AND say so.
            "pr.orders_pkey": IndexInfo(
                schema="pr", table="orders", name="orders_pkey",
                columns=["id"], is_unique=True, is_primary=True,
                method="btree", constraint_name="orders_pkey",
            ),
            "pr.customer_pkey": IndexInfo(
                schema="pr", table="customer", name="customer_pkey",
                columns=["cust_id"], is_unique=True, is_primary=True,
                method="btree", constraint_name="customer_pkey",
            ),
        },
    )


def _index_window(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._ddl_schema = _index_schema()
    return window


def _index_orders(window):
    return window._ddl_schema.tables["pr.orders"]


def test_the_slice_three_operations_open_their_own_dialogs(qtbot, tmp_path):
    """Still ONE mapping for every id the tree emits. The two comment ids are
    the second pair to share a dialog whose mode is fixed by the menu item --
    exactly what `ColumnActionDialog` already does for its four."""
    window = _index_window(qtbot, tmp_path)

    built = {
        operation: type(
            window._alter_column_dialog(operation, _index_orders(window), "code")
        )
        for operation in ("create_index", "drop_index", "drop_table")
    }

    assert built == {
        "create_index": CreateIndexDialog,
        "drop_index": DropIndexDialog,
        "drop_table": DropTableDialog,
    }


@pytest.mark.parametrize("target", [OP_TABLE_COMMENT, OP_COLUMN_COMMENT])
def test_a_comment_entry_opens_the_one_dialog_in_the_mode_its_menu_item_named(
    qtbot, tmp_path, target
):
    """One class, two modes, and the mode is not a field inside it: a dialog
    opened from "Set column comment" that could quietly comment the table
    instead would only invite disagreeing with the menu."""
    window = _index_window(qtbot, tmp_path)

    dialog = window._alter_column_dialog(target, _index_orders(window), "code")
    qtbot.addWidget(dialog)

    assert isinstance(dialog, SetCommentDialog)
    assert dialog.target() == target
    # A column is named in column mode only -- a table comment has none, so the
    # inherited dropdown is left out of the form and reports nothing.
    assert dialog.column() == ("code" if target == OP_COLUMN_COMMENT else "")


def test_the_drop_index_picker_is_sourced_from_the_explorers_own_schema(qtbot, tmp_path):
    """The slice's trap. `DatabaseSchema.indexes` is populated by
    `fetch_routines_and_triggers` -- the DDL Explorer's own fetch, which is what
    `_fetch_ddl_schema` calls and what `_ddl_schema` holds. Sourcing the picker
    from a `fetch_schema`-derived schema instead would silently show nothing
    about a table full of indexes."""
    window = _index_window(qtbot, tmp_path)

    dialog = window._alter_column_dialog("drop_index", _index_orders(window), "")
    qtbot.addWidget(dialog)

    assert dialog.available_indexes() == ["idx_orders_code"]

    # The other schema in this app, built from the same three queries plus no
    # index query at all: same tables, same constraints, no indexes.
    from_fetch_schema = fetch_schema(
        ConnectionParams(host="h", port="5432", database="d", user="u"),
        runner=lambda *_a, **_k: [[], [], []],
    )
    assert from_fetch_schema.indexes == {}
    # And the picker would be empty if it were fed one -- so this is a
    # provenance requirement, not a preference.
    window._ddl_schema = replace(window._ddl_schema, indexes={})
    starved = window._alter_column_dialog("drop_index", _index_orders(window), "")
    qtbot.addWidget(starved)
    assert starved.available_indexes() == []


def test_constraint_backed_indexes_are_hidden_and_the_reason_is_shown(qtbot, tmp_path):
    """Listing them would offer a statement PostgreSQL refuses; omitting them
    silently would make a "where did my unique index go?" mystery, since the
    user can see it in the Explorer. So they are filtered AND named, pointing at
    the entry that CAN remove them."""
    window = _index_window(qtbot, tmp_path)

    dialog = window._alter_column_dialog("drop_index", _index_orders(window), "")
    qtbot.addWidget(dialog)

    assert dialog.available_indexes() == ["idx_orders_code"]
    assert dialog.hidden_indexes() == ["orders_pkey"]
    note = dialog.note()
    assert "orders_pkey" in note
    # The destination is slice 2's unified entry, by the name the menu uses.
    assert "Drop constraint…" in note
    # A note, never a block: it explains an omission, it does not object to the
    # user's choice.
    assert dialog._buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def test_the_index_list_follows_the_table_dropdown(qtbot, tmp_path):
    """Injected as a CALLABLE, exactly as the constraint list is: re-picking a
    table reads the current schema rather than a snapshot taken when the menu
    was clicked."""
    window = _index_window(qtbot, tmp_path)
    dialog = window._alter_column_dialog("drop_index", _index_orders(window), "")
    qtbot.addWidget(dialog)

    dialog._table_combo.setCurrentText("pr.customer")

    # `pr.customer`'s only index is its primary key's, which is not droppable.
    assert dialog.available_indexes() == []
    assert dialog.hidden_indexes() == ["customer_pkey"]


def test_the_column_comment_dialog_opens_on_the_existing_comment(qtbot, tmp_path):
    """A comment is a value rendered as a SQL string literal, not free SQL, so
    unlike a DEFAULT or a USING clause it may be seeded -- which is the
    difference between editing a description and retyping it from memory."""
    window = _index_window(qtbot, tmp_path)

    dialog = window._alter_column_dialog(OP_COLUMN_COMMENT, _index_orders(window), "code")
    qtbot.addWidget(dialog)

    assert dialog.column() == "code"
    assert dialog.comment() == "the customer-facing order code"
    assert not dialog.removes_the_comment()


def test_a_table_comment_opens_on_the_existing_comment(qtbot, tmp_path):
    """The table mode is seeded exactly as the column mode is, from
    `TableInfo.comment` (`pg_description` at `objsubid = 0`) on the schema the
    Explorer already fetched -- no extra query.

    It used to open blank, which was not merely inconvenient: see the
    data-loss regression lock below."""
    window = _index_window(qtbot, tmp_path)

    dialog = window._alter_column_dialog(OP_TABLE_COMMENT, _index_orders(window), "code")
    qtbot.addWidget(dialog)

    assert dialog.comment() == "ordering, one row per order"
    assert not dialog.removes_the_comment()


def test_an_untouched_ok_on_a_table_comment_never_removes_it(qtbot, tmp_path):
    """**Data-loss regression lock.** A blank box emits `IS NULL`, which is
    Postgres's only spelling for "remove the comment" -- so an unseeded table
    dialog turned "I opened it and pressed OK" into a silent deletion of the
    table's description. The emitted DDL must PRESERVE the comment, verbatim.
    """
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested(
        OP_TABLE_COMMENT, _index_orders(window), ""
    )
    dialog = window.findChildren(SetCommentDialog)[-1]

    dialog.accept()  # nothing typed, nothing changed

    text = _alter_tabs(window)[0].editor.toPlainText()
    assert text == set_table_comment_skeleton(
        table="pr.orders", comment="ordering, one row per order"
    )
    assert "IS NULL" not in text
    assert "ordering, one row per order" in text


def test_a_table_with_no_comment_still_opens_blank(qtbot, tmp_path):
    """The seed is the *existing* comment, and `None` is a real state --
    `TableInfo.comment` is `None` when `pg_description` has no `objsubid = 0`
    row. A table that never had a comment must still offer an empty box (and
    so may still be given one), not the word "None"."""
    window = _index_window(qtbot, tmp_path)

    dialog = window._alter_column_dialog(
        OP_TABLE_COMMENT, window._ddl_schema.tables["pr.customer"], ""
    )
    qtbot.addWidget(dialog)

    assert dialog.comment() == ""
    assert dialog.removes_the_comment()


def test_a_table_comment_is_seeded_verbatim_quotes_and_all(qtbot, tmp_path):
    """No strip, no normalisation: the box must round-trip what is stored, or
    an untouched OK still REWRITES the comment instead of leaving it alone."""
    window = _index_window(qtbot, tmp_path)
    stored = "  it's the 'orders' table  "
    window._ddl_schema.tables["pr.orders"] = replace(
        window._ddl_schema.tables["pr.orders"], comment=stored
    )

    dialog = window._alter_column_dialog(OP_TABLE_COMMENT, _index_orders(window), "")
    qtbot.addWidget(dialog)

    assert dialog.comment() == stored


def test_create_table_is_its_own_gesture_with_the_clicked_schema_seeded(qtbot, tmp_path):
    """`Create Table…` has no table to alter, so it takes its own signal and its
    own handler: the schema is its whole context, and `table()` means "the table
    being created"."""
    window = _index_window(qtbot, tmp_path)

    window._on_ddl_create_table_requested("pr")
    dialog = window.findChild(CreateTableDialog)

    assert dialog.table() == "pr."  # seeded, and waiting for the name
    assert _alter_tabs(window) == []  # nothing until it is accepted


@pytest.mark.parametrize(
    "gesture",
    [
        lambda window: window._on_ddl_create_table_requested("pr"),
        lambda window: window._on_ddl_alter_column_requested(
            "drop_table", _index_orders(window), ""
        ),
        lambda window: window._on_ddl_alter_column_requested(
            "drop_index", _index_orders(window), ""
        ),
    ],
)
def test_every_slice_three_dialog_is_shown_non_modally(qtbot, tmp_path, monkeypatch, gesture):
    """§30's rule, and FQ-025's: the window stays usable while the statement is
    composed, and a cancelled dialog opens nothing at all."""
    monkeypatch.setattr(
        QDialog, "exec", lambda self: pytest.fail("the dialog was exec()'d")
    )
    window = _index_window(qtbot, tmp_path)

    gesture(window)

    assert _alter_tabs(window) == []


def test_accepting_create_index_opens_a_tab_with_the_emitters_own_text(qtbot, tmp_path):
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("create_index", _index_orders(window), "code")
    dialog = window.findChild(CreateIndexDialog)
    dialog._name_edit.setText("idx_orders_code2")
    dialog.column_picker().set_selection(["code"])
    dialog._unique_check.setChecked(True)

    dialog.accept()

    tabs = _alter_tabs(window)
    assert len(tabs) == 1
    assert tabs[0].editor.toPlainText() == create_index_skeleton(
        name="idx_orders_code2", table="pr.orders", columns=["code"],
        unique=True, method="btree",
    )


def test_accepting_drop_index_drops_the_indexs_own_qualified_identity(qtbot, tmp_path):
    """`DROP INDEX … ON table` does not exist: an index is identified by
    `schema.name`, which is what reaches the emitter -- never the display label
    and never the table's name."""
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_index", _index_orders(window), "")
    dialog = window.findChild(DropIndexDialog)

    dialog.accept()

    tabs = _alter_tabs(window)
    assert len(tabs) == 1
    assert tabs[0].editor.toPlainText() == drop_index_skeleton(
        index="pr.idx_orders_code"
    )


@pytest.mark.parametrize(
    "target, expected",
    [
        (OP_TABLE_COMMENT, lambda: set_table_comment_skeleton(
            table="pr.orders", comment="ordering, one row per order"
        )),
        (OP_COLUMN_COMMENT, lambda: set_column_comment_skeleton(
            table="pr.orders", column="code", comment="ordering, one row per order"
        )),
    ],
)
def test_accepting_a_comment_opens_a_tab_with_the_emitters_own_text(
    qtbot, tmp_path, target, expected
):
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested(target, _index_orders(window), "code")
    dialog = window.findChild(SetCommentDialog)
    dialog._comment_edit.setText("ordering, one row per order")

    dialog.accept()

    tabs = _alter_tabs(window)
    assert len(tabs) == 1
    assert tabs[0].editor.toPlainText() == expected()


def test_accepting_create_table_opens_a_tab_with_the_emitters_own_text(qtbot, tmp_path):
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_create_table_requested("pr")
    dialog = window.findChild(CreateTableDialog)
    dialog._name_edit.setText("pr.invoice")
    dialog.column_rows().set_row(0, name="id", datatype="integer", nullable=False,
                                 primary_key=True)
    dialog.column_rows().set_row(1, name="total", datatype="numeric")

    dialog.accept()

    tabs = _alter_tabs(window)
    assert len(tabs) == 1
    assert tabs[0].editor.toPlainText() == create_table_skeleton(
        table="pr.invoice",
        columns=[
            ColumnSpec(name="id", datatype="integer", nullable=False),
            ColumnSpec(name="total", datatype="numeric"),
        ],
        primary_key=["id"],
    )


def test_accepting_drop_table_generates_it_with_no_confirmation_at_all(
    qtbot, tmp_path, monkeypatch
):
    """FQ-025's ruling, honoured deliberately: no typed-name gate, no "are you
    sure?", no message box on any path. Generating `DROP TABLE t` executes
    nothing -- the editable tab is the safeguard, and running it is a separate
    explicit gesture, so friction here would sit where nothing happens and be
    absent where something does."""
    for name in ("question", "warning", "critical", "information"):
        monkeypatch.setattr(
            QMessageBox,
            name,
            staticmethod(
                lambda *a, _name=name, **k: pytest.fail(
                    f"Drop table put up a QMessageBox.{_name}"
                )
            ),
        )
    window = _index_window(qtbot, tmp_path)

    window._on_ddl_alter_column_requested("drop_table", _index_orders(window), "")
    window.findChild(DropTableDialog).accept()

    tabs = _alter_tabs(window)
    assert len(tabs) == 1
    assert tabs[0].editor.toPlainText() == drop_table_skeleton(table="pr.orders")


def test_a_cancelled_slice_three_dialog_opens_nothing(qtbot, tmp_path):
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_create_table_requested("pr")

    window.findChild(CreateTableDialog).reject()

    assert _alter_tabs(window) == []


def test_each_slice_three_generation_gets_its_own_tab(qtbot, tmp_path):
    """The serial counter, unchanged: two comments on one table are two
    different statements, and `open_ddl_object_tab` would focus the first tab
    and DISCARD the second's text if they shared a key."""
    window = _index_window(qtbot, tmp_path)
    for text in ("first", "second"):
        window._on_ddl_alter_column_requested(OP_TABLE_COMMENT, _index_orders(window), "")
        dialog = window.findChildren(SetCommentDialog)[-1]
        dialog._comment_edit.setText(text)
        dialog.accept()

    texts = [panel.editor.toPlainText() for panel in _alter_tabs(window)]

    assert len(texts) == 2
    assert texts[0] != texts[1]


# --- The generated tab's TITLE ----------------------------------------------
#
# Every generation used to be titled `ALTER <table>`, whatever it held: a
# `CREATE TABLE pr.invoice` tab read `ALTER invoice`, and a `DROP INDEX` tab
# named a table its statement does not mention at all. The ref now carries the
# statement AND its subject, because the subject is the half no verb lookup can
# supply -- `DROP INDEX` names an index and `COMMENT ON COLUMN` names a column,
# and neither is in the `(schema, table)` pair the ref was built from.


def _titled(window):
    """(short_title, qualified) of the newest generated tab."""
    ref = _alter_tabs(window)[-1].ref
    return ref.short_title, ref.qualified


def test_an_alter_tab_is_titled_after_the_statement_it_holds(qtbot, tmp_path):
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_column", _index_orders(window), "code")
    window.findChildren(ColumnActionDialog)[-1].accept()

    # The twelve column/constraint operations really do emit `ALTER TABLE`, so
    # for them the only change is that the title says so in full.
    assert _titled(window) == ("ALTER TABLE orders", "ALTER TABLE pr.orders")


def test_a_create_table_tab_is_not_titled_alter(qtbot, tmp_path):
    """The tab is named after its BUFFER, not after the `Alter Table ▸`
    submenu -- and `Create Table…` is not even on that submenu."""
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_create_table_requested("pr")
    dialog = window.findChild(CreateTableDialog)
    dialog._name_edit.setText("pr.invoice")
    dialog.column_rows().set_row(0, name="id", datatype="integer", nullable=False,
                                 primary_key=True)

    dialog.accept()

    assert _titled(window) == ("CREATE TABLE invoice", "CREATE TABLE pr.invoice")


def test_a_drop_index_tab_names_the_index_not_the_table(qtbot, tmp_path):
    """`DROP INDEX pr.idx_orders_code` mentions no table, so a title built from
    the table named something the statement never touches."""
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_index", _index_orders(window), "")
    window.findChildren(DropIndexDialog)[-1].accept()

    assert _titled(window) == (
        "DROP INDEX idx_orders_code",
        "DROP INDEX pr.idx_orders_code",
    )


def test_a_create_index_tab_names_the_index_the_user_typed(qtbot, tmp_path):
    """The bare name from the dialog, qualified with the TABLE's schema --
    an index lives in its table's schema in Postgres."""
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("create_index", _index_orders(window), "code")
    dialog = window.findChildren(CreateIndexDialog)[-1]
    dialog._name_edit.setText("idx_orders_total")
    dialog.column_picker().set_selection(["code"])

    dialog.accept()

    assert _titled(window) == (
        "CREATE INDEX idx_orders_total",
        "CREATE INDEX pr.idx_orders_total",
    )


def test_a_column_comment_tab_names_the_column(qtbot, tmp_path):
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested(OP_COLUMN_COMMENT, _index_orders(window), "code")
    window.findChildren(SetCommentDialog)[-1].accept()

    assert _titled(window) == (
        "COMMENT ON COLUMN orders.code",
        "COMMENT ON COLUMN pr.orders.code",
    )


def test_a_table_comment_tab_names_the_table(qtbot, tmp_path):
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested(OP_TABLE_COMMENT, _index_orders(window), "")
    window.findChildren(SetCommentDialog)[-1].accept()

    assert _titled(window) == (
        "COMMENT ON TABLE orders",
        "COMMENT ON TABLE pr.orders",
    )


def test_a_drop_table_tab_says_drop_table(qtbot, tmp_path):
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_table", _index_orders(window), "")
    window.findChildren(DropTableDialog)[-1].accept()

    assert _titled(window) == ("DROP TABLE orders", "DROP TABLE pr.orders")


def test_the_tab_widgets_label_is_the_refs_short_title(qtbot, tmp_path):
    """The title is not merely computable -- it is what the tab bar shows."""
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_index", _index_orders(window), "")
    window.findChildren(DropIndexDialog)[-1].accept()
    panel = _alter_tabs(window)[-1]

    assert panel.tab_title().startswith("DROP INDEX idx_orders_code")


def test_the_save_as_prefill_follows_the_statement_too(qtbot, tmp_path):
    """A saved `DROP INDEX` script called `alter_pr_orders.sql` is a file whose
    name has to be disbelieved."""
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_index", _index_orders(window), "")
    window.findChildren(DropIndexDialog)[-1].accept()

    assert _alter_tabs(window)[-1].ref.default_file_name == (
        "drop_index_pr_idx_orders_code.sql"
    )


def test_the_title_change_left_the_empty_name_alone(qtbot, tmp_path):
    """`AlterDdlRef.name` stays empty on purpose: `CheckRequest.checked_name`
    derives from it, and an ALTER creates no function for tier 3's
    `plpgsql_check` to analyse. A nicer title must not put one there."""
    window = _index_window(qtbot, tmp_path)
    window._on_ddl_alter_column_requested("drop_index", _index_orders(window), "")
    window.findChildren(DropIndexDialog)[-1].accept()

    assert _alter_tabs(window)[-1].ref.name == ""
