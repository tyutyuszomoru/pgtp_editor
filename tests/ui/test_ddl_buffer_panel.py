from pgtp_editor.db.ddl_buffer import build_ddl_text
from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, RoutineInfo, TableInfo, TriggerInfo
from pgtp_editor.ui.ddl_buffer_panel import (
    ALTER_TABLE_ACTIONS,
    ALTER_TABLE_COLUMN_ACTIONS,
    ALTER_TABLE_CONSTRAINT_ACTIONS,
    ALTER_TABLE_MENU_TITLE,
    BrowserPanel,
    resolve_edit_target,
)
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

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


def test_context_menu_on_an_argument_leaf_offers_no_edit(qtbot, monkeypatch):
    """Argument-name child leaves carry no span -- no Edit… entry (§18.5)."""
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QTreeWidget

    arg_leaf = _routine_item(panel).child(0)  # "item_id (integer)"
    assert arg_leaf.data(0, Qt.ItemDataRole.UserRole) is None
    monkeypatch.setattr(QTreeWidget, "itemAt", lambda self, pos: arg_leaf)
    got = []
    panel.edit_requested.connect(lambda *a: got.append(a))

    panel._on_context_menu(QPoint(0, 0))  # position is irrelevant, itemAt is patched

    assert got == []


def test_context_menu_at_empty_position_does_nothing(qtbot):
    schema = _schema()
    text, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)
    got = []
    panel.edit_requested.connect(lambda *a: got.append(a))

    from PySide6.QtCore import QPoint

    panel._on_context_menu(QPoint(-1, -1))  # below the last row: no item there

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
    # and the row already names the object so the entry does not repeat it.
    labels = [label for label, _cb in captured["actions"]]
    assert labels == ["Edit DDL"]
    assert len(got) == 1
    ref, source = got[0]
    assert ref.name == "calc_total"
    assert source == "body1"


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


def test_click_on_table_node_does_not_emit_navigate_requested(qtbot):
    """A table node has no DdlObjectSpan -- clicking it must go through the
    table_selected path, never navigate_requested."""
    schema = DatabaseSchema(tables={"pr.widget": _table_info("pr.widget")})
    _, spans = build_ddl_text(schema)
    panel = BrowserPanel()
    qtbot.addWidget(panel)
    panel.set_schema(schema, spans)

    got = []
    panel.navigate_requested.connect(got.append)
    table_item = panel.tree.topLevelItem(0).child(0)
    panel._on_item_clicked(table_item, 0)

    assert got == []


def test_click_on_trigger_owning_table_node_still_emits_table_selected(qtbot):
    """A table WITH triggers is still a table node in its own right -- its
    top-level row click emits table_selected, distinct from clicking one of
    its nested trigger leaves (which emits navigate_requested instead)."""
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
    assert got_navigate == []


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
    """A table node still offers NO Edit…/Check Out (§18.1) -- a whole table
    has no single DdlObjectSpan/source text for either to act on, and table
    nodes carry only _TABLE_ROLE data, never _SPAN_ROLE.

    FQ-002 carved out a *creation* entry on this node (covered below), which
    is why this asserts the absence of the two edit gestures rather than the
    absence of a menu: the reason the edit entries stay away is unchanged, and
    that is the guarantee worth pinning.
    """
    from PySide6.QtCore import Qt

    panel = _table_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)
    assert table_item.data(0, Qt.ItemDataRole.UserRole) is None  # no _SPAN_ROLE

    menu = panel._menu_for_item(table_item)

    labels = [action.text() for action in menu.actions()]
    assert not any("Edit" in label for label in labels)
    assert not any("Check Out" in label for label in labels)


