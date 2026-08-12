from pgtp_editor.db.ddl_buffer import DdlObjectSpan, build_ddl_text
from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, RoutineInfo, TableInfo, TriggerInfo
from pgtp_editor.ui.ddl_buffer_panel import (
    ALTER_TABLE_ACTIONS,
    ALTER_TABLE_COLUMN_ACTIONS,
    ALTER_TABLE_COLUMN_COMMENT_ACTIONS,
    ALTER_TABLE_CONSTRAINT_ACTIONS,
    ALTER_TABLE_DROP_TABLE_ACTIONS,
    ALTER_TABLE_INDEX_ACTIONS,
    ALTER_TABLE_MENU_TITLE,
    ALTER_TABLE_TABLE_COMMENT_ACTIONS,
    CREATE_TABLE_LABEL,
    DISCARD_LOCAL_LABEL,
    RELOAD_LABEL,
    BrowserPanel,
    alter_table_action_groups,
    edit_refusal_for_span,
    resolve_edit_target,
)
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
# Imported from the dialog, not re-typed: the panel shows the dialog's own
# sentence, and a second spelling here would let the two drift (DEC-260811025733).
from pgtp_editor.ui.new_trigger_dialog import NO_TRIGGERS_MESSAGE

# DatabaseSchema is used directly (not just via _schema()) in several tests
# below to exercise empty/dangling-reference/cross-schema edge cases.


