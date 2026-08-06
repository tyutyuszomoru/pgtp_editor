# tests/db/test_routine_refs.py
"""Pure tests for XML↔routine cross-referencing (no Qt, no live DB)."""
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo, TriggerInfo
from pgtp_editor.db.routine_refs import (
    REF_TYPE_CALL,
    REF_TYPE_MENTION,
    RoutineUsage,
    collect_routine_references,
    routine_reference_index,
)
from pgtp_editor.model.nodes import (
    ChildElement,
    ColumnNode,
    DetailNode,
    EventNode,
    PageNode,
    ProjectModel,
)


def _event(tag_name, text, sourceline=None):
    return EventNode(
        identity=tag_name,
        tag_name=tag_name,
        side="S",
        text=text,
        sourceline=sourceline,
    )


def _routine(name, arg_types=(), schema="public", kind="function", return_type="integer"):
    return RoutineInfo(
        schema=schema,
        name=name,
        arg_types=list(arg_types),
        return_type=return_type,
        language="plpgsql",
        source=f"CREATE FUNCTION {schema}.{name}() ...",
        kind=kind,
    )


def _trigger(name, table="public.orders", function_name="trg_fn"):
    schema, _, table_name = table.partition(".")
    return TriggerInfo(
        schema=schema,
        table=table_name,
        name=name,
        timing="before",
        events=["insert"],
        function_name=function_name,
    )


def _schema(routines=(), triggers=()):
    return DatabaseSchema(
        routines={r.signature: r for r in routines},
        triggers={f"{t.schema}.{t.table}.{t.name}": t for t in triggers},
    )


def _usage(usages, key):
    matches = [u for u in usages if u.key == key]
    assert matches, f"{key} not in {[u.key for u in usages]}"
    return matches[0]


# --- happy path -------------------------------------------------------------


def test_event_body_call_is_found_with_breadcrumb_and_line():
    page = PageNode(
        identity="p1",
        attrib={"caption": "Orders", "tableName": "pr.orders"},
        sourceline=10,
        events=[_event("OnBeforeInsert", "\nSELECT\n  public.recalc_total(1);\n", sourceline=12)],
    )
    project = ProjectModel(pages=[page])
    schema = _schema(routines=[_routine("recalc_total", ["integer"])])

    usages = collect_routine_references(project, schema)
    usage = _usage(usages, "public.recalc_total(integer)")

    assert usage.referenced is True
    assert usage.kind == "function"
    assert usage.ambiguous is False
    (ref,) = usage.references
    assert ref.routine_name == "public.recalc_total"
    assert ref.breadcrumb == "Page 'Orders' ▸ Event 'OnBeforeInsert'"
    assert ref.kind == "event"
    assert ref.ref_type == REF_TYPE_CALL
    # <OnBeforeInsert> opens on line 12; the call sits two newlines into its text.
    assert ref.line == 14
    assert ref.node is page.events[0]


def test_unqualified_call_and_whitespace_before_paren_match():
    page = PageNode(
        identity="p1",
        attrib={"caption": "P"},
        sourceline=1,
        events=[_event("OnCustom", "PERFORM recalc_total ();", sourceline=3)],
    )
    schema = _schema(routines=[_routine("recalc_total")])

    usage = _usage(collect_routine_references(ProjectModel(pages=[page]), schema), "public.recalc_total()")
    assert [r.line for r in usage.references] == [3]


def test_match_is_case_insensitive():
    page = PageNode(
        identity="p1",
        attrib={"caption": "P"},
        events=[_event("OnCustom", "select PUBLIC.Recalc_Total();")],
    )
    schema = _schema(routines=[_routine("recalc_total")])

    assert _usage(
        collect_routine_references(ProjectModel(pages=[page]), schema),
        "public.recalc_total()",
    ).referenced


# --- referenced from more than one place ------------------------------------


def test_routine_referenced_from_several_places_keeps_document_order():
    detail = DetailNode(
        identity="d1",
        attrib={"tableName": "pr.lines", "caption": "Lines"},
        sourceline=30,
        events=[_event("OnAfterUpdate", "PERFORM recalc_total();", sourceline=31)],
    )
    page = PageNode(
        identity="p1",
        attrib={"caption": "Orders", "customQuery": "SELECT recalc_total(id) FROM t"},
        sourceline=10,
        events=[_event("OnBeforeInsert", "PERFORM public.recalc_total();", sourceline=12)],
        columns=[
            ColumnNode(
                identity="c1",
                attrib={"fieldName": "total", "defaultValue": "recalc_total(0)"},
                sourceline=20,
            )
        ],
        details=[detail],
    )
    schema = _schema(routines=[_routine("recalc_total")])

    usage = _usage(
        collect_routine_references(ProjectModel(pages=[page]), schema),
        "public.recalc_total()",
    )
    assert [(r.kind, r.breadcrumb, r.line) for r in usage.references] == [
        ("page", "Page 'Orders' @customQuery", 10),
        ("event", "Page 'Orders' ▸ Event 'OnBeforeInsert'", 12),
        ("column", "Page 'Orders' ▸ Column 'total' @defaultValue", 20),
        ("event", "Page 'Orders' ▸ Detail 'Lines' ▸ Event 'OnAfterUpdate'", 31),
    ]