def test_context_menu_on_a_table_node_offers_add_trigger(qtbot):
    """FQ-002's carve-out: the table node's menu leads with the create entry,
    and it emits the clicked table's TableInfo so the caller can scope the new
    trigger to it without a second lookup. FQ-025's mutation submenu sits
    BELOW it -- creating an object and altering one are different acts."""
    panel = _table_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)
    requested = []
    panel.add_trigger_requested.connect(requested.append)

    menu = panel._menu_for_item(table_item)

    assert [action.text() for action in menu.actions()] == [
        "Add Trigger…",
        ALTER_TABLE_MENU_TITLE,
    ]
    menu.actions()[0].trigger()
    assert len(requested) == 1
    assert requested[0].name == "pr.widget"


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


def test_context_menu_on_the_tables_branch_root_offers_nothing(qtbot):
    """Creation is scoped: a trigger needs a specific table, so the Tables
    root itself has nothing to offer -- and must not pop an empty menu."""
    panel = _table_panel(qtbot)

    assert panel._menu_for_item(panel.tree.topLevelItem(0)) is None


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


def test_the_table_node_submenu_offers_the_twelve_alter_operations(qtbot):
    """Slice 1's eight column operations, then slice 2's four constraint ones."""
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
    ]
    # No `Drop Foreign Key…`: a FK *is* a constraint and `DROP CONSTRAINT` is
    # the identical statement, so one entry covers every type (and stays the
    # place a constraint-backed index has to be dropped from).
    assert "Drop Foreign Key…" not in _submenu_labels(submenu)


def test_a_separator_divides_the_column_operations_from_the_constraint_ones(qtbot):
    """Twelve undifferentiated entries would read as one list; the two groups
    answer different questions about the table."""
    panel = _alter_panel(qtbot)
    table_item = panel.tree.topLevelItem(0).child(0)

    actions = _submenu(panel._menu_for_item(table_item)).actions()

    separators = [i for i, action in enumerate(actions) if action.isSeparator()]
    assert separators == [len(ALTER_TABLE_COLUMN_ACTIONS)]
    assert [a.text() for a in actions[: separators[0]]] == [
        label for _op, label in ALTER_TABLE_COLUMN_ACTIONS
    ]
    assert [a.text() for a in actions[separators[0] + 1 :]] == [
        label for _op, label in ALTER_TABLE_CONSTRAINT_ACTIONS
    ]


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
    assert _submenu_labels(submenu) == [label for _op, label in ALTER_TABLE_ACTIONS]
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
    """Every entry emits `ALTER TABLE`, which a view cannot take -- so the
    submenu is absent on the view's node and on its column leaves alike."""
    panel = _alter_panel(qtbot, kind="view")
    table_item = panel.tree.topLevelItem(0).child(0)

    assert _submenu(panel._menu_for_item(table_item)) is None
    assert [a.text() for a in panel._menu_for_item(table_item).actions()] == [
        "Add Trigger…"
    ]
    assert panel._menu_for_item(_columns_group(panel).child(0)) is None


def test_browse_only_suppresses_every_alter_table_entry(qtbot):
    """§18.7's sandbox Explorer must not offer schema mutations -- suppressed at
    menu-BUILD time, so there is no dead control to click. All TWELVE go: adding
    a constraint or dropping a foreign key is the same kind of act as dropping a
    column, and the sandbox tree exists to look at a sandbox, not reshape it."""
    panel = _alter_panel(qtbot, browse_only=True)

    table_item = panel.tree.topLevelItem(0).child(0)
    assert panel._menu_for_item(table_item) is None
    assert panel._menu_for_item(_columns_group(panel)) is None
    assert panel._menu_for_item(_columns_group(panel).child(0)) is None


def test_a_view_offers_no_constraint_operations_either(qtbot):
    """The submenu is refused wholesale on a view, so slice 2's four are gone
    with slice 1's eight -- `ALTER TABLE … ADD CONSTRAINT` on a view is DDL the
    server refuses just as surely."""
    panel = _alter_panel(qtbot, kind="matview")
    table_item = panel.tree.topLevelItem(0).child(0)

    assert _submenu(panel._menu_for_item(table_item)) is None
