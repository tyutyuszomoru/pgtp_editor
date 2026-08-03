from pgtp_editor.db.ddl_buffer import build_ddl_text
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo, TriggerInfo
from pgtp_editor.ui.ddl_buffer_panel import BrowserPanel, resolve_edit_target

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
    """The actual right-click ▸ Edit… menu path, end to end -- QMenu itself is
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

    captured = {}

    class _FakeMenu:
        def __init__(self, *a, **k):
            pass

        def addAction(self, label, cb=None):
            captured["label"] = label
            captured["cb"] = cb

        def exec(self, *a, **k):
            captured["cb"]()

    monkeypatch.setattr("pgtp_editor.ui.ddl_buffer_panel.QMenu", _FakeMenu)
    item = _routine_item(panel)
    monkeypatch.setattr(QTreeWidget, "itemAt", lambda self, pos: item)

    panel._on_context_menu(QPoint(0, 0))  # position is irrelevant, itemAt is patched

    assert captured["label"] == "Edit pr.calc_total(integer, numeric)…"
    assert len(got) == 1
    ref, source = got[0]
    assert ref.name == "calc_total"
    assert source == "body1"