def test_lookup_child_element_attribute_is_searched():
    column = ColumnNode(
        identity="c1",
        attrib={"fieldName": "customer"},
        sourceline=20,
        lookup=ChildElement(
            attrib={"tableName": "pr.customers", "customQuery": "SELECT * FROM pick_customer(1)"},
            sourceline=21,
        ),
    )
    page = PageNode(identity="p1", attrib={"caption": "Orders"}, sourceline=10, columns=[column])
    schema = _schema(routines=[_routine("pick_customer", ["integer"])])

    usage = _usage(
        collect_routine_references(ProjectModel(pages=[page]), schema),
        "public.pick_customer(integer)",
    )
    (ref,) = usage.references
    assert ref.breadcrumb == "Page 'Orders' ▸ Column 'customer' ▸ <Lookup> @customQuery"
    assert ref.line == 21
    assert ref.node is column


def test_several_hits_on_one_line_collapse_to_one_reference():
    page = PageNode(
        identity="p1",
        attrib={"caption": "P"},
        events=[_event("OnCustom", "SELECT f(f(1));", sourceline=5)],
    )
    schema = _schema(routines=[_routine("f", ["integer"])])

    usage = _usage(collect_routine_references(ProjectModel(pages=[page]), schema), "public.f(integer)")
    assert [r.line for r in usage.references] == [5]


# --- referenced nowhere -----------------------------------------------------


def test_unreferenced_routine_is_reported_with_no_references():
    page = PageNode(identity="p1", attrib={"caption": "Orders"})
    schema = _schema(routines=[_routine("never_called")])

    usage = _usage(collect_routine_references(ProjectModel(pages=[page]), schema), "public.never_called()")
    assert usage.references == []
    assert usage.referenced is False


def test_prose_attribute_without_call_parens_is_not_a_match():
    # The whole reason a call-shaped match is required: a caption mentioning
    # the word must not be reported as a call site.
    page = PageNode(identity="p1", attrib={"caption": "Recalc total of the order"})
    schema = _schema(routines=[_routine("recalc")])

    assert not _usage(
        collect_routine_references(ProjectModel(pages=[page]), schema),
        "public.recalc()",
    ).referenced


def test_call_qualified_with_another_schema_is_not_attributed():
    page = PageNode(
        identity="p1",
        attrib={"caption": "P"},
        events=[_event("OnCustom", "SELECT other.recalc();")],
    )
    schema = _schema(routines=[_routine("recalc")])

    assert not _usage(
        collect_routine_references(ProjectModel(pages=[page]), schema),
        "public.recalc()",
    ).referenced


def test_name_embedded_in_a_longer_identifier_is_not_a_match():
    page = PageNode(
        identity="p1",
        attrib={"caption": "P"},
        events=[_event("OnCustom", "SELECT my_recalc(); SELECT recalc_more();")],
    )
    schema = _schema(routines=[_routine("recalc")])

    assert not _usage(
        collect_routine_references(ProjectModel(pages=[page]), schema),
        "public.recalc()",
    ).referenced


# --- overloads --------------------------------------------------------------


def test_overloads_are_separate_usages_and_both_marked_ambiguous():
    page = PageNode(
        identity="p1",
        attrib={"caption": "P"},
        events=[_event("OnCustom", "SELECT f(1);", sourceline=7)],
    )
    schema = _schema(
        routines=[_routine("f", ["integer"]), _routine("f", ["integer", "text"])]
    )

    usages = collect_routine_references(ProjectModel(pages=[page]), schema)
    keys = [u.key for u in usages]
    assert keys == ["public.f(integer)", "public.f(integer, text)"]  # sorted, not conflated

    for usage in usages:
        assert usage.ambiguous is True
        assert usage.name == "public.f"
        assert [r.line for r in usage.references] == [7]
    # Separate objects, so a consumer mutating one cannot disturb the other.
    assert usages[0].references is not usages[1].references


def test_single_overload_is_not_ambiguous_and_zero_arg_signature_has_parens():
    schema = _schema(routines=[_routine("f")])
    page = PageNode(identity="p1", attrib={"caption": "P"}, events=[_event("E", "f();")])

    (usage,) = collect_routine_references(ProjectModel(pages=[page]), schema)
    assert usage.key == "public.f()"
    assert usage.ambiguous is False


