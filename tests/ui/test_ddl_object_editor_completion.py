# tests/ui/test_ddl_object_editor_completion.py
"""Schema-aware Ctrl+Space completion in the DDL object editor (spec §18.6).

Covers the injection seam (`set_schema_index`, mirroring
`XmlEditor.set_schema_model`), the three completion contexts (schema-qualified
table reference, attached-trigger NEW./OLD., unattached-trigger NEW./OLD.),
and the session-only (never persisted) unattached-trigger table pick.

No live database: `SchemaIndex` is built directly from a canned
`DatabaseSchema`, mirroring `test_xml_editor_completion.py`'s canned-Model
style. The unattached-trigger picker's `QInputDialog.getItem` is monkeypatched
per the project's "never let a test reach an un-patched modal Qt call" rule.
"""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QInputDialog

from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
)
from pgtp_editor.db.schema_index import SchemaIndex
from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel, DdlObjectRef


def _schema():
    tables = {
        "pr.equipment": TableInfo(
            name="pr.equipment",
            kind="table",
            columns=[
                ColumnInfo(name="id", data_type="integer", is_pk=True, is_fk=False, is_nullable=False, default=None),
                ColumnInfo(name="tag", data_type="varchar", is_pk=False, is_fk=False, is_nullable=True, default=None),
            ],
        ),
        "pr.eq_view": TableInfo(name="pr.eq_view", kind="view", columns=[]),
        "hr.employee": TableInfo(
            name="hr.employee",
            kind="table",
            columns=[
                ColumnInfo(name="name", data_type="text", is_pk=False, is_fk=False, is_nullable=True, default=None),
            ],
        ),
    }
    routines = {
        "pr.audit_log()": RoutineInfo(
            schema="pr", name="audit_log", arg_types=[], return_type="trigger",
            language="plpgsql", source="CREATE FUNCTION pr.audit_log() ...", kind="function",
        ),
        "pr.unattached()": RoutineInfo(
            schema="pr", name="unattached", arg_types=[], return_type="trigger",
            language="plpgsql", source="CREATE FUNCTION pr.unattached() ...", kind="function",
        ),
    }
    triggers = {
        "pr.equipment.trg_audit": TriggerInfo(
            schema="pr", table="equipment", name="trg_audit", timing="after",
            events=["insert"], function_name="audit_log",
            definition="CREATE TRIGGER trg_audit ...",
        ),
    }
    return DatabaseSchema(tables=tables, routines=routines, triggers=triggers)


def _index():
    return SchemaIndex(_schema())


def _panel(qtbot, ref=None, text="", schema_index=None):
    ref = ref or DdlObjectRef(kind="function", schema="pr", name="audit_log")
    panel = DdlObjectEditorPanel(ref, text)
    qtbot.addWidget(panel)
    if schema_index is not None:
        panel.set_schema_index(schema_index)
    return panel


def _put_caret_after(panel, marker: str) -> None:
    text = panel.editor.toPlainText()
    cursor = panel.editor.textCursor()
    cursor.setPosition(text.index(marker) + len(marker))
    panel.editor.setTextCursor(cursor)


def _ctrl_space(panel) -> None:
    panel.editor.setFocus()
    QTest.keyClick(panel.editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)


# --- Injection seam ----------------------------------------------------------
def test_schema_index_defaults_to_none(qtbot):
    panel = _panel(qtbot)
    assert panel.schema_index() is None


def test_set_schema_index_injects_it(qtbot):
    panel = _panel(qtbot)
    index = _index()
    panel.set_schema_index(index)
    assert panel.schema_index() is index


def test_ctrl_space_no_popup_without_schema_index(qtbot):
    panel = _panel(qtbot, text="select * from pr.equ")
    _put_caret_after(panel, "equ")
    _ctrl_space(panel)
    assert panel._completion_popup is None or not panel._completion_popup.isVisible()


def test_panel_never_imports_db_introspect():
    """§18.5 D1's invariant, restated for §18.6: the panel module must not
    import db/introspect.py directly (it only ever sees a finished
    SchemaIndex handed in by injection)."""
    import pgtp_editor.ui.ddl_object_editor as mod

    source = open(mod.__file__, encoding="utf-8").read()
    assert "db.introspect" not in source
    assert "db import introspect" not in source


