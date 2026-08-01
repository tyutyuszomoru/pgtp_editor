from pgtp_editor.db.ddl_buffer import build_ddl_text
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo, TriggerInfo
from pgtp_editor.ui.ddl_buffer_panel import BrowserPanel

# DatabaseSchema is used directly (not just via _schema()) in several tests
# below to exercise empty/dangling-reference/cross-schema edge cases.


def _schema():
    routines = {
        "pr.calc_total": RoutineInfo(
            schema="pr", name="calc_total", arg_types=["integer"],
            return_type="numeric", language="plpgsql", source="body1", kind="function",
        ),
        "pr.audit_log": RoutineInfo(
            schema="pr", name="audit_log", arg_types=[], return_type="trigger",
            language="plpgsql", source="body2", kind="function",
        ),
    }
    triggers = {
        "pr.equipment.trg_audit": TriggerInfo(
            schema="pr", table="equipment", name="trg_audit", timing="after",
            events=["insert", "update"], function_name="audit_log", definition="def1",
        ),
        "pr.equipment.trg_other": TriggerInfo(
            schema="pr", table="equipment", name="trg_other", timing="before",
            events=["delete"], function_name="unrelated_fn", definition="def2",
        ),
    }
    return DatabaseSchema(routines=routines, triggers=triggers)