def test_same_name_in_two_schemas_is_matched_independently():
    page = PageNode(
        identity="p1",
        attrib={"caption": "P"},
        events=[_event("E", "SELECT audit.log_it();", sourceline=4)],
    )
    schema = _schema(
        routines=[_routine("log_it", schema="audit"), _routine("log_it", schema="public")]
    )

    usages = collect_routine_references(ProjectModel(pages=[page]), schema)
    assert _usage(usages, "audit.log_it()").referenced is True
    assert _usage(usages, "public.log_it()").referenced is False
    for usage in usages:
        assert usage.ambiguous is False


# --- triggers ---------------------------------------------------------------


def test_trigger_is_matched_as_a_bare_word_mention():
    page = PageNode(
        identity="p1",
        attrib={"caption": "Orders"},
        events=[
            _event("OnBeforeInsert", "ALTER TABLE orders DISABLE TRIGGER trg_guard;", sourceline=9)
        ],
    )
    schema = _schema(triggers=[_trigger("trg_guard")])

    usage = _usage(
        collect_routine_references(ProjectModel(pages=[page]), schema),
        "public.orders.trg_guard",
    )
    assert usage.kind == "trigger"
    assert usage.name == "trg_guard"
    (ref,) = usage.references
    assert ref.ref_type == REF_TYPE_MENTION
    assert ref.routine_name == "trg_guard"
    assert ref.line == 9


def test_unreferenced_trigger_still_listed():
    page = PageNode(identity="p1", attrib={"caption": "Orders"})
    schema = _schema(triggers=[_trigger("trg_guard")])

    assert not _usage(
        collect_routine_references(ProjectModel(pages=[page]), schema),
        "public.orders.trg_guard",
    ).referenced


def test_trigger_word_boundary_still_applies():
    page = PageNode(
        identity="p1",
        attrib={"caption": "P"},
        events=[_event("E", "trg_guard_old is not it")],
    )
    schema = _schema(triggers=[_trigger("trg_guard")])

    assert not _usage(
        collect_routine_references(ProjectModel(pages=[page]), schema),
        "public.orders.trg_guard",
    ).referenced


# --- ordering, keying, and the projectless case -----------------------------


def test_routines_come_before_triggers_and_both_are_name_sorted():
    page = PageNode(identity="p1", attrib={"caption": "P"})
    schema = _schema(
        routines=[_routine("zeta"), _routine("alpha"), _routine("mid", kind="procedure")],
        triggers=[_trigger("trg_b", table="public.z"), _trigger("trg_a", table="public.a")],
    )

    keys = [u.key for u in collect_routine_references(ProjectModel(pages=[page]), schema)]
    assert keys == [
        "public.alpha()",
        "public.mid()",
        "public.zeta()",
        "public.a.trg_a",
        "public.z.trg_b",
    ]


def test_procedure_kind_is_carried_through():
    page = PageNode(identity="p1", attrib={"caption": "P"})
    schema = _schema(routines=[_routine("do_it", kind="procedure", return_type=None)])

    (usage,) = collect_routine_references(ProjectModel(pages=[page]), schema)
    assert usage.kind == "procedure"
    assert usage.info.kind == "procedure"


def test_no_project_yields_nothing_rather_than_false_unreferenced_claims():
    schema = _schema(routines=[_routine("f")], triggers=[_trigger("trg_guard")])

    assert collect_routine_references(None, schema) == []
    assert collect_routine_references(ProjectModel(pages=[]), schema) == []
    assert routine_reference_index(None, schema) == {}


def test_index_is_keyed_by_signature_and_trigger_key():
    page = PageNode(identity="p1", attrib={"caption": "P"}, events=[_event("E", "f(1);")])
    schema = _schema(routines=[_routine("f", ["integer"])], triggers=[_trigger("trg_guard")])

    index = routine_reference_index(ProjectModel(pages=[page]), schema)
    assert set(index) == {"public.f(integer)", "public.orders.trg_guard"}
    assert isinstance(index["public.f(integer)"], RoutineUsage)
    assert index["public.f(integer)"].referenced is True


def test_result_is_deterministic_across_runs():
    page = PageNode(
        identity="p1",
        attrib={"caption": "P", "b": "f()", "a": "f()"},
        sourceline=5,
        events=[_event("E", "f();", sourceline=6)],
    )
    schema = _schema(routines=[_routine("f")])

    first = collect_routine_references(ProjectModel(pages=[page]), schema)
    second = collect_routine_references(ProjectModel(pages=[page]), schema)
    assert [r.breadcrumb for r in first[0].references] == [
        "Page 'P' @a",
        "Page 'P' @b",
        "Page 'P' ▸ Event 'E'",
    ]
    assert [r.breadcrumb for r in first[0].references] == [
        r.breadcrumb for r in second[0].references
    ]


def test_node_without_sourceline_yields_a_none_line():
    page = PageNode(identity="p1", attrib={"caption": "P"}, events=[_event("E", "f();")])
    schema = _schema(routines=[_routine("f")])

    (usage,) = collect_routine_references(ProjectModel(pages=[page]), schema)
    assert [r.line for r in usage.references] == [None]