# --- Schema-qualified table reference (row 1) --------------------------------
def test_ctrl_space_offers_schemas_with_no_dotted_prefix(qtbot):
    panel = _panel(qtbot, text="select * from ", schema_index=_index())
    cursor = panel.editor.textCursor()
    cursor.setPosition(len(panel.editor.toPlainText()))
    panel.editor.setTextCursor(cursor)
    _ctrl_space(panel)
    popup = panel._completion_popup
    assert popup is not None and popup.isVisible()
    assert popup.visible_keys() == ["hr", "pr"]


def test_ctrl_space_offers_tables_in_schema(qtbot):
    panel = _panel(qtbot, text="select * from pr.", schema_index=_index())
    _put_caret_after(panel, "pr.")
    _ctrl_space(panel)
    popup = panel._completion_popup
    assert popup is not None and popup.isVisible()
    assert popup.visible_keys() == ["eq_view", "equipment"]
    assert popup.item(0).text() == "pr.eq_view"


def test_ctrl_space_filters_tables_by_prefix(qtbot):
    panel = _panel(qtbot, text="select * from pr.equ", schema_index=_index())
    _put_caret_after(panel, "equ")
    _ctrl_space(panel)
    popup = panel._completion_popup
    assert popup.visible_keys() == ["equipment"]


def test_choosing_table_inserts_bare_name_replacing_prefix(qtbot):
    panel = _panel(qtbot, text="select * from pr.equ", schema_index=_index())
    _put_caret_after(panel, "equ")
    _ctrl_space(panel)
    panel._completion_popup.chosen.emit("equipment")
    assert panel.text() == "select * from pr.equipment"


def test_ctrl_space_no_popup_for_unknown_schema(qtbot):
    panel = _panel(qtbot, text="select * from nosuch.", schema_index=_index())
    _put_caret_after(panel, "nosuch.")
    _ctrl_space(panel)
    assert panel._completion_popup is None or not panel._completion_popup.isVisible()


# --- NEW./OLD. inside an attached trigger function (row 2) -------------------
def _trigger_function_ref():
    return DdlObjectRef(kind="function", schema="pr", name="audit_log", arg_types=())


def test_ctrl_space_new_dot_offers_attached_trigger_table_columns(qtbot):
    text = "BEGIN\n  IF new."
    panel = _panel(qtbot, ref=_trigger_function_ref(), text=text, schema_index=_index())
    _put_caret_after(panel, "new.")
    _ctrl_space(panel)
    popup = panel._completion_popup
    assert popup is not None and popup.isVisible()
    assert popup.visible_keys() == ["id", "tag"]


def test_ctrl_space_old_dot_offers_attached_trigger_table_columns(qtbot):
    text = "BEGIN\n  IF old.ta"
    panel = _panel(qtbot, ref=_trigger_function_ref(), text=text, schema_index=_index())
    _put_caret_after(panel, "ta")
    _ctrl_space(panel)
    popup = panel._completion_popup
    assert popup.visible_keys() == ["tag"]


def test_choosing_attached_column_inserts_it(qtbot):
    text = "BEGIN\n  IF new.ta"
    panel = _panel(qtbot, ref=_trigger_function_ref(), text=text, schema_index=_index())
    _put_caret_after(panel, "ta")
    _ctrl_space(panel)
    panel._completion_popup.chosen.emit("tag")
    assert panel.text() == "BEGIN\n  IF new.tag"


def test_ctrl_space_new_dot_on_a_trigger_object_itself_uses_its_own_table(qtbot):
    """Editing the TRIGGER object directly (not its function) already knows
    its own target table via `DdlObjectRef.table` -- no reverse lookup or
    unattached-trigger prompt needed."""
    ref = DdlObjectRef(kind="trigger", schema="pr", name="trg_audit", table="equipment")
    text = "CREATE TRIGGER trg_audit ... BEGIN new."
    panel = _panel(qtbot, ref=ref, text=text, schema_index=_index())
    _put_caret_after(panel, "new.")
    _ctrl_space(panel)
    popup = panel._completion_popup
    assert popup is not None and popup.isVisible()
    assert popup.visible_keys() == ["id", "tag"]


# --- NEW./OLD. inside an unattached trigger function (row 3) -----------------
def _unattached_function_ref():
    return DdlObjectRef(kind="function", schema="pr", name="unattached", arg_types=())


def test_ctrl_space_new_dot_unattached_prompts_table_pick(qtbot, monkeypatch):
    calls = []

    def fake_get_item(parent, title, label, items, current, editable):
        calls.append((title, list(items)))
        return "pr.equipment", True

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(fake_get_item))

    text = "BEGIN\n  IF new."
    panel = _panel(qtbot, ref=_unattached_function_ref(), text=text, schema_index=_index())
    _put_caret_after(panel, "new.")
    _ctrl_space(panel)

    assert len(calls) == 1
    title, options = calls[0]
    assert "No Trigger" in title or "trigger" in title.lower()
    assert options == ["hr.employee", "pr.eq_view", "pr.equipment"]

    popup = panel._completion_popup
    assert popup is not None and popup.isVisible()
    assert popup.visible_keys() == ["id", "tag"]