def test_set_schema_builds_tables_and_routines_top_level_groups(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()
    _, spans = build_ddl_text(schema)

    panel.set_schema(schema, spans)

    assert panel.tree.topLevelItemCount() == 2
    assert panel.tree.topLevelItem(0).text(0) == "Tables"
    assert panel.tree.topLevelItem(1).text(0) == "Functions & Procedures"


def test_tables_branch_groups_triggers_under_their_table():
    panel = BrowserPanel()
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    tables_root = panel.tree.topLevelItem(0)
    assert tables_root.childCount() == 1
    table_item = tables_root.child(0)
    assert table_item.text(0) == "pr.equipment  (2)"
    trigger_names = sorted(table_item.child(i).text(0) for i in range(table_item.childCount()))
    assert table_item.childCount() == 2
    assert any("trg_audit" in name for name in trigger_names)
    assert any("trg_other" in name for name in trigger_names)


def test_routines_branch_lists_functions_with_marker_and_calling_triggers():
    panel = BrowserPanel()
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    routines_root = panel.tree.topLevelItem(1)
    assert routines_root.childCount() == 2  # audit_log, calc_total (sorted by name)
    audit_log_item = routines_root.child(0)
    assert audit_log_item.text(0) == "audit_log()  [F]"
    assert audit_log_item.childCount() == 1  # only trg_audit calls audit_log
    assert "trg_audit" in audit_log_item.child(0).text(0)
    assert "on equipment" in audit_log_item.child(0).text(0)

    calc_total_item = routines_root.child(1)
    assert calc_total_item.text(0) == "calc_total(integer)  [F]"
    assert calc_total_item.childCount() == 0  # nothing calls calc_total


def test_trigger_appears_as_two_leaves_pointing_at_the_same_span():
    panel = BrowserPanel()
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    table_item = panel.tree.topLevelItem(0).child(0)
    trigger_leaf_under_table = next(
        table_item.child(i) for i in range(table_item.childCount())
        if "trg_audit" in table_item.child(i).text(0)
    )
    routine_item = panel.tree.topLevelItem(1).child(0)  # audit_log
    trigger_leaf_under_routine = routine_item.child(0)

    from PySide6.QtCore import Qt
    span_a = trigger_leaf_under_table.data(0, Qt.ItemDataRole.UserRole)
    span_b = trigger_leaf_under_routine.data(0, Qt.ItemDataRole.UserRole)
    assert span_a is not None
    assert span_a == span_b


def test_click_on_leaf_emits_navigate_requested_with_start_line(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    routine_item = panel.tree.topLevelItem(1).child(1)  # calc_total
    got = []
    panel.navigate_requested.connect(got.append)

    panel._on_item_clicked(routine_item, 0)

    expected_span = next(s for s in spans if s.name == "calc_total")
    assert got == [expected_span.start_line]


def test_click_on_group_header_emits_nothing(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    got = []
    panel.navigate_requested.connect(got.append)
    panel._on_item_clicked(panel.tree.topLevelItem(0), 0)  # "Tables" header

    assert got == []


def test_set_schema_is_idempotent_and_clears_previous_tree(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()
    _, spans = build_ddl_text(schema)

    panel.set_schema(schema, spans)
    panel.set_schema(schema, spans)

    assert panel.tree.topLevelItemCount() == 2


def test_set_schema_on_empty_schema_still_builds_both_empty_groups(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(DatabaseSchema(), [])

    assert panel.tree.topLevelItemCount() == 2
    assert panel.tree.topLevelItem(0).text(0) == "Tables"
    assert panel.tree.topLevelItem(0).childCount() == 0
    assert panel.tree.topLevelItem(1).text(0) == "Functions & Procedures"
    assert panel.tree.topLevelItem(1).childCount() == 0


def test_trigger_with_no_matching_routine_still_appears_under_its_table_only():
    """A trigger whose function_name matches nothing in schema.routines (e.g.
    the function was dropped, or lives in a different schema than the
    trigger) must not crash tree-building and must simply be absent from the
    Functions & Procedures branch (best-effort matching, §18.1)."""
    schema = DatabaseSchema(
        triggers={
            "pr.equipment.trg_orphan": TriggerInfo(
                schema="pr", table="equipment", name="trg_orphan", timing="after",
                events=["insert"], function_name="no_such_function", definition="def",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    panel.set_schema(schema, spans)

    tables_root = panel.tree.topLevelItem(0)
    assert tables_root.childCount() == 1
    assert "trg_orphan" in tables_root.child(0).child(0).text(0)

    routines_root = panel.tree.topLevelItem(1)
    assert routines_root.childCount() == 0


def test_function_name_matching_is_scoped_to_the_same_schema():
    """A trigger's bare function_name must only match a routine in the SAME
    schema -- a same-named routine in a different schema is not a match
    (best-effort, no cross-schema false positives, §18.1)."""
    schema = DatabaseSchema(
        routines={
            "other.audit_log": RoutineInfo(
                schema="other", name="audit_log", arg_types=[], return_type="trigger",
                language="plpgsql", source="CREATE FUNCTION other.audit_log() ...",
                kind="function",
            ),
        },
        triggers={
            "pr.equipment.trg_x": TriggerInfo(
                schema="pr", table="equipment", name="trg_x", timing="after",
                events=["insert"], function_name="audit_log", definition="def",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    panel.set_schema(schema, spans)

    routine_item = panel.tree.topLevelItem(1).child(0)
    assert routine_item.text(0) == "audit_log()  [F]"
    assert routine_item.childCount() == 0


def test_click_on_functions_group_header_emits_nothing(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    got = []
    panel.navigate_requested.connect(got.append)
    panel._on_item_clicked(panel.tree.topLevelItem(1), 0)  # "Functions & Procedures"

    assert got == []


def test_click_on_routine_with_no_span_emits_nothing(qtbot):
    """A routine that has no corresponding DdlObjectSpan (e.g. the caller
    passed a schema/spans pair that got out of sync) must not raise and must
    simply not navigate -- defensive against a None span lookup."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()

    panel.set_schema(schema, [])  # no spans at all

    got = []
    panel.navigate_requested.connect(got.append)
    routines_root = panel.tree.topLevelItem(1)
    panel._on_item_clicked(routines_root.child(0), 0)

    assert got == []


def test_routine_with_no_calling_triggers_has_no_children(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = DatabaseSchema(
        routines={
            "pr.lonely": RoutineInfo(
                schema="pr", name="lonely", arg_types=[], return_type="void",
                language="sql", source="CREATE FUNCTION pr.lonely() ...", kind="function",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    routines_root = panel.tree.topLevelItem(1)
    assert routines_root.childCount() == 1
    assert routines_root.child(0).childCount() == 0