def _schema():
    routines = {
        "pr.calc_total(integer, numeric)": RoutineInfo(
            schema="pr", name="calc_total", arg_types=["integer", "numeric"],
            return_type="numeric", language="plpgsql", source="body1", kind="function",
            args=[("item_id", "integer"), ("rate", "numeric")],
        ),
        "pr.audit_log()": RoutineInfo(
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
    assert trigger_names == [
        "pr.equipment.trg_audit [A][I][U]",
        "pr.equipment.trg_other [B][D]",
    ]


def test_routines_branch_lists_functions_with_marker_and_calling_triggers():
    panel = BrowserPanel()
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    routines_root = panel.tree.topLevelItem(1)
    assert routines_root.childCount() == 2  # audit_log, calc_total (sorted by name)
    audit_log_item = routines_root.child(0)
    # zero-arg trigger function -> empty parens + [T]
    assert audit_log_item.text(0) == "pr.audit_log() [T]"
    assert audit_log_item.childCount() == 1  # only trg_audit calls audit_log
    assert audit_log_item.child(0).text(0) == "pr.equipment.trg_audit [A][I][U]"

    calc_total_item = routines_root.child(1)
    # has input args -> no parens on the top line, one child leaf per arg
    assert calc_total_item.text(0) == "pr.calc_total [F]"
    assert [
        calc_total_item.child(i).text(0) for i in range(calc_total_item.childCount())
    ] == ["item_id (integer)", "rate (numeric)"]  # nothing calls calc_total


def test_procedure_gets_p_marker():
    schema = DatabaseSchema(
        routines={
            "pr.do_it": RoutineInfo(
                schema="pr", name="do_it", arg_types=[], return_type=None,
                language="plpgsql", source="body", kind="procedure",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    panel.set_schema(schema, spans)

    assert panel.tree.topLevelItem(1).child(0).text(0) == "pr.do_it() [P]"


def test_worked_example_function_with_args():
    """Spec §18.1 worked example -- must reproduce exactly."""
    schema = DatabaseSchema(
        routines={
            "public.get_working_days_in_month": RoutineInfo(
                schema="public", name="get_working_days_in_month",
                arg_types=["integer", "integer"], return_type="integer",
                language="plpgsql", source="body", kind="function",
                args=[("year", "integer"), ("month", "integer")],
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    panel.set_schema(schema, spans)

    item = panel.tree.topLevelItem(1).child(0)
    assert item.text(0) == "public.get_working_days_in_month [F]"
    assert item.childCount() == 2
    assert item.child(0).text(0) == "year (integer)"
    assert item.child(1).text(0) == "month (integer)"


def test_worked_example_trigger_function_with_its_trigger():
    """Spec §18.1 worked example -- must reproduce exactly."""
    schema = DatabaseSchema(
        routines={
            "public.dont_delete_standards": RoutineInfo(
                schema="public", name="dont_delete_standards", arg_types=[],
                return_type="trigger", language="plpgsql", source="body",
                kind="function",
            ),
        },
        triggers={
            "public.phpgen_users.dont_delete_model_users": TriggerInfo(
                schema="public", table="phpgen_users",
                name="dont_delete_model_users", timing="before",
                events=["delete"], function_name="dont_delete_standards",
                definition="def",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    panel.set_schema(schema, spans)

    item = panel.tree.topLevelItem(1).child(0)
    assert item.text(0) == "public.dont_delete_standards() [T]"
    assert item.childCount() == 1
    assert item.child(0).text(0) == "public.phpgen_users.dont_delete_model_users [B][D]"


def test_instead_of_and_truncate_indicators():
    schema = DatabaseSchema(
        triggers={
            "pr.v_x.trg_io": TriggerInfo(
                schema="pr", table="v_x", name="trg_io", timing="instead of",
                events=["insert", "update", "delete", "truncate"],
                function_name="fn", definition="def",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    panel.set_schema(schema, spans)

    leaf = panel.tree.topLevelItem(0).child(0).child(0)
    assert leaf.text(0) == "pr.v_x.trg_io [I][I][U][D][T]"


def test_argument_leaf_is_not_a_navigation_target(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    calc_total_item = panel.tree.topLevelItem(1).child(1)
    got = []
    panel.navigate_requested.connect(got.append)
    panel._on_item_clicked(calc_total_item.child(0), 0)  # "item_id (integer)"

    assert got == []


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
    assert tables_root.child(0).child(0).text(0) == "pr.equipment.trg_orphan [A][I]"

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
    assert routine_item.text(0) == "other.audit_log() [T]"
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


# --- Argument children alongside calling triggers (§18.1 tree presentation) --


def _trigger_function_with_args_and_callers():
    """A trigger function that takes arguments (legal: `CREATE TRIGGER ...
    EXECUTE FUNCTION f('a', 'b')`) AND is invoked by two triggers -- the one
    routine node that carries both kinds of child."""
    routines = {
        "pr.audit": RoutineInfo(
            schema="pr", name="audit", arg_types=["text", "text"],
            return_type="trigger", language="plpgsql", source="body",
            kind="function", args=[("table_label", "text"), ("mode", "text")],
        ),
    }
    triggers = {
        "pr.orders.trg_b": TriggerInfo(
            schema="pr", table="orders", name="trg_b", timing="after",
            events=["insert"], function_name="audit", definition="def_b",
        ),
        "pr.items.trg_a": TriggerInfo(
            schema="pr", table="items", name="trg_a", timing="before",
            events=["update"], function_name="audit", definition="def_a",
        ),
    }
    return DatabaseSchema(routines=routines, triggers=triggers)


def test_routine_lists_argument_children_before_calling_triggers(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _trigger_function_with_args_and_callers()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    routine_item = panel.tree.topLevelItem(1).child(0)
    assert routine_item.text(0) == "pr.audit [T]"  # has args -> no parens
    labels = [routine_item.child(i).text(0) for i in range(routine_item.childCount())]
    assert labels == [
        "table_label (text)",       # declared order, args first
        "mode (text)",
        "pr.items.trg_a [B][U]",    # then calling triggers, sorted by name
        "pr.orders.trg_b [A][I]",
    ]


def test_only_the_trigger_children_of_a_routine_navigate(qtbot):
    """Arg leaves carry no span; the trigger leaves under the same routine
    still jump to their own span."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _trigger_function_with_args_and_callers()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)
    trigger_span = {(s.schema, s.table, s.name): s for s in spans if s.kind == "trigger"}

    routine_item = panel.tree.topLevelItem(1).child(0)
    got = []
    panel.navigate_requested.connect(got.append)
    for index in range(routine_item.childCount()):
        panel._on_item_clicked(routine_item.child(index), 0)

    assert got == [
        trigger_span[("pr", "items", "trg_a")].start_line,
        trigger_span[("pr", "orders", "trg_b")].start_line,
    ]


def test_unnamed_argument_renders_with_an_empty_name(qtbot):
    """`CREATE FUNCTION f(integer)` -- Postgres gives no name; the leaf still
    renders its type and stays a non-navigating label."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = DatabaseSchema(
        routines={
            "pr.unnamed": RoutineInfo(
                schema="pr", name="unnamed", arg_types=["integer"],
                return_type="integer", language="sql", source="body",
                kind="function", args=[("", "integer")],
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    routine_item = panel.tree.topLevelItem(1).child(0)
    assert routine_item.text(0) == "pr.unnamed [F]"  # args present -> no parens
    assert routine_item.childCount() == 1
    assert routine_item.child(0).text(0) == " (integer)"


def test_out_only_routine_renders_as_a_zero_input_routine(qtbot):
    """`arg_types` (banner) can be non-empty while `args` is empty (OUT-only
    signature). The tree keys off `args`, so this shows the empty parens."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = DatabaseSchema(
        routines={
            "pr.stats": RoutineInfo(
                schema="pr", name="stats", arg_types=["integer"],
                return_type="record", language="plpgsql", source="body",
                kind="function", args=[],
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    routine_item = panel.tree.topLevelItem(1).child(0)
    assert routine_item.text(0) == "pr.stats() [F]"
    assert routine_item.childCount() == 0


def test_procedure_marker_wins_over_trigger_return_type(qtbot):
    """The marker table is evaluated in order: kind == "procedure" -> [P]
    before the return_type == "trigger" -> [T] rule."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = DatabaseSchema(
        routines={
            "pr.odd": RoutineInfo(
                schema="pr", name="odd", arg_types=[], return_type="trigger",
                language="plpgsql", source="body", kind="procedure",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    assert panel.tree.topLevelItem(1).child(0).text(0) == "pr.odd() [P]"


def test_routine_top_line_navigates_to_its_own_span(qtbot):
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)
    by_name = {s.name: s for s in spans}

    got = []
    panel.navigate_requested.connect(got.append)
    routines_root = panel.tree.topLevelItem(1)
    panel._on_item_clicked(routines_root.child(1), 0)  # pr.calc_total

    assert got == [by_name["calc_total"].start_line]
    banner = text.splitlines()[by_name["calc_total"].start_line - 1]
    assert banner == "-- FUNCTION pr.calc_total(integer, numeric) --"


def test_rebuilding_the_tree_replaces_rather_than_appends(qtbot):
    """set_schema recomputes from scratch every call (no cache of its own)."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)
    panel.set_schema(schema, spans)

    assert panel.tree.topLevelItemCount() == 2
    assert panel.tree.topLevelItem(1).childCount() == 2
    calc_total = panel.tree.topLevelItem(1).child(1)
    assert calc_total.childCount() == 2  # two args, not four


def test_unknown_timing_or_event_degrades_to_a_question_mark(qtbot):
    """Defensive: an unrecognised timing/event string must render a marker,
    not raise -- the same 'no silent surprise' posture as _decode_trigger_type."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = DatabaseSchema(
        triggers={
            "pr.t.weird": TriggerInfo(
                schema="pr", table="t", name="weird", timing="sideways",
                events=["levitate"], function_name="fn", definition="def",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    leaf = panel.tree.topLevelItem(0).child(0).child(0)
    assert leaf.text(0) == "pr.t.weird [?][?]"


def test_trigger_with_no_events_renders_timing_only(qtbot):
    """_decode_trigger_type can yield an empty event list (tgtype with no
    event bits) -- the label then carries just the timing bracket."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = DatabaseSchema(
        triggers={
            "pr.t.bare": TriggerInfo(
                schema="pr", table="t", name="bare", timing="before",
                events=[], function_name="fn", definition="def",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    assert panel.tree.topLevelItem(0).child(0).child(0).text(0) == "pr.t.bare [B]"


def test_both_trigger_leaves_carry_the_identical_composite_label(qtbot):
    """§18.1: the composite label is used in BOTH branches -- the old
    'on table' / '→ function' split is gone."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    table_leaf = panel.tree.topLevelItem(0).child(0).child(0)
    routine_leaf = panel.tree.topLevelItem(1).child(0).child(0)
    assert table_leaf.text(0) == routine_leaf.text(0) == "pr.equipment.trg_audit [A][I][U]"


# --- Overloads: two routines sharing a schema.name (BUG-018) ----------------


def test_each_overload_gets_its_own_tree_item_and_its_own_span(qtbot):
    """Two overloads must navigate to *different* bodies.

    Keyed on `(schema, name)` the span map gave both tree items the same
    last-wins span, so clicking either one landed on the same routine -- the
    half of BUG-018 that `db/introspect.py` alone does not fix.
    """
    routines = {}
    for arg in ("integer", "text"):
        routine = RoutineInfo(
            schema="pr", name="fmt", arg_types=[arg], return_type="text",
            language="plpgsql", source=f"BODY-{arg}", kind="function",
            args=[("v", arg)],
        )
        routines[routine.signature] = routine
    schema = DatabaseSchema(routines=routines)

    from PySide6.QtCore import Qt

    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    routines_root = panel.tree.topLevelItem(1)
    assert routines_root.childCount() == 2

    items = [routines_root.child(i) for i in range(2)]
    item_spans = [item.data(0, Qt.ItemDataRole.UserRole) for item in items]
    assert all(span is not None for span in item_spans)
    # Distinct spans -- and each points at that overload's own body.
    assert item_spans[0].start_line != item_spans[1].start_line
    lines = text.splitlines()
    bodies = [lines[s.start_line: s.end_line] for s in item_spans]
    assert bodies == [["BODY-integer"], ["BODY-text"]]
    # Argument leaves still disambiguate the two identically-labelled items.
    assert [item.text(0) for item in items] == ["pr.fmt [F]", "pr.fmt [F]"]
    assert [item.child(0).text(0) for item in items] == ["v (integer)", "v (text)"]


# --- Right-click ▸ Edit… (spec §18.5, D1 entry point 1) ---------------------
def _routine_item(panel):
    """The `calc_total` routine row from `_schema()` (sorted after audit_log)."""
    routines_root = panel.tree.topLevelItem(1)
    return routines_root.child(1)


def _trigger_leaf_under_table(panel):
    tables_root = panel.tree.topLevelItem(0)
    table_item = tables_root.child(0)  # pr.equipment
    return table_item.child(0)  # trg_audit (sorted by name)


def test_edit_requested_carries_a_ref_and_the_live_source_for_a_routine(qtbot):
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    from PySide6.QtCore import Qt

    item = _routine_item(panel)
    got = []
    panel.edit_requested.connect(lambda ref, source: got.append((ref, source)))

    span = item.data(0, Qt.ItemDataRole.UserRole)
    ref, source = resolve_edit_target(panel._schema, span)
    panel.edit_requested.emit(ref, source)

    assert got == [(ref, source)]
    assert ref.kind == "function"
    assert ref.schema == "pr"
    assert ref.name == "calc_total"
    assert ref.arg_types == ("integer", "numeric")
    assert ref.disambiguate is False  # sole holder of pr.calc_total
    assert source == "body1"


def test_edit_target_marks_an_overloaded_routine_for_disambiguation(qtbot):
    routines = {}
    for arg in ("integer", "text"):
        routine = RoutineInfo(
            schema="pr", name="fmt", arg_types=[arg], return_type="text",
            language="plpgsql", source=f"BODY-{arg}", kind="function",
        )
        routines[routine.signature] = routine
    schema = DatabaseSchema(routines=routines)
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    from PySide6.QtCore import Qt

    item = panel.tree.topLevelItem(1).child(0)
    span = item.data(0, Qt.ItemDataRole.UserRole)

    ref, source = resolve_edit_target(panel._schema, span)

    assert ref.disambiguate is True
    assert ref.arg_types == ("integer",)


def test_edit_target_for_a_trigger(qtbot):
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    item = _trigger_leaf_under_table(panel)
    from PySide6.QtCore import Qt

    span = item.data(0, Qt.ItemDataRole.UserRole)

    ref, source = resolve_edit_target(panel._schema, span)

    assert ref.kind == "trigger"
    assert ref.schema == "pr"
    assert ref.table == "equipment"
    assert ref.name == "trg_audit"
    assert source == "def1"


def test_context_menu_on_an_argument_leaf_offers_no_edit(qtbot):
    """Argument-name child leaves carry no span -- no Edit… entry (§18.5).

    Since BUG-062 such a leaf DOES get a menu: `Reload DDL` is offered wherever
    the click lands, because it is a property of the connection and not of the
    clicked row. What must stay true is that no editing entry appears -- asserted
    through `context_menu_for_item` rather than `_on_context_menu`, which would
    reach a real `QMenu.exec`."""
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    from PySide6.QtCore import Qt

    arg_leaf = _routine_item(panel).child(0)  # "item_id (integer)"
    assert arg_leaf.data(0, Qt.ItemDataRole.UserRole) is None

    assert panel._menu_for_item(arg_leaf) is None  # nothing this ITEM offers
    labels = [a.text() for a in panel.context_menu_for_item(arg_leaf).actions()]
    assert labels == [RELOAD_LABEL]


def test_context_menu_at_empty_position_offers_only_reload(qtbot):
    """A right-click below the last row used to offer nothing at all. BUG-062
    requires `Reload DDL` "wherever in DDL Objects", which includes the blank
    area -- and still nothing else, since there is no item to act on."""
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    got = []
    panel.edit_requested.connect(lambda *a: got.append(a))

    labels = [a.text() for a in panel.context_menu_for_item(None).actions()]

    assert labels == [RELOAD_LABEL]
    assert got == []


def test_edit_menu_action_triggers_edit_requested(qtbot, monkeypatch):
    """The actual right-click ▸ Edit DDL menu path, end to end -- QMenu itself is
    faked (the established `_FakeMenu` convention, see
    test_caption_management_panel.py) so no real popup blocks the test."""
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    got = []
    panel.edit_requested.connect(lambda ref, source: got.append((ref, source)))

    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QTreeWidget

    captured = {"actions": []}

    class _FakeMenu:
        def __init__(self, *a, **k):
            pass

        def addAction(self, label, cb=None):
            captured["actions"].append((label, cb))

        def addSeparator(self):
            # BUG-062 puts `Reload DDL` below a separator on every menu of this
            # tree, so the fake has to accept one.
            captured["actions"].append(("--", None))

        def exec(self, *a, **k):
            # The real menu only ever triggers the ONE action the user
            # clicked; simulate clicking "Edit DDL" specifically.
            for label, cb in captured["actions"]:
                if label.startswith("Edit DDL"):
                    cb()
                    return

    monkeypatch.setattr("pgtp_editor.ui.ddl_buffer_panel.QMenu", _FakeMenu)
    item = _routine_item(panel)
    monkeypatch.setattr(QTreeWidget, "itemAt", lambda self, pos: item)

    panel._on_context_menu(QPoint(0, 0))  # position is irrelevant, itemAt is patched

    # ONE editing entry since FQ-024: `Check Out for Versioning` is withdrawn,
    # and the row already names the object so the entry does not repeat it. The
    # separator + `Reload DDL` below it are BUG-062's connection-level gesture,
    # offered on every menu of this tree.
    labels = [label for label, _cb in captured["actions"]]
    assert labels == ["Edit DDL", "--", RELOAD_LABEL]
    assert len(got) == 1
    ref, source = got[0]
    assert ref.name == "calc_total"
    assert source == "body1"


# --- BUG-062: Reload DDL, wherever in the tree -------------------------------


def test_reload_is_offered_on_an_object_row_and_emits_the_signal(qtbot):
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    got = []
    panel.reload_requested.connect(lambda: got.append(True))

    menu = panel.context_menu_for_item(_routine_item(panel))
    reload_action = [a for a in menu.actions() if a.text() == RELOAD_LABEL][0]
    reload_action.trigger()

    assert got == [True]


def test_reload_is_the_only_entry_a_browse_only_tree_offers(qtbot):
    """§18.7's sandbox tree suppresses every edit/create gesture, which left it
    with no menu at all. Reload is neither an edit nor a creation, and it is the
    gesture a sandbox browse needs most (BUG-062)."""
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel(browse_only=True)
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    got = []
    panel.reload_requested.connect(lambda: got.append(True))

    menu = panel.context_menu_for_item(_routine_item(panel))

    assert [a.text() for a in menu.actions()] == [RELOAD_LABEL]
    menu.actions()[0].trigger()
    assert got == [True]


def test_the_reload_entry_carries_no_shortcut(qtbot):
    """DEC-012: Reload DDL has exactly ONE keyboard host, the `Ctrl+Shift+R`
    QShortcut on the Explorer's viewing pane. Every menu form is click-only, and
    this is the invariant a future edit would break silently."""
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    menu = panel.context_menu_for_item(_routine_item(panel))

    reload_action = [a for a in menu.actions() if a.text() == RELOAD_LABEL][0]
    assert reload_action.shortcut().isEmpty()


def test_the_object_row_menu_has_no_checkout_entry_or_signal(qtbot):
    """FQ-024: the withdrawn gesture is gone from the menu AND the panel no
    longer declares the signal it emitted, so no host can re-wire it."""
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    menu = panel._menu_for_item(_routine_item(panel))

    assert [a.text() for a in menu.actions()] == ["Edit DDL"]
    assert not hasattr(panel, "checkout_requested")


# --- BUG-260810193333: Discard local change ----------------------------------


def _panel_with_schema(qtbot, **kwargs):
    schema = _schema()
    _text, spans = build_ddl_text(schema)
    panel = BrowserPanel(**kwargs)
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    return panel


def test_discard_local_is_absent_when_nothing_is_checked_out(qtbot):
    """No predicate injected (projectless) means no local working copy exists,
    so the entry is ABSENT rather than selectable-and-explaining."""
    panel = _panel_with_schema(qtbot)

    menu = panel._menu_for_item(_routine_item(panel))

    assert [a.text() for a in menu.actions()] == ["Edit DDL"]


def test_discard_local_is_offered_beside_edit_ddl_for_a_checked_out_object(qtbot):
    panel = _panel_with_schema(qtbot)
    panel.set_checked_out_predicate(lambda ref: True)
    got = []
    panel.discard_local_requested.connect(got.append)

    menu = panel._menu_for_item(_routine_item(panel))

    assert [a.text() for a in menu.actions()] == ["Edit DDL", DISCARD_LOCAL_LABEL]
    menu.actions()[1].trigger()
    assert len(got) == 1
    assert got[0].name == "calc_total"


def test_discard_local_is_offered_per_object_not_per_tree(qtbot):
    """The predicate is asked with the row's own ref, so a checked-out routine
    offers it and its neighbour does not."""
    panel = _panel_with_schema(qtbot)
    panel.set_checked_out_predicate(lambda ref: ref.name == "calc_total")

    routines_root = panel.tree.topLevelItem(1)
    offered = panel._menu_for_item(routines_root.child(1))
    other = panel._menu_for_item(routines_root.child(0))

    assert DISCARD_LOCAL_LABEL in [a.text() for a in offered.actions()]
    assert DISCARD_LOCAL_LABEL not in [a.text() for a in other.actions()]


def test_discard_local_is_never_offered_on_the_browse_only_tree(qtbot):
    """§18.7's sandbox Explorer: discard is an edit gesture, and the sandbox
    tree offers none -- even with a predicate wired that says yes."""
    panel = _panel_with_schema(qtbot, browse_only=True)
    panel.set_checked_out_predicate(lambda ref: True)

    assert panel._menu_for_item(_routine_item(panel)) is None
    labels = [a.text() for a in panel.context_menu_for_item(_routine_item(panel)).actions()]
    assert labels == [RELOAD_LABEL]


def test_discard_local_carries_no_shortcut(qtbot):
    """DEC-012 / KEYBINDINGS.md: this is a context-menu-only command; no chord
    is reserved for it, so the action must not claim one."""
    panel = _panel_with_schema(qtbot)
    panel.set_checked_out_predicate(lambda ref: True)

    menu = panel._menu_for_item(_routine_item(panel))

    action = [a for a in menu.actions() if a.text() == DISCARD_LOCAL_LABEL][0]
    assert action.shortcut().isEmpty()


def test_a_raising_checked_out_predicate_hides_the_entry_instead_of_the_menu(qtbot):
    """The predicate reads the filesystem while a context menu is being built:
    an unreadable project must cost one entry, never an exception out of a
    right-click -- and hiding a destructive gesture is the safe direction."""
    panel = _panel_with_schema(qtbot)

    def boom(ref):
        raise OSError("project folder went away")

    panel.set_checked_out_predicate(boom)

    menu = panel._menu_for_item(_routine_item(panel))

    assert [a.text() for a in menu.actions()] == ["Edit DDL"]


# --- */! drift markers (spec §18.2) -----------------------------------------
def test_no_markers_when_drift_markers_is_none(qtbot):
    """No project open -- rendering must be identical to before this
    feature existed (no trailing marker text at all)."""
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(schema, spans)  # drift_markers omitted entirely

    calc_total_item = panel.tree.topLevelItem(1).child(1)
    assert calc_total_item.text(0) == "pr.calc_total [F]"


def test_star_marker_rendered_on_a_locally_edited_routine(qtbot):
    from pgtp_editor.db.ddl_project import DriftMarkers

    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(
        schema, spans,
        drift_markers={"ddl/pr.calc_total.sql": DriftMarkers(locally_edited=True)},
    )

    calc_total_item = panel.tree.topLevelItem(1).child(1)
    assert calc_total_item.text(0) == "pr.calc_total [F] *"


def test_bang_marker_rendered_on_a_live_drifted_routine(qtbot):
    from pgtp_editor.db.ddl_project import DriftMarkers

    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(
        schema, spans,
        drift_markers={"ddl/pr.calc_total.sql": DriftMarkers(live_drifted=True)},
    )

    calc_total_item = panel.tree.topLevelItem(1).child(1)
    assert calc_total_item.text(0) == "pr.calc_total [F] !"


def test_both_markers_combine_never_a_third_symbol(qtbot):
    from pgtp_editor.db.ddl_project import DriftMarkers

    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(
        schema, spans,
        drift_markers={
            "ddl/pr.calc_total.sql": DriftMarkers(locally_edited=True, live_drifted=True)
        },
    )

    calc_total_item = panel.tree.topLevelItem(1).child(1)
    assert calc_total_item.text(0) == "pr.calc_total [F] *!"


def test_marker_only_applies_to_the_named_object_not_siblings(qtbot):
    from pgtp_editor.db.ddl_project import DriftMarkers

    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(
        schema, spans,
        drift_markers={"ddl/pr.calc_total.sql": DriftMarkers(locally_edited=True)},
    )

    audit_log_item = panel.tree.topLevelItem(1).child(0)
    assert audit_log_item.text(0) == "pr.audit_log() [T]"  # untouched


def test_marker_rendered_on_a_trigger_leaf_under_its_table(qtbot):
    from pgtp_editor.db.ddl_project import DriftMarkers

    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(
        schema, spans,
        drift_markers={
            "ddl/pr.equipment.trg_audit.sql": DriftMarkers(locally_edited=True)
        },
    )

    table_item = panel.tree.topLevelItem(0).child(0)  # pr.equipment
    trigger_leaf = next(
        table_item.child(i) for i in range(table_item.childCount())
        if "trg_audit" in table_item.child(i).text(0)
    )
    assert trigger_leaf.text(0) == "pr.equipment.trg_audit [A][I][U] *"


def test_marker_rendered_on_a_trigger_leaf_under_its_calling_function(qtbot):
    """Both trigger occurrences (§18.1: table branch + function branch) get
    the same marker -- they point at the same underlying object."""
    from pgtp_editor.db.ddl_project import DriftMarkers

    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(
        schema, spans,
        drift_markers={
            "ddl/pr.equipment.trg_audit.sql": DriftMarkers(live_drifted=True)
        },
    )

    audit_log_item = panel.tree.topLevelItem(1).child(0)
    trigger_leaf = audit_log_item.child(0)
    assert trigger_leaf.text(0) == "pr.equipment.trg_audit [A][I][U] !"


def test_object_with_no_matching_marker_entry_renders_unmarked(qtbot):
    from pgtp_editor.db.ddl_project import DriftMarkers

    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(
        schema, spans,
        drift_markers={"ddl/some.other.sql": DriftMarkers(locally_edited=True)},
    )

    calc_total_item = panel.tree.topLevelItem(1).child(1)
    assert calc_total_item.text(0) == "pr.calc_total [F]"


def test_empty_drift_markers_dict_renders_unmarked(qtbot):
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(schema, spans, drift_markers={})

    calc_total_item = panel.tree.topLevelItem(1).child(1)
    assert calc_total_item.text(0) == "pr.calc_total [F]"


# --- Tables branch widened to every table, plus click-to-Properties --------
# (§18.1, 2026-08-05)


def _table_info(name: str) -> TableInfo:
    return TableInfo(
        name=name,
        kind="table",
        columns=[
            ColumnInfo(
                name="id", data_type="integer", is_pk=True, is_fk=False,
                is_nullable=False, default=None,
            ),
        ],
    )


def test_table_with_no_triggers_gets_a_plain_leaf_node(qtbot):
    """A table in schema.tables that owns zero triggers must still get a
    tree node -- the branch's original under-by-omission scope, now
    completed -- rendered as a bare 'schema.table' label with no children."""
    schema = DatabaseSchema(tables={"pr.widget": _table_info("pr.widget")})
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(schema, spans)

    tables_root = panel.tree.topLevelItem(0)
    assert tables_root.childCount() == 1
    table_item = tables_root.child(0)
    assert table_item.text(0) == "pr.widget"  # no "(N)" suffix
    # Its ONLY child is FQ-025's columns group -- no trigger leaves.
    assert [table_item.child(i).text(0) for i in range(table_item.childCount())] == [
        "Columns  (1)"
    ]


def test_table_with_triggers_keeps_existing_presentation_when_also_in_tables(qtbot):
    """A table present in BOTH schema.tables and schema.triggers keeps its
    current (N)-suffixed/nested presentation unchanged -- the two data
    sources merge on the shared (schema, table) key."""
    schema = DatabaseSchema(
        tables={"pr.equipment": _table_info("pr.equipment")},
        triggers={
            "pr.equipment.trg_audit": TriggerInfo(
                schema="pr", table="equipment", name="trg_audit", timing="after",
                events=["insert"], function_name="audit_log", definition="def",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(schema, spans)

    tables_root = panel.tree.topLevelItem(0)
    assert tables_root.childCount() == 1
    table_item = tables_root.child(0)
    assert table_item.text(0) == "pr.equipment  (1)"
    # Triggers first, then FQ-025's columns group: the branch is about triggers,
    # and the columns must not push them out of view.
    assert [table_item.child(i).text(0) for i in range(table_item.childCount())] == [
        "pr.equipment.trg_audit [A][I]",
        "Columns  (1)",
    ]


def test_tables_branch_unions_schema_tables_and_trigger_only_tables(qtbot):
    """A table that only shows up via schema.triggers (no TableInfo, e.g. a
    caller that populates triggers without tables) must still appear --
    the widening is additive, never a narrowing of prior behavior."""
    schema = DatabaseSchema(
        tables={"pr.widget": _table_info("pr.widget")},
        triggers={
            "pr.equipment.trg_audit": TriggerInfo(
                schema="pr", table="equipment", name="trg_audit", timing="after",
                events=["insert"], function_name="audit_log", definition="def",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(schema, spans)

    tables_root = panel.tree.topLevelItem(0)
    labels = sorted(tables_root.child(i).text(0) for i in range(tables_root.childCount()))
    assert labels == ["pr.equipment  (1)", "pr.widget"]


def test_tables_branch_sorted_by_table_name(qtbot):
    schema = DatabaseSchema(
        tables={
            "pr.zeta": _table_info("pr.zeta"),
            "pr.alpha": _table_info("pr.alpha"),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)

    panel.set_schema(schema, spans)

    tables_root = panel.tree.topLevelItem(0)
    labels = [tables_root.child(i).text(0) for i in range(tables_root.childCount())]
    assert labels == ["pr.alpha", "pr.zeta"]


def test_click_on_table_node_emits_table_selected_with_table_info(qtbot):
    table_info = _table_info("pr.widget")
    schema = DatabaseSchema(tables={"pr.widget": table_info})
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    got = []
    panel.table_selected.connect(got.append)
    table_item = panel.tree.topLevelItem(0).child(0)
    panel._on_item_clicked(table_item, 0)

    assert got == [table_info]


def test_click_on_table_node_navigates_to_its_synthesized_ddl(qtbot):
    """A table node now DOES carry a span (`FQ-260810183812`): the buffer holds
    its synthesized `CREATE TABLE`, and clicking the node jumps to its banner.

    This supersedes the pre-feature assertion that a table click never emitted
    `navigate_requested` -- which held only because tables had no DDL anywhere
    in the app.
    """
    schema = DatabaseSchema(tables={"pr.widget": _table_info("pr.widget")})
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    got = []
    panel.navigate_requested.connect(got.append)
    table_item = panel.tree.topLevelItem(0).child(0)
    panel._on_item_clicked(table_item, 0)

    table_span = next(span for span in spans if span.kind == "table")
    assert got == [table_span.start_line]


def test_click_on_trigger_owning_table_node_still_emits_table_selected(qtbot):
    """A table WITH triggers is still a table node in its own right -- its
    top-level row click emits table_selected.

    Since `FQ-260810183812` the click is ADDITIVE (open question 2, settled
    both-not-either): it ALSO navigates to the table's synthesized DDL. The
    Properties population is the working behaviour that must not be withdrawn
    to buy the jump, so this pins that it survives."""
    table_info = _table_info("pr.equipment")
    schema = DatabaseSchema(
        tables={"pr.equipment": table_info},
        triggers={
            "pr.equipment.trg_audit": TriggerInfo(
                schema="pr", table="equipment", name="trg_audit", timing="after",
                events=["insert"], function_name="audit_log", definition="def",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    got_table = []
    got_navigate = []
    panel.table_selected.connect(got_table.append)
    panel.navigate_requested.connect(got_navigate.append)
    table_item = panel.tree.topLevelItem(0).child(0)
    panel._on_item_clicked(table_item, 0)

    assert got_table == [table_info]
    table_span = next(span for span in spans if span.kind == "table")
    assert got_navigate == [table_span.start_line]


def test_table_with_no_tableinfo_and_no_triggers_never_happens_but_empty_schema_is_safe(qtbot):
    """Defensive: an empty schema still builds the (empty) Tables branch
    without raising."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(DatabaseSchema(), [])
    assert panel.tree.topLevelItem(0).childCount() == 0


def _table_panel(qtbot):
    schema = DatabaseSchema(tables={"pr.widget": _table_info("pr.widget")})
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    return panel


def test_context_menu_on_a_table_node_offers_no_edit(qtbot):
    """A table node still offers NO Edit…/Check Out (§18.1) -- a table is not
    part of §18.2's checkout model, and its shape changes through
    `Alter Table ▸` alone.

    Since `FQ-260810183812` the node DOES carry a `_SPAN_ROLE` (it navigates to
    its synthesized DDL), so the reason the edit entries stay away is no longer
    "there is no span" but "this span's kind is not editable" -- which is what
    `edit_refusal_for_span` answers and what this pins. The table menu must
    still be the `Alter Table ▸`/creation one, not the span menu.
    """
    from PySide6.QtCore import Qt

    panel = _table_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)
    span = table_item.data(0, Qt.ItemDataRole.UserRole)
    assert span is not None and span.kind == "table"
    assert edit_refusal_for_span(span) is not None

    menu = panel._menu_for_item(table_item)

    labels = [action.text() for action in menu.actions()]
    assert not any("Edit" in label for label in labels)
    assert not any("Check Out" in label for label in labels)


def test_context_menu_on_a_table_node_offers_add_trigger(qtbot):
    """FQ-002's carve-out: the table node's menu leads with the create entries,
    and Add Trigger… emits the clicked table's TableInfo so the caller can scope
    the new trigger to it without a second lookup. FQ-025's mutation submenu
    sits BELOW both -- creating an object and altering one are different acts,
    which is also why slice 3's `Create Table…` joined them up here rather than
    inside `Alter Table ▸`."""
    panel = _table_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)
    requested = []
    panel.add_trigger_requested.connect(requested.append)

    menu = panel._menu_for_item(table_item)

    assert [action.text() for action in menu.actions()] == [
        "Add Trigger…",
        CREATE_TABLE_LABEL,
        ALTER_TABLE_MENU_TITLE,
    ]
    menu.actions()[0].trigger()
    assert len(requested) == 1
    assert requested[0].name == "pr.widget"


def test_add_trigger_is_offered_on_a_view_node(qtbot):
    """DEC-260811025733: a view keeps the gesture -- `INSTEAD OF` on a view is
    the standard way to make one updatable, so this is a real command there. It
    emits the view's own `TableInfo`, kind included, which is how the dialog
    learns to offer `INSTEAD OF` only."""
    panel = _alter_panel(qtbot, kind="view")
    view_item = panel.tree.topLevelItem(0).child(0)
    requested = []
    panel.add_trigger_requested.connect(requested.append)

    menu = panel._menu_for_item(view_item)

    labels = [action.text() for action in menu.actions()]
    assert labels == ["Add Trigger…", CREATE_TABLE_LABEL]  # no Alter Table ▸
    menu.actions()[0].trigger()
    assert [(info.name, info.kind) for info in requested] == [("pr.widget", "view")]


def test_add_trigger_on_a_matview_node_is_a_stated_refusal(qtbot):
    """DEC-260811025733: PostgreSQL supports no trigger on a materialized view,
    so the command is not offered -- but per FQ-023 it says why rather than
    vanishing, as a DISABLED entry carrying the reason (the shape
    `DdlEditorPanel` uses for `edit_refusal_for_span`). Nothing can be emitted
    from it: a disabled action does not fire, and there is no enabled entry
    whose text mentions triggers."""
    panel = _alter_panel(qtbot, kind="matview")
    matview_item = panel.tree.topLevelItem(0).child(0)
    requested = []
    panel.add_trigger_requested.connect(requested.append)

    menu = panel._menu_for_item(matview_item)

    refusals = [a for a in menu.actions() if a.text() == NO_TRIGGERS_MESSAGE]
    assert len(refusals) == 1
    assert not refusals[0].isEnabled()
    assert not any(a.text() == "Add Trigger…" for a in menu.actions())
    # The reason is stated exactly once, and the sibling creation entry survives.
    assert [a.text() for a in menu.actions()] == [
        NO_TRIGGERS_MESSAGE,
        CREATE_TABLE_LABEL,
    ]
    refusals[0].trigger()
    assert requested == []


def test_context_menu_on_the_routines_branch_offers_new_routine(qtbot):
    """Right-clicking the "Functions & Procedures" root offers creation. The
    root is identified by its branch role, not its visible label."""
    panel = _table_panel(qtbot)
    routines_root = panel.tree.topLevelItem(1)
    fired = []
    panel.new_routine_requested.connect(lambda: fired.append(True))

    menu = panel._menu_for_item(routines_root)

    assert [action.text() for action in menu.actions()] == ["New Function/Procedure…"]
    menu.actions()[0].trigger()
    assert fired == [True]


def test_context_menu_on_the_tables_branch_root_offers_create_table(qtbot):
    """The mirror of the routines root above, and the whole reason the Tables
    root -- which offered nothing until FQ-025 slice 3, a trigger being scoped
    to a specific table -- has a menu at all: each branch root offers "create a
    new one of the kind this branch lists". The root names no schema, so none
    is emitted."""
    panel = _table_panel(qtbot)
    requested = []
    panel.create_table_requested.connect(requested.append)

    menu = panel._menu_for_item(panel.tree.topLevelItem(0))

    assert [action.text() for action in menu.actions()] == [CREATE_TABLE_LABEL]
    menu.actions()[0].trigger()
    assert requested == [""]


# --- BUG-033: the unsaved-in-editor `*` overlay ------------------------------
def _dirty_panel(qtbot, **kwargs):
    schema = _schema()
    _text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans, **kwargs)
    return panel


def _calc_total_ref():
    return DdlObjectRef(
        kind="function", schema="pr", name="calc_total",
        arg_types=("integer", "numeric"),
    )


def test_set_object_dirty_adds_a_star_to_the_matching_routine_row(qtbot):
    """The reported symptom: editing a function must mark its tree row, with
    no project and therefore no drift markers involved at all."""
    panel = _dirty_panel(qtbot)
    row = panel.tree.topLevelItem(1).child(1)
    assert row.text(0) == "pr.calc_total [F]"

    panel.set_object_dirty(_calc_total_ref(), True)

    assert row.text(0) == "pr.calc_total [F] *"


def test_set_object_dirty_false_removes_the_star_again(qtbot):
    panel = _dirty_panel(qtbot)
    ref = _calc_total_ref()
    panel.set_object_dirty(ref, True)

    panel.set_object_dirty(ref, False)

    assert panel.tree.topLevelItem(1).child(1).text(0) == "pr.calc_total [F]"
    assert panel.is_object_dirty(ref) is False


def test_dirty_overlay_marks_only_the_named_object(qtbot):
    panel = _dirty_panel(qtbot)

    panel.set_object_dirty(_calc_total_ref(), True)

    audit_log_row = panel.tree.topLevelItem(1).child(0)
    assert audit_log_row.text(0) == "pr.audit_log() [T]"


def test_dirty_overlay_is_keyed_on_arg_types_so_an_overload_is_not_marked(qtbot):
    """`DdlObjectRef.key` carries the argument types; a sibling overload is a
    different object and must not inherit the marker."""
    schema = DatabaseSchema(
        routines={
            "pr.fmt(integer)": RoutineInfo(
                schema="pr", name="fmt", arg_types=["integer"], return_type="text",
                language="sql", source="a", kind="function", args=[("v", "integer")],
            ),
            "pr.fmt(text)": RoutineInfo(
                schema="pr", name="fmt", arg_types=["text"], return_type="text",
                language="sql", source="b", kind="function", args=[("v", "text")],
            ),
        }
    )
    _text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    panel.set_object_dirty(
        DdlObjectRef(kind="function", schema="pr", name="fmt", arg_types=("text",)), True
    )

    rows = [panel.tree.topLevelItem(1).child(i).text(0) for i in range(2)]
    assert rows == ["pr.fmt [F]", "pr.fmt [F] *"]


def test_dirty_overlay_does_not_double_mark_a_drift_starred_row(qtbot):
    """§18.2's `*` and the unsaved-edit `*` collapse to ONE glyph -- the user
    must never see `**`."""
    from pgtp_editor.db.ddl_project import DriftMarkers

    panel = _dirty_panel(
        qtbot,
        drift_markers={"ddl/pr.calc_total.sql": DriftMarkers(locally_edited=True)},
    )

    panel.set_object_dirty(_calc_total_ref(), True)

    assert panel.tree.topLevelItem(1).child(1).text(0) == "pr.calc_total [F] *"


def test_dirty_overlay_combines_with_a_bang_as_the_established_star_bang(qtbot):
    from pgtp_editor.db.ddl_project import DriftMarkers

    panel = _dirty_panel(
        qtbot,
        drift_markers={"ddl/pr.calc_total.sql": DriftMarkers(live_drifted=True)},
    )

    panel.set_object_dirty(_calc_total_ref(), True)

    assert panel.tree.topLevelItem(1).child(1).text(0) == "pr.calc_total [F] *!"


def test_dirty_overlay_survives_a_set_schema_rebuild(qtbot):
    """The tree is rebuilt wholesale by every refresh; a still-open, still-dirty
    tab's marker must come back with it (nothing may be keyed on an index)."""
    panel = _dirty_panel(qtbot)
    panel.set_object_dirty(_calc_total_ref(), True)

    schema = _schema()
    _text, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    assert panel.tree.topLevelItem(1).child(1).text(0) == "pr.calc_total [F] *"


def test_dirty_overlay_marks_both_leaves_of_a_trigger(qtbot):
    """A trigger renders twice (§18.1); one object, one dirty state, both rows."""
    panel = _dirty_panel(qtbot)
    ref = DdlObjectRef(kind="trigger", schema="pr", name="trg_audit", table="equipment")

    panel.set_object_dirty(ref, True)

    under_table = panel.tree.topLevelItem(0).child(0).child(0)
    under_function = panel.tree.topLevelItem(1).child(0).child(0)
    assert under_table.text(0).endswith("*")
    assert under_function.text(0).endswith("*")
    assert under_table.text(0) == under_function.text(0)


def test_set_object_dirty_accepts_a_bare_key_tuple(qtbot):
    panel = _dirty_panel(qtbot)

    panel.set_object_dirty(_calc_total_ref().key, True)

    assert panel.tree.topLevelItem(1).child(1).text(0) == "pr.calc_total [F] *"


def test_dirty_overlay_never_marks_argument_or_group_rows(qtbot):
    """Only object rows carry an identity; argument leaves and branch roots must
    be untouched whatever is marked dirty."""
    panel = _dirty_panel(qtbot)
    panel.set_object_dirty(_calc_total_ref(), True)

    calc_total = panel.tree.topLevelItem(1).child(1)
    assert calc_total.child(0).text(0) == "item_id (integer)"
    assert panel.tree.topLevelItem(1).text(0) == "Functions & Procedures"
    assert panel.tree.topLevelItem(0).text(0) == "Tables"


# --- FQ-025 slice 1: column rows and the "Alter Table ▸" submenu -------------


def _alter_panel(qtbot, *, browse_only=False, kind="table"):
    """A one-table tree whose table carries two columns -- the click contexts
    the FQ-025 dialogs default to."""
    schema = DatabaseSchema(
        tables={
            "pr.widget": TableInfo(
                name="pr.widget",
                kind=kind,
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
            )
        }
    )
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel(browse_only=browse_only)
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    return panel


def _columns_group(panel):
    table_item = panel.tree.topLevelItem(0).child(0)
    for i in range(table_item.childCount()):
        child = table_item.child(i)
        if child.text(0).startswith("Columns"):
            return child
    raise AssertionError("no Columns group under the table node")


def _submenu(menu, title=None):
    """The one submenu on `menu` (the `Alter Table ▸` one), as a QMenu."""
    wanted = ALTER_TABLE_MENU_TITLE if title is None else title
    for action in menu.actions():
        if action.text() == wanted:
            return action.menu()
    return None


def test_a_table_node_gains_a_columns_group_with_one_leaf_per_column(qtbot):
    """Column rows did not exist in this tree at all before FQ-025 -- which is
    why a right-click could never carry "which column" into a dialog."""
    panel = _alter_panel(qtbot)

    group = _columns_group(panel)

    assert group.text(0) == "Columns  (2)"
    # Declared order, not alphabetical -- the same order the Properties panel
    # renders the same table in.
    assert [group.child(i).text(0) for i in range(group.childCount())] == [
        "id (integer)",
        "note (text)",
    ]


def test_a_table_with_no_table_info_gets_no_columns_group(qtbot):
    """A trigger-only table node has no TableInfo, so there are no columns to
    show -- and an empty `Columns (0)` folder would state nothing."""
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    schema = _schema()  # triggers only, no `tables`
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)

    table_item = panel.tree.topLevelItem(0).child(0)
    labels = [table_item.child(i).text(0) for i in range(table_item.childCount())]
    assert not any(label.startswith("Columns") for label in labels)


def _submenu_labels(submenu):
    """The submenu's entries, separators dropped (they carry no text)."""
    return [a.text() for a in submenu.actions() if not a.isSeparator()]


def test_the_table_node_submenu_offers_the_full_operation_set_in_order(qtbot):
    """FQ-025 end to end, in menu order: slice 1's eight column operations,
    slice 2's four constraint ones, then slice 3's two index ones, the TABLE
    comment (this click came from the table node) and Drop Table…"""
    panel = _alter_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)

    submenu = _submenu(panel._menu_for_item(table_item))

    assert _submenu_labels(submenu) == [label for _op, label in ALTER_TABLE_ACTIONS]
    assert [label for _op, label in ALTER_TABLE_ACTIONS] == [
        "Add Column…",
        "Drop Column…",
        "Rename Column…",
        "Change Column Type…",
        "Set NOT NULL…",
        "Drop NOT NULL…",
        "Set DEFAULT…",
        "Drop DEFAULT…",
        "Add Constraint…",
        "Add Foreign Key…",
        "Drop Constraint…",
        "Rename Constraint…",
        "Create Index…",
        "Drop Index…",
        "Set Table Comment…",
        "Drop Table…",
    ]
    # No `Drop Foreign Key…`: a FK *is* a constraint and `DROP CONSTRAINT` is
    # the identical statement, so one entry covers every type (and stays the
    # place a constraint-backed index has to be dropped from).
    assert "Drop Foreign Key…" not in _submenu_labels(submenu)
    # `Create Table…` is NOT here: it creates an object rather than altering
    # this one, so it lives at the menu's top level with FQ-002's two.
    assert CREATE_TABLE_LABEL not in _submenu_labels(submenu)


def test_the_column_leaf_submenu_swaps_the_table_comment_for_the_column_one(qtbot):
    """The ONE place the two entry points differ. A comment entry names its
    subject, and the subject is whatever was right-clicked -- everything else
    (constraints, indexes, Drop Table…) is scoped to the table either way, so
    one builder still produces both menus."""
    panel = _alter_panel(qtbot)
    note_leaf = _columns_group(panel).child(1)

    labels = _submenu_labels(_submenu(panel._menu_for_item(note_leaf)))

    assert "Set Column Comment…" in labels
    assert "Set Table Comment…" not in labels
    assert labels == [
        label
        for group in alter_table_action_groups("note")
        for _op, label in group
    ]
    # Only the comment entry moved: the table node's other fifteen are all here.
    assert [label for label in labels if label != "Set Column Comment…"] == [
        label for _op, label in ALTER_TABLE_ACTIONS if label != "Set Table Comment…"
    ]


def test_a_separator_divides_every_group_of_the_submenu(qtbot):
    """Sixteen undifferentiated entries would read as one list; the five groups
    answer different questions about the table -- what its columns are, its
    constraints, its indexes, what it says about itself, and whether it exists
    at all."""
    panel = _alter_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)

    actions = _submenu(panel._menu_for_item(table_item)).actions()

    groups = alter_table_action_groups()
    separators = [i for i, action in enumerate(actions) if action.isSeparator()]
    # One separator BETWEEN each pair of groups -- never a leading or trailing
    # one, which would draw a line under nothing.
    assert len(separators) == len(groups) - 1
    sliced, cursor = [], 0
    for position in separators + [len(actions)]:
        sliced.append([a.text() for a in actions[cursor:position]])
        cursor = position + 1
    assert sliced == [[label for _op, label in group] for group in groups]
    assert sliced[-1] == ["Drop Table…"]


def test_each_constraint_entry_emits_its_own_operation_id(qtbot):
    """The four ride slice 1's signal, carrying the same click context -- a
    parallel signal would be the same three arguments under another name."""
    panel = _alter_panel(qtbot)
    note_leaf = _columns_group(panel).child(1)
    requested = []
    panel.alter_column_requested.connect(
        lambda op, table, column: requested.append((op, table.name, column))
    )

    submenu = _submenu(panel._menu_for_item(note_leaf))
    for action in submenu.actions():
        if action.text() in [label for _op, label in ALTER_TABLE_CONSTRAINT_ACTIONS]:
            action.trigger()

    assert requested == [
        (operation, "pr.widget", "note")
        for operation, _label in ALTER_TABLE_CONSTRAINT_ACTIONS
    ]


def test_the_table_node_submenu_emits_no_column_context(qtbot):
    """The same operations are reachable from the table, with no column
    pre-selected -- the dialog then opens on that table's first column."""
    panel = _alter_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)
    requested = []
    panel.alter_column_requested.connect(
        lambda op, table, column: requested.append((op, table.name, column))
    )

    _submenu(panel._menu_for_item(table_item)).actions()[1].trigger()  # Drop Column…

    assert requested == [("drop_column", "pr.widget", "")]


def test_a_column_leaf_menu_pre_fills_the_clicked_column(qtbot):
    """The entry's core interaction rule: right-clicking a column defaults the
    dialog to the table AND the column the click came from."""
    panel = _alter_panel(qtbot)
    note_leaf = _columns_group(panel).child(1)
    requested = []
    panel.alter_column_requested.connect(
        lambda op, table, column: requested.append((op, table.name, column))
    )

    menu = panel._menu_for_item(note_leaf)

    assert [action.text() for action in menu.actions()] == [ALTER_TABLE_MENU_TITLE]
    submenu = _submenu(menu)
    assert _submenu_labels(submenu) == [
        label for group in alter_table_action_groups("note") for _op, label in group
    ]
    submenu.actions()[0].trigger()  # Add Column…
    assert requested == [("add_column", "pr.widget", "note")]


def test_a_column_leaf_click_shows_its_table_in_the_properties_panel(qtbot):
    panel = _alter_panel(qtbot)
    selected = []
    panel.table_selected.connect(selected.append)

    panel._on_item_clicked(_columns_group(panel).child(0), 0)

    assert [info.name for info in selected] == ["pr.widget"]


def test_the_columns_group_node_itself_offers_no_menu(qtbot):
    """A container, not a target: it names no column, so it can seed nothing."""
    panel = _alter_panel(qtbot)

    assert panel._menu_for_item(_columns_group(panel)) is None


def test_a_view_offers_no_alter_table_submenu_anywhere(qtbot):
    """The entries emit `ALTER TABLE`/`DROP TABLE` against the clicked object,
    which a view cannot take -- so the submenu is absent on the view's node and
    on its column leaves alike. The two CREATION entries stay: what they create
    is a trigger and a table regardless of what was clicked, which is exactly
    why neither lives inside the table-only submenu."""
    panel = _alter_panel(qtbot, kind="view")
    table_item = panel.tree.topLevelItem(0).child(0)

    assert _submenu(panel._menu_for_item(table_item)) is None
    assert [a.text() for a in panel._menu_for_item(table_item).actions()] == [
        "Add Trigger…",
        CREATE_TABLE_LABEL,
    ]
    assert panel._menu_for_item(_columns_group(panel).child(0)) is None


def test_browse_only_suppresses_every_alter_table_entry(qtbot):
    """§18.7's sandbox Explorer must not offer schema mutations -- suppressed at
    menu-BUILD time, so there is no dead control to click. All SIXTEEN go, plus
    `Create Table…` at both of its top-level homes: adding a constraint,
    dropping an index or creating a table is the same kind of act as dropping a
    column, and the sandbox tree exists to look at a sandbox, not reshape it."""
    panel = _alter_panel(qtbot, browse_only=True)

    table_item = panel.tree.topLevelItem(0).child(0)
    assert panel._menu_for_item(table_item) is None
    assert panel._menu_for_item(_columns_group(panel)) is None
    assert panel._menu_for_item(_columns_group(panel).child(0)) is None
    # The Tables branch root gained a menu in slice 3; it must be suppressed too.
    assert panel._menu_for_item(panel.tree.topLevelItem(0)) is None


def test_a_table_node_seeds_create_table_with_its_own_schema(qtbot):
    """The only place in this tree that names a schema, which is what makes the
    table-node placement worth having on top of the branch-root one: a table
    created from a right-click lands where the click was."""
    panel = _alter_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)
    requested = []
    panel.create_table_requested.connect(requested.append)

    menu = panel._menu_for_item(table_item)
    [a for a in menu.actions() if a.text() == CREATE_TABLE_LABEL][0].trigger()

    assert requested == ["pr"]


def test_a_column_leaf_offers_no_create_table_entry(qtbot):
    """A column leaf's menu is the submenu and nothing else: the creation
    gestures belong to the objects that can own the new object, and a column
    owns nothing."""
    panel = _alter_panel(qtbot)

    menu = panel._menu_for_item(_columns_group(panel).child(1))

    assert [a.text() for a in menu.actions()] == [ALTER_TABLE_MENU_TITLE]


def test_each_slice_three_entry_emits_its_own_operation_id(qtbot):
    """Indexes, the comment and Drop Table ride slice 1's signal, carrying the
    same click context -- only `Create Table…`, which has no table to carry,
    needed one of its own."""
    panel = _alter_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)
    requested = []
    panel.alter_column_requested.connect(
        lambda op, table, column: requested.append((op, table.name, column))
    )

    slice_three = (
        *ALTER_TABLE_INDEX_ACTIONS,
        *ALTER_TABLE_TABLE_COMMENT_ACTIONS,
        *ALTER_TABLE_DROP_TABLE_ACTIONS,
    )
    submenu = _submenu(panel._menu_for_item(table_item))
    for action in submenu.actions():
        if action.text() in [label for _op, label in slice_three]:
            action.trigger()

    assert requested == [
        (operation, "pr.widget", "") for operation, _label in slice_three
    ]


def test_the_column_comment_entry_carries_the_clicked_column(qtbot):
    """It is offered from the column leaf precisely so it can: the dialog opens
    on that column rather than on the dropdown's first one."""
    panel = _alter_panel(qtbot)
    note_leaf = _columns_group(panel).child(1)
    requested = []
    panel.alter_column_requested.connect(
        lambda op, table, column: requested.append((op, table.name, column))
    )

    submenu = _submenu(panel._menu_for_item(note_leaf))
    [
        a
        for a in submenu.actions()
        if a.text() == ALTER_TABLE_COLUMN_COMMENT_ACTIONS[0][1]
    ][0].trigger()

    assert requested == [("column_comment", "pr.widget", "note")]


def test_a_view_offers_no_constraint_operations_either(qtbot):
    """The submenu is refused wholesale on a view, so slice 2's four are gone
    with slice 1's eight -- `ALTER TABLE … ADD CONSTRAINT` on a view is DDL the
    server refuses just as surely."""
    panel = _alter_panel(qtbot, kind="matview")
    table_item = panel.tree.topLevelItem(0).child(0)

    assert _submenu(panel._menu_for_item(table_item)) is None


# ---------------------------------------------------------------------------
# Every tree item that has DDL navigates to it (`FQ-260810183812`).
# ---------------------------------------------------------------------------

from pgtp_editor.db.introspect import ConstraintInfo, IndexInfo  # noqa: E402
from pgtp_editor.ui.ddl_buffer_panel import (  # noqa: E402
    NOT_EDITABLE_REFUSALS,
)


def _rich_table_schema():
    table = TableInfo(
        name="pr.orders",
        kind="table",
        columns=[
            ColumnInfo("id", "integer", True, False, False, None),
            ColumnInfo("tag", "text", False, False, True, None),
        ],
    )
    view = TableInfo(name="pr.v_orders", kind="view", view_definition="SELECT 1")
    constraints = {
        "pr.orders.orders_pkey": ConstraintInfo(
            schema="pr", table="orders", name="orders_pkey", kind="primary key",
            columns=["id"], definition="PRIMARY KEY (id)",
        )
    }
    indexes = {
        "pr.ix_tag": IndexInfo(
            schema="pr", table="orders", name="ix_tag", columns=["tag"],
            method="btree", definition="CREATE INDEX ix_tag ON pr.orders (tag)",
        ),
        "pr.orders_pkey": IndexInfo(
            schema="pr", table="orders", name="orders_pkey", columns=["id"],
            is_unique=True, is_primary=True, method="btree",
            definition="CREATE UNIQUE INDEX orders_pkey ON pr.orders (id)",
            constraint_name="orders_pkey",
        ),
    }
    return DatabaseSchema(
        tables={"pr.orders": table, "pr.v_orders": view},
        constraints=constraints,
        indexes=indexes,
    )


def _rich_panel(qtbot):
    schema = _rich_table_schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    return panel, text.splitlines()


def _group_named(table_item, prefix):
    for index in range(table_item.childCount()):
        child = table_item.child(index)
        if child.text(0).startswith(prefix):
            return child
    return None


def _orders_item(panel):
    root = panel.tree.topLevelItem(0)
    for index in range(root.childCount()):
        if root.child(index).text(0).startswith("pr.orders"):
            return root.child(index)
    raise AssertionError("no pr.orders node")


def _clicked_line(panel, item):
    got = []
    panel.navigate_requested.connect(got.append)
    panel._on_item_clicked(item, 0)
    return got


def test_a_view_node_navigates_to_its_create_view(qtbot):
    panel, lines = _rich_panel(qtbot)
    root = panel.tree.topLevelItem(0)
    view_item = next(
        root.child(i) for i in range(root.childCount())
        if root.child(i).text(0).startswith("pr.v_orders")
    )
    got = _clicked_line(panel, view_item)
    assert got and lines[got[0] - 1] == "-- VIEW pr.v_orders --"


def test_a_column_node_jumps_to_its_own_line_not_the_banner(qtbot):
    """Open question 3, settled: the column's line. Landing on the banner
    would make the user find the row they just clicked by eye."""
    panel, lines = _rich_panel(qtbot)
    columns = _group_named(_orders_item(panel), "Columns")
    tag_leaf = next(
        columns.child(i) for i in range(columns.childCount())
        if columns.child(i).text(0).startswith("tag")
    )
    got = _clicked_line(panel, tag_leaf)
    assert got and lines[got[0] - 1].strip().startswith("tag text")


def test_the_tree_gains_a_constraints_group_whose_nodes_navigate(qtbot):
    """Open question 1, settled: a constraint jumps to its INLINE line inside
    the `CREATE TABLE`, which is the only place it exists in a buffer that
    emits no ALTERs."""
    panel, lines = _rich_panel(qtbot)
    group = _group_named(_orders_item(panel), "Constraints")
    assert group is not None and group.childCount() == 1
    got = _clicked_line(panel, group.child(0))
    assert got and "CONSTRAINT orders_pkey" in lines[got[0] - 1]


def test_the_tree_gains_an_indexes_group_whose_nodes_navigate(qtbot):
    panel, lines = _rich_panel(qtbot)
    group = _group_named(_orders_item(panel), "Indexes")
    assert group is not None and group.childCount() == 2
    ix_tag = next(
        group.child(i) for i in range(group.childCount())
        if group.child(i).text(0).startswith("ix_tag")
    )
    got = _clicked_line(panel, ix_tag)
    assert got and lines[got[0] - 1].startswith("CREATE INDEX ix_tag")


def test_a_constraint_backed_index_navigates_to_its_constraints_line(qtbot):
    """The buffer never emits a `CREATE INDEX` for one (PostgreSQL rejects it
    and the constraint already prints it), so the constraint's line is where
    that index genuinely is."""
    panel, lines = _rich_panel(qtbot)
    group = _group_named(_orders_item(panel), "Indexes")
    backed = next(
        group.child(i) for i in range(group.childCount())
        if group.child(i).text(0).startswith("orders_pkey")
    )
    got = _clicked_line(panel, backed)
    assert got and "CONSTRAINT orders_pkey" in lines[got[0] - 1]


def test_a_table_click_is_additive_navigate_and_properties(qtbot):
    """Open question 2, settled both-not-either."""
    panel, lines = _rich_panel(qtbot)
    got_table = []
    panel.table_selected.connect(got_table.append)
    got_line = _clicked_line(panel, _orders_item(panel))
    assert got_table and got_table[0].name == "pr.orders"
    assert got_line and lines[got_line[0] - 1] == "-- TABLE pr.orders --"


def test_a_column_click_still_populates_properties_too(qtbot):
    panel, _lines = _rich_panel(qtbot)
    columns = _group_named(_orders_item(panel), "Columns")
    got_table = []
    panel.table_selected.connect(got_table.append)
    got_line = _clicked_line(panel, columns.child(0))
    assert got_table and got_table[0].name == "pr.orders"
    assert got_line


def test_the_columns_group_node_itself_still_navigates_nowhere(qtbot):
    """The shipped rule "an item with no span navigates nowhere" is unchanged
    -- which is what keeps this widening additive rather than a rewrite."""
    panel, _lines = _rich_panel(qtbot)
    group = _group_named(_orders_item(panel), "Columns")
    assert _clicked_line(panel, group) == []


def test_a_table_node_keeps_its_alter_table_menu_not_the_span_menu(qtbot):
    """A table node carries a span AND a `_TABLE_ROLE`; the span must not
    shadow the menu that matters."""
    panel, _lines = _rich_panel(qtbot)
    menu = panel._menu_for_item(_orders_item(panel))
    labels = [action.text() for action in menu.actions()]
    assert any("Add Trigger" in label for label in labels)
    assert not any("Edit DDL" == label for label in labels)


def test_every_non_editable_kind_has_a_stated_reason():
    """A refusal with a reason, not a silently disabled menu (FQ-023)."""
    for kind in ("table", "matview", "column", "constraint", "index"):
        assert NOT_EDITABLE_REFUSALS[kind]
        assert edit_refusal_for_span(DdlObjectSpan(kind, "pr", "x", None, 1, 1))


def test_a_matview_span_is_still_refused_and_says_why():
    """`FQ-260812025836`'s carve-out, asserted as a REFUSAL rather than as an
    absence: views became editable, matviews must not have followed by analogy
    (the BUG-052 / BUG-063 failure mode). The reason travels with the rule --
    there is no `CREATE OR REPLACE MATERIALIZED VIEW`, so a replace would be a
    `DROP` + `CREATE` discarding the stored data."""
    refusal = edit_refusal_for_span(DdlObjectSpan("matview", "pr", "x", None, 1, 1))
    assert refusal is not None
    assert "CREATE OR REPLACE MATERIALIZED VIEW" in refusal
    assert "data" in refusal


def test_a_table_span_is_still_refused():
    refusal = edit_refusal_for_span(DdlObjectSpan("table", "pr", "x", None, 1, 1))
    assert refusal is not None
    assert "Alter Table" in refusal


def test_routines_triggers_and_views_are_editable():
    for kind in ("function", "procedure", "trigger", "view"):
        assert edit_refusal_for_span(DdlObjectSpan(kind, "pr", "x", None, 1, 1)) is None
    assert "view" not in NOT_EDITABLE_REFUSALS


# ---------------------------------------------------------------------------
# Views are editable (`FQ-260812025836`).
# ---------------------------------------------------------------------------
def _relation_item(panel, prefix):
    root = panel.tree.topLevelItem(0)
    for index in range(root.childCount()):
        if root.child(index).text(0).startswith(prefix):
            return root.child(index)
    raise AssertionError(f"no {prefix} node")


def _matview_panel(qtbot):
    """The same fixture with the view's kind flipped to `matview` -- the ONE
    difference, so anything that passes for the view and fails here is the
    carve-out doing its job."""
    schema = _rich_table_schema()
    schema.tables["pr.v_orders"] = TableInfo(
        name="pr.v_orders", kind="matview", view_definition="SELECT 1"
    )
    _text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    return panel


def _span_of(item):
    from PySide6.QtCore import Qt

    return item.data(0, Qt.ItemDataRole.UserRole)


def test_a_view_span_resolves_to_a_create_or_replace_view_edit_target(qtbot):
    """The editable text is `pg_get_viewdef` wrapped in `CREATE OR REPLACE
    VIEW` -- the shape that alters a view in place, and the same text the
    read-only buffer already shows."""
    panel, _lines = _rich_panel(qtbot)
    span = _span_of(_relation_item(panel, "pr.v_orders"))

    ref, source = resolve_edit_target(panel._schema, span)

    assert (ref.kind, ref.schema, ref.name) == ("view", "pr", "v_orders")
    assert ref.arg_types == ()
    assert ref.table is None
    assert source == "CREATE OR REPLACE VIEW pr.v_orders AS\nSELECT 1;"


def test_the_editable_view_text_carries_no_create_trigger(qtbot):
    """LOAD-BEARING (`FQ-260812025836`, open question 1). A view can carry
    `INSTEAD OF` triggers, and each of those already owns its own `ddl/*.sql`
    checkout identity. The double-identity collision dissolves only because the
    editable text comes from `pg_get_viewdef` -- the `SELECT` body alone.
    Sourcing it from `pg_dump` output instead brings the collision straight
    back, which is what this assertion is here to catch."""
    panel, _lines = _rich_panel(qtbot)
    _ref, source = resolve_edit_target(
        panel._schema, _span_of(_relation_item(panel, "pr.v_orders"))
    )
    assert "CREATE TRIGGER" not in source.upper()


def test_a_view_node_offers_edit_ddl_beside_its_relation_gestures(qtbot):
    """A view row carries BOTH an editable span and a `_TABLE_ROLE`, so its
    menu is the union: `Edit DDL` must not have displaced `Add Trigger…`, which
    is how a view is made updatable."""
    panel, _lines = _rich_panel(qtbot)
    view_item = _relation_item(panel, "pr.v_orders")

    labels = [a.text() for a in panel._menu_for_item(view_item).actions() if a.text()]

    assert labels[0] == "Edit DDL"
    assert "Add Trigger…" in labels
    assert CREATE_TABLE_LABEL in labels
    # No `Discard local change`: a view is not part of the checkout model.
    assert DISCARD_LOCAL_LABEL not in labels


def test_edit_ddl_on_a_view_node_emits_the_ref_and_the_source(qtbot):
    panel, _lines = _rich_panel(qtbot)
    requested = []
    panel.edit_requested.connect(lambda ref, src: requested.append((ref, src)))

    menu = panel._menu_for_item(_relation_item(panel, "pr.v_orders"))
    next(a for a in menu.actions() if a.text() == "Edit DDL").trigger()

    assert len(requested) == 1
    ref, source = requested[0]
    assert ref.kind == "view"
    assert ref.qualified == "pr.v_orders"
    assert source.startswith("CREATE OR REPLACE VIEW")


def test_a_matview_node_offers_no_edit_ddl(qtbot):
    """The carve-out, driven through the real menu path rather than asserted
    off a constant: there is no `CREATE OR REPLACE MATERIALIZED VIEW`, so a
    matview keeps exactly the menu it had."""
    panel = _matview_panel(qtbot)
    labels = [
        a.text() for a in panel._menu_for_item(_relation_item(panel, "pr.v_orders")).actions()
    ]
    assert "Edit DDL" not in labels


def test_a_matview_span_resolves_no_edit_target(qtbot):
    """The last line of defence, below the menu: even handed the span
    directly, the resolver refuses to produce an editable matview."""
    panel = _matview_panel(qtbot)
    span = _span_of(_relation_item(panel, "pr.v_orders"))
    assert span.kind == "matview"
    assert resolve_edit_target(panel._schema, span) is None
    # And a span that merely CLAIMS to be a view over a matview relation is
    # refused too -- the resolver re-checks `TableInfo.kind`.
    assert (
        resolve_edit_target(
            panel._schema,
            DdlObjectSpan("view", "pr", "v_orders", None, span.start_line, span.end_line),
        )
        is None
    )


def test_a_table_node_still_offers_no_edit_ddl(qtbot):
    panel, _lines = _rich_panel(qtbot)
    labels = [a.text() for a in panel._menu_for_item(_orders_item(panel)).actions()]
    assert "Edit DDL" not in labels
    assert any("Add Trigger" in label for label in labels)


def test_a_view_with_no_available_definition_falls_back_to_its_table_menu(qtbot):
    """A connection that could not supply `pg_get_viewdef` leaves nothing to
    edit -- and inventing a body is the one thing this app does not do. The row
    must keep its relation gestures rather than losing its whole menu."""
    schema = _rich_table_schema()
    schema.tables["pr.v_orders"] = TableInfo(
        name="pr.v_orders", kind="view", view_definition=None
    )
    _text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    labels = [a.text() for a in panel._menu_for_item(_relation_item(panel, "pr.v_orders")).actions()]

    assert "Edit DDL" not in labels
    assert "Add Trigger…" in labels


def test_a_browse_only_tree_still_offers_nothing_on_a_view(qtbot):
    """§18.7's sandbox Explorer is browse-only, and widening what is editable
    must not have given it an editing gesture."""
    schema = _rich_table_schema()
    _text, spans = build_ddl_text(schema)
    panel = BrowserPanel(browse_only=True)
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    assert panel._menu_for_item(_relation_item(panel, "pr.v_orders")) is None


def test_a_browse_only_tree_gains_the_navigation_but_no_creation_entries(qtbot):
    """§18.7: both Explorers get this for free, because the change lands in
    the panels the two roles construct from one path. The sandbox instance is
    `browse_only=True`, so its widened tree must NAVIGATE without gaining any
    of the creation / `Alter Table ▸` entries browse-only suppresses at
    menu-BUILD time."""
    schema = _rich_table_schema()
    _text, spans = build_ddl_text(schema)
    panel = BrowserPanel(browse_only=True)
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    table_item = _orders_item(panel)
    got = _clicked_line(panel, table_item)
    assert got  # navigation works on the sandbox tree

    labels = [a.text() for a in panel.context_menu_for_item(table_item).actions()]
    assert labels == [RELOAD_LABEL]

    constraints = _group_named(table_item, "Constraints")
    assert _clicked_line(panel, constraints.child(0))


# ---------------------------------------------------------------------------
# The tree NAME FILTER (`FQ-260810180336`, §18.1) and the QUALITY tree's DANGER
# selection colour (`FQ-260810165518`, §18.7).
#
# Everything colour-related below asserts RENDERED PIXELS, never a palette or a
# stylesheet string. `BUG-260811021804` is the standing proof that a read-back
# assertion here is a false green: `sql_results_panel.py`'s palette faithfully
# reports a red that is painted zero times.
# ---------------------------------------------------------------------------
from collections import Counter  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402

from pgtp_editor.ui.ddl_buffer_panel import (  # noqa: E402
    CLEAR_FILTER_BUTTON_LABEL,
    FILTER_BUTTON_LABEL,
    FILTER_MODE_CONTAINS,
    FILTER_MODE_DEFAULT,
    FILTER_MODE_ENDS_WITH,
    FILTER_MODE_LABELS,
    FILTER_MODE_NOT_CONTAINS,
    FILTER_MODE_NOT_STARTS_WITH,
    FILTER_MODE_STARTS_WITH,
    FILTER_PLACEHOLDER,
    NO_FILTER_MATCHES_TEXT,
    danger_selection_colors,
    danger_selection_stylesheet,
    filter_matches,
    filter_mode_label,
)
from pgtp_editor.ui.mode_indicator import MODE_MAINTENANCE, mode_colors  # noqa: E402
from pgtp_editor.ui.theme import apply_theme  # noqa: E402


def _filtered_panel(schema=None):
    panel = BrowserPanel()
    schema = schema if schema is not None else _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)
    return panel, schema, spans


def _visible_labels(panel):
    """Every row the user can actually see, in tree order -- a row whose parent
    is hidden is not visible however its own flag reads."""
    seen: list[str] = []

    def walk(item, parent_visible):
        visible = parent_visible and not item.isHidden()
        if visible:
            seen.append(item.text(0))
        for index in range(item.childCount()):
            walk(item.child(index), visible)

    for index in range(panel.tree.topLevelItemCount()):
        walk(panel.tree.topLevelItem(index), True)
    return seen


def _filter_for(panel, term, mode=FILTER_MODE_CONTAINS):
    panel.filter_input.setText(term)
    panel.filter_mode_combo.setCurrentIndex(
        [value for _, value in FILTER_MODE_LABELS].index(mode)
    )
    panel.apply_filter()


# -- the five predicates, pure ----------------------------------------------


@pytest.mark.parametrize(
    "name,term,mode,expected",
    [
        ("pr.calc_total", "calc", FILTER_MODE_CONTAINS, True),
        ("pr.calc_total", "zzz", FILTER_MODE_CONTAINS, False),
        ("pr.calc_total", "pr.", FILTER_MODE_STARTS_WITH, True),
        ("pr.calc_total", "calc", FILTER_MODE_STARTS_WITH, False),
        ("pr.calc_total", "total", FILTER_MODE_ENDS_WITH, True),
        ("pr.calc_total", "calc", FILTER_MODE_ENDS_WITH, False),
        ("pr.calc_total", "calc", FILTER_MODE_NOT_CONTAINS, False),
        ("pr.calc_total", "zzz", FILTER_MODE_NOT_CONTAINS, True),
        ("pr.calc_total", "pr.", FILTER_MODE_NOT_STARTS_WITH, False),
        ("pr.calc_total", "calc", FILTER_MODE_NOT_STARTS_WITH, True),
    ],
)
def test_each_filter_mode_answers_its_own_question(name, term, mode, expected):
    assert filter_matches(name, term, mode) is expected


def test_matching_is_case_insensitive():
    """Open question 1, settled: insensitive, with no `Match case` toggle."""
    assert filter_matches("pr.Calc_Total", "CALC", FILTER_MODE_CONTAINS)
    assert filter_matches("pr.Calc_Total", "PR.", FILTER_MODE_STARTS_WITH)


def test_an_empty_term_matches_everything_even_in_a_negative_mode():
    """Otherwise `Filter` on an empty box would empty the tree under
    "Doesn't contain", which is nobody's idea of clearing a filter."""
    for _, mode in FILTER_MODE_LABELS:
        assert filter_matches("anything", "", mode)


# -- the bar -----------------------------------------------------------------


def test_the_filter_bar_offers_the_owners_four_controls(qtbot):
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    assert panel.filter_input.placeholderText() == FILTER_PLACEHOLDER
    assert panel.filter_button.text() == FILTER_BUTTON_LABEL
    assert panel.clear_filter_button.text() == CLEAR_FILTER_BUTTON_LABEL
    assert [
        panel.filter_mode_combo.itemText(i)
        for i in range(panel.filter_mode_combo.count())
    ] == [label for label, _ in FILTER_MODE_LABELS]


def test_the_default_mode_is_contains(qtbot):
    """Open question 3, settled."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    assert FILTER_MODE_DEFAULT == FILTER_MODE_CONTAINS
    assert panel.filter_mode_combo.currentData() == FILTER_MODE_CONTAINS


def test_return_in_the_input_filters_but_typing_does_not(qtbot):
    """A text input beside a button that ignores Return is its own small
    defect -- but nothing filters on a keystroke."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    panel.filter_input.setText("calc")
    assert panel.active_filter() is None
    panel.filter_input.returnPressed.emit()
    assert panel.active_filter() == (FILTER_MODE_CONTAINS, "calc")


def test_the_name_filter_is_not_the_find_replace_bar(qtbot):
    """The DDL Explorer tab now carries two search inputs, and the panel-side
    one must be distinguishable at a glance: different verbs, a mode dropdown
    Find has no equivalent of, and a placeholder that names its subject."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    assert not hasattr(panel, "find_replace_bar")
    assert "Find" not in panel.filter_button.text()
    assert "object names" in panel.filter_input.placeholderText()


# -- what it hides and what it keeps -----------------------------------------


def test_filtering_hides_non_matching_routines_and_keeps_the_match(qtbot):
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "calc")
    visible = _visible_labels(panel)
    assert "pr.calc_total [F]" in visible
    assert "pr.audit_log() [T]" not in visible
    # The branch root survives so the hit is shown in context.
    assert "Functions & Procedures" in visible


def test_a_group_with_a_matching_child_stays_visible(qtbot):
    """The "function 1" case: an ancestor is visible iff it matches itself or
    has a visible descendant."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "trg_other")
    visible = _visible_labels(panel)
    assert "Tables" in visible
    assert "pr.equipment  (2)" in visible  # ancestor of the hit
    assert "pr.equipment.trg_other [B][D]" in visible
    assert "pr.equipment.trg_audit [A][I][U]" not in visible


def test_a_matched_object_still_shows_its_own_children(qtbot):
    """A matched routine keeps its argument leaves -- hiding them would answer
    a different question than the one asked."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "calc_total")
    visible = _visible_labels(panel)
    assert "item_id (integer)" in visible
    assert "rate (numeric)" in visible


def test_argument_leaves_are_not_match_targets(qtbot):
    """§18.1: column leaves and routine-argument leaves are not object rows."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "item_id")
    assert panel.filter_banner_label.text() == NO_FILTER_MATCHES_TEXT
    assert _visible_labels(panel) == []


def test_column_leaves_are_not_match_targets(qtbot):
    schema = DatabaseSchema(
        tables={
            "pr.equipment": TableInfo(
                name="pr.equipment",
                kind="table",
                columns=[
                    ColumnInfo(
                        name="serial_no", data_type="text", is_pk=False,
                        is_fk=False, is_nullable=True, default=None,
                    ),
                ],
            )
        }
    )
    panel, _, _ = _filtered_panel(schema)
    qtbot.addWidget(panel)
    _filter_for(panel, "serial_no")
    assert _visible_labels(panel) == []
    _filter_for(panel, "equipment")
    assert "serial_no (text)" in _visible_labels(panel)  # rides along


def test_the_marker_letters_are_never_matched(qtbot):
    """The spec's own worked example, and the reason the filter reads a stored
    NAME rather than the base label: `d` must not match every DELETE trigger,
    and `f` must not match every function."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "[D]")
    assert _visible_labels(panel) == []
    _filter_for(panel, "[F]")
    assert _visible_labels(panel) == []


def test_the_drift_and_dirty_markers_are_never_matched_either(qtbot):
    """The label carries more decoration than `[F]`/`[D]`: §18.2's `*`/`!` drift
    markers and BUG-033's unsaved-edit star are appended to the same text. A
    filter that read the label would make `*` select "everything the user has
    touched", which is a different feature nobody asked for."""
    from pgtp_editor.db.ddl_project import DriftMarkers

    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(
        schema, spans,
        drift_markers={"ddl/pr.calc_total.sql": DriftMarkers(locally_edited=True)},
    )
    assert "pr.calc_total [F] *" in _visible_labels(panel)

    _filter_for(panel, "*")
    assert _visible_labels(panel) == []
    _filter_for(panel, "!")
    assert _visible_labels(panel) == []


def test_a_row_marked_dirty_UNDER_a_live_filter_keeps_matching_its_bare_name(qtbot):
    """The two label rewriters meet here: `set_object_dirty` re-renders the row
    text while a filter is applied. The stored name is what the filter reads, so
    a starred row must neither vanish nor start matching its star."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "calc")
    panel.set_object_dirty(_calc_total_ref(), True)

    assert "pr.calc_total [F] *" in _visible_labels(panel)
    _filter_for(panel, "*")
    assert _visible_labels(panel) == []


def test_the_trigger_count_suffix_on_a_table_is_not_matched(qtbot):
    """A table row reads `pr.equipment  (2)` -- the count is presentation, so
    filtering for it must not select "tables with two triggers"."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    assert "pr.equipment  (2)" in _visible_labels(panel)

    _filter_for(panel, "(2)")
    assert _visible_labels(panel) == []


def test_a_trigger_is_hidden_in_BOTH_of_its_occurrences(qtbot):
    """One object is never half-hidden (§18.1's dual-grouped tree)."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "calc_total")
    assert not any("trg_audit" in label for label in _visible_labels(panel))


def test_clear_filter_restores_every_row_and_empties_the_input(qtbot):
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    everything = _visible_labels(panel)
    _filter_for(panel, "calc")
    assert _visible_labels(panel) != everything
    panel.clear_filter()
    assert panel.active_filter() is None
    assert panel.filter_input.text() == ""
    assert _visible_labels(panel) == everything


def test_pressing_filter_on_an_empty_box_clears_rather_than_hiding(qtbot):
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    everything = _visible_labels(panel)
    _filter_for(panel, "calc")
    _filter_for(panel, "   ")
    assert panel.active_filter() is None
    assert _visible_labels(panel) == everything


def test_hiding_a_row_changes_nothing_about_a_visible_rows_behaviour(qtbot):
    """A visibility operation and nothing else: same span, same signal, same
    context menu."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "calc_total")
    routines_root = panel.tree.topLevelItem(1)
    routine_item = next(
        routines_root.child(i)
        for i in range(routines_root.childCount())
        if not routines_root.child(i).isHidden()
    )
    with qtbot.waitSignal(panel.navigate_requested):
        panel._on_item_clicked(routine_item, 0)
    labels = [a.text() for a in panel.context_menu_for_item(routine_item).actions()]
    assert "Edit DDL" in labels


def test_the_sandbox_tree_gets_the_filter_too(qtbot):
    """`browse_only` withholds edits, creations and mutations -- a search aid
    is none of those."""
    panel = BrowserPanel(browse_only=True)
    qtbot.addWidget(panel)
    schema = _schema()
    _, spans = build_ddl_text(schema)
    panel.set_schema(schema, spans)
    _filter_for(panel, "calc")
    assert "pr.calc_total [F]" in _visible_labels(panel)
    assert "pr.audit_log() [T]" not in _visible_labels(panel)


# -- the banner --------------------------------------------------------------


def test_an_active_filter_announces_itself(qtbot):
    """Open question 2, settled: yes. A tree silently missing objects is the
    shape of a silent wrong result."""
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    assert not panel.filter_banner_label.isVisibleTo(panel)
    _filter_for(panel, "calc")
    assert panel.filter_banner_label.isVisibleTo(panel)
    text = panel.filter_banner_label.text()
    assert filter_mode_label(FILTER_MODE_CONTAINS).lower() in text
    assert "calc" in text
    panel.clear_filter()
    assert not panel.filter_banner_label.isVisibleTo(panel)


def test_an_all_hidden_tree_says_why(qtbot):
    panel, _, _ = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "no_such_object")
    assert panel.filter_banner_label.text() == NO_FILTER_MATCHES_TEXT
    assert panel.filter_banner_label.isVisibleTo(panel)


# -- the rebuild-under-a-live-filter case, which is the real correctness risk -


def test_a_rebuild_under_a_live_filter_re_applies_it(qtbot):
    """Open question 4, settled: RE-APPLY, the `_dirty_keys` shape. A
    `set_schema` that came back unfiltered would leave the user reading a tree
    they believe is narrowed."""
    panel, schema, spans = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "calc")

    panel.set_schema(schema, spans)  # a Reload DDL / re-fetch

    assert panel.active_filter() == (FILTER_MODE_CONTAINS, "calc")
    visible = _visible_labels(panel)
    assert "pr.calc_total [F]" in visible
    assert "pr.audit_log() [T]" not in visible
    assert panel.filter_banner_label.isVisibleTo(panel)


def test_a_rebuild_re_filters_the_NEW_rows_not_the_old_ones(qtbot):
    """The filter must act on whatever the rebuild produced -- an object that
    appears in the refresh and does not match must come back hidden."""
    panel, schema, spans = _filtered_panel()
    qtbot.addWidget(panel)
    _filter_for(panel, "calc")

    widened = DatabaseSchema(
        routines={
            **schema.routines,
            "pr.new_helper()": RoutineInfo(
                schema="pr", name="new_helper", arg_types=[], return_type="void",
                language="plpgsql", source="body3", kind="function",
            ),
        },
        triggers=schema.triggers,
    )
    _, new_spans = build_ddl_text(widened)
    panel.set_schema(widened, new_spans)

    visible = _visible_labels(panel)
    assert "pr.new_helper() [F]" not in visible
    assert "pr.calc_total [F]" in visible


def test_a_rebuild_with_no_filter_hides_nothing(qtbot):
    panel, schema, spans = _filtered_panel()
    qtbot.addWidget(panel)
    everything = _visible_labels(panel)
    panel.set_schema(schema, spans)
    assert _visible_labels(panel) == everything


# -- the danger selection colour, asserted in PIXELS -------------------------

#: The live qdarkstyle chrome the tree's rows are drawn on, per theme -- the
#: contrast target §7 requires ("against the live QDarkStyle chrome, not the
#: bare palette"), not `theme.py`'s `Highlight`, which a tree row never paints.
TREE_CHROME = {True: "#fafafa", False: "#19232d"}


def _rendered(name: str) -> str:
    """A colour spelled the way `QImage.pixelColor().name()` spells it.
    `mode_colors` stores upper-case literals, so a raw comparison against a
    pixel name silently never matches."""
    return QColor(name).name()


def _pixel_counts(widget) -> Counter:
    image = widget.grab().toImage()
    counts: Counter = Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            counts[image.pixelColor(x, y).name()] += 1
    return counts


def _relative_luminance(name: str) -> float:
    color = QColor(name)
    channels = [
        raw / 12.92 if raw <= 0.03928 else ((raw + 0.055) / 1.055) ** 2.4
        for raw in (color.redF(), color.greenF(), color.blueF())
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(one: str, other: str) -> float:
    first, second = _relative_luminance(one), _relative_luminance(other)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


@pytest.fixture
def themed_browser(qtbot, qapp):
    """A *shown* panel with a selected row, under a real theme. Showing is not
    optional: an unshown widget's grab is not evidence of what the user sees,
    and the app-wide QSS is only resolved once the widget is polished."""

    def build(light: bool, browse_only: bool = False) -> BrowserPanel:
        apply_theme(qapp, light)
        panel = BrowserPanel(browse_only=browse_only)
        qtbot.addWidget(panel)
        schema = _schema()
        _, spans = build_ddl_text(schema)
        panel.resize(420, 320)
        panel.show()
        panel.set_schema(schema, spans)
        panel.tree.expandAll()
        routines_root = panel.tree.topLevelItem(1)
        panel.tree.setCurrentItem(routines_root.child(0))
        qapp.processEvents()
        return panel

    return build


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_quality_tree_actually_paints_its_selection_in_the_danger_red(
    themed_browser, light
):
    """Rendered pixels, not a palette read-back: `BUG-260811021804` is the
    standing proof that a palette can report a red nothing paints."""
    panel = themed_browser(light)
    background, _ = danger_selection_colors(light)
    assert _pixel_counts(panel.tree)[_rendered(background)] > 0


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_sandbox_tree_keeps_the_ordinary_selection(themed_browser, light):
    """The DIFFERENCE is the feature -- colouring both would say nothing."""
    panel = themed_browser(light, browse_only=True)
    background, _ = danger_selection_colors(light)
    assert _pixel_counts(panel.tree)[_rendered(background)] == 0
    assert panel.has_danger_highlight() is False


#: The app-wide qdarkstyle selection blue, per theme -- the colour the indent
#: strip was still painting when only the two `::item` selectors were overridden.
ORDINARY_SELECTION = {True: "#9FCBFF", False: "#346792"}


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_no_ordinary_blue_survives_inside_the_danger_band(themed_browser, light):
    """Found by looking at pixels: overriding only the two `::item` selectors
    left the selected row's indent strip painting the app-wide selection blue,
    so the band was red with a blue notch in it."""
    panel = themed_browser(light)
    ordinary = _rendered(ORDINARY_SELECTION[light])
    assert _pixel_counts(panel.tree)[ordinary] == 0


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_ordinary_selection_colour_this_file_watches_for_is_REALLY_painted(
    themed_browser, light
):
    """The anchor for the test above, and the reason it is not a false green of
    its own shape: an "assert this colour is absent" test passes forever if the
    colour was never the app's selection blue in the first place (a theme tweak,
    a typo, a case difference). The sandbox tree is selected identically and
    NOT reddened, so it must paint exactly that value.
    """
    panel = themed_browser(light, browse_only=True)
    assert _pixel_counts(panel.tree)[_rendered(ORDINARY_SELECTION[light])] > 0


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_danger_band_reaches_the_rows_INDENT_STRIP_not_just_its_text(
    themed_browser, light
):
    """The regression stated positionally rather than by a global count: the
    strip left of the label is drawn from the universal `QWidget` rule's
    `selection-background-color`, so the band must be red at x=1 of the selected
    row, not merely red somewhere."""
    panel = themed_browser(light)
    red = _rendered(danger_selection_colors(light)[0])
    rect = panel.tree.visualItemRect(panel.tree.currentItem())
    assert rect.width() > 0 and rect.height() > 0
    image = panel.tree.viewport().grab().toImage()
    middle = rect.top() + rect.height() // 2
    assert image.pixelColor(1, middle).name() == red
    assert image.pixelColor(rect.left() + 1, middle).name() == red


def test_the_danger_red_survives_a_light_dark_round_trip(themed_browser, qapp):
    """The value is a per-theme pair, so it must be re-applied on every flip.

    Settled with `processEvents` on purpose: `PaletteChange` fires four times
    per flip and the first two still report the OLD lightness, so the handler
    is idempotent and last-write-wins rather than right on the first event.
    """
    panel = themed_browser(False)
    dark_red = _rendered(danger_selection_colors(False)[0])
    light_red = _rendered(danger_selection_colors(True)[0])
    assert dark_red != light_red
    assert _pixel_counts(panel.tree)[dark_red] > 0

    apply_theme(qapp, True)
    qapp.processEvents()
    counts = _pixel_counts(panel.tree)
    assert counts[light_red] > 0
    assert counts[dark_red] == 0

    apply_theme(qapp, False)
    qapp.processEvents()
    counts = _pixel_counts(panel.tree)
    assert counts[dark_red] > 0
    assert counts[light_red] == 0


def test_turning_the_danger_highlight_off_restores_the_ordinary_selection(
    themed_browser, qapp
):
    panel = themed_browser(True)
    red = _rendered(danger_selection_colors(True)[0])
    assert _pixel_counts(panel.tree)[red] > 0
    panel.set_danger_highlight(False)
    qapp.processEvents()
    assert _pixel_counts(panel.tree)[red] == 0


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_danger_red_is_the_maintenance_pair_and_never_a_second_red(light):
    """Trap 1: no colour literal enters this module. The pair is used swapped
    -- the chip's strong colour becomes the band, the pale one the text on it --
    because the chip background is useless as a selection band (see below)."""
    chip_background, chip_foreground = mode_colors(light)[MODE_MAINTENANCE]
    assert danger_selection_colors(light) == (chip_foreground, chip_background)
    sheet = danger_selection_stylesheet(light)
    assert chip_foreground in sheet and chip_background in sheet


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_selected_rows_text_is_legible_on_the_danger_band(light):
    """The pair was already tuned to be legible against itself, which is what
    reusing it buys: 7.98:1 light, 8.50:1 dark, against qdarkstyle's own
    9.44:1 / 4.57:1 for the blue it replaces."""
    background, text = danger_selection_colors(light)
    assert _contrast_ratio(background, text) >= 4.5


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_danger_band_is_visible_AS_a_band_against_the_tree_chrome(light):
    """Why the pair is swapped rather than used as-is: the chip's light
    background `#FDECEA` measures 1.10:1 against the tree's chrome, so a
    selection painted in it would be invisible as a selection. The swapped
    band measures 8.74:1 / 9.28:1."""
    background, _ = danger_selection_colors(light)
    chrome = TREE_CHROME[light]
    assert _contrast_ratio(background, chrome) >= 3.0
    chip_background, _ = mode_colors(light)[MODE_MAINTENANCE]
    if light:
        assert _contrast_ratio(chip_background, chrome) < 3.0