def test_unattached_trigger_pick_is_remembered_for_the_rest_of_the_session(qtbot, monkeypatch):
    """Second Ctrl+Space in the same tab does not prompt again."""
    calls = []

    def fake_get_item(parent, title, label, items, current, editable):
        calls.append(1)
        return "hr.employee", True

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(fake_get_item))

    text = "BEGIN\n  IF new.\n  IF old."
    panel = _panel(qtbot, ref=_unattached_function_ref(), text=text, schema_index=_index())

    _put_caret_after(panel, "IF new.")
    _ctrl_space(panel)
    assert len(calls) == 1
    assert panel._completion_popup.visible_keys() == ["name"]

    _put_caret_after(panel, "IF old.")
    _ctrl_space(panel)
    assert len(calls) == 1  # not prompted again
    assert panel._completion_popup.visible_keys() == ["name"]


def test_unattached_trigger_pick_cancelled_shows_no_popup(qtbot, monkeypatch):
    def fake_get_item(parent, title, label, items, current, editable):
        return "", False  # user cancelled

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(fake_get_item))

    text = "BEGIN\n  IF new."
    panel = _panel(qtbot, ref=_unattached_function_ref(), text=text, schema_index=_index())
    _put_caret_after(panel, "new.")
    _ctrl_space(panel)

    assert panel._completion_popup is None or not panel._completion_popup.isVisible()
    assert panel._unattached_trigger_table is None


def test_unattached_trigger_association_is_never_persisted(qtbot, monkeypatch):
    """§18.6: the pick lives only in the panel's in-memory attribute -- never
    written to settings.json, a sidecar file, or anywhere else on disk. This
    test pins that by asserting there is no save/persist call anywhere in the
    pick path: the panel exposes it only via the plain Python attribute, and
    a fresh panel for the same object starts with no association at all."""

    def fake_get_item(parent, title, label, items, current, editable):
        return "pr.equipment", True

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(fake_get_item))

    text = "BEGIN\n  IF new."
    ref = _unattached_function_ref()
    panel = _panel(qtbot, ref=ref, text=text, schema_index=_index())
    _put_caret_after(panel, "new.")
    _ctrl_space(panel)
    assert panel._unattached_trigger_table == "pr.equipment"

    # A brand new tab/panel for the SAME object starts fresh -- nothing durable
    # carried the association across panel instances (simulates tab close +
    # reopen, or an app restart).
    fresh_panel = _panel(qtbot, ref=ref, text=text, schema_index=_index())
    assert fresh_panel._unattached_trigger_table is None


def test_unattached_trigger_prompt_skipped_when_no_tables_to_pick(qtbot, monkeypatch):
    """No tables anywhere in the injected index (e.g. an empty/unreachable
    schema) -- `_prompt_unattached_trigger_table` has nothing to offer, so it
    must not open the modal `QInputDialog.getItem` at all."""
    calls = []

    def fake_get_item(parent, title, label, items, current, editable):
        calls.append(1)
        return "", False

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(fake_get_item))

    empty_index = SchemaIndex(DatabaseSchema())
    text = "BEGIN\n  IF new."
    panel = _panel(qtbot, ref=_unattached_function_ref(), text=text, schema_index=empty_index)
    _put_caret_after(panel, "new.")
    _ctrl_space(panel)

    assert calls == []
    assert panel._unattached_trigger_table is None
    assert panel._completion_popup is None or not panel._completion_popup.isVisible()


# --- Insertion marks the buffer dirty (§18.5's dirty-tracking contract) ------
def test_choosing_a_completion_marks_the_panel_dirty(qtbot):
    """Completion insertion is a real edit like any other -- it must flip the
    clean->dirty transition (and its `dirty_changed` signal, §18.5) exactly
    like typed input does, not bypass it via some non-tracked text-insertion
    path."""
    panel = _panel(qtbot, text="select * from pr.equ", schema_index=_index())
    assert panel.is_dirty() is False
    seen = []
    panel.dirty_changed.connect(seen.append)

    _put_caret_after(panel, "equ")
    _ctrl_space(panel)
    panel._completion_popup.chosen.emit("equipment")

    assert panel.is_dirty() is True
    assert seen == [True]
