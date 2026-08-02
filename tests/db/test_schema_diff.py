# tests/db/test_schema_diff.py
"""Pure tests for `DatabaseSchema` → `SchemaDifference` diffing (no Qt, no live DB).

Every case here is canned data: `diff_schemas` takes no runner and opens no
connection, so these tests never touch psycopg.
"""
import dataclasses
import inspect

from pgtp_editor.db import schema_diff
from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
)
from pgtp_editor.db.schema_diff import (
    SchemaDifference,
    diff_schemas,
    routine_identity,
    trigger_identity,
)


def _routine(name, arg_types=(), source="BODY", language="plpgsql", schema="pr"):
    return RoutineInfo(
        schema=schema,
        name=name,
        arg_types=list(arg_types),
        return_type="void",
        language=language,
        source=source,
    )


def _trigger(name, table="t", definition="CREATE TRIGGER", schema="pr"):
    return TriggerInfo(
        schema=schema,
        table=table,
        name=name,
        timing="before",
        events=["insert"],
        function_name="pr.f",
        definition=definition,
    )


def _schema(routines=(), triggers=(), tables=()):
    # Deliberately NOT the keying `fetch_routines_and_triggers` uses (it keys
    # by the full signature since BUG-018). The mismatch is the regression
    # guard for `_by_identity`: `diff_schemas` must recompute identity from
    # each object's own fields and never trust the mapping's key -- a schema
    # handed to the diff can be built by anyone (see the overload test below).
    return DatabaseSchema(
        tables={t.name: t for t in tables},
        routines={f"{r.schema}.{r.name}#{i}": r for i, r in enumerate(routines)},
        triggers={f"{t.schema}.{t.table}.{t.name}": t for t in triggers},
    )


# --- the §18.3 record shape -------------------------------------------------


def test_difference_has_the_verbatim_18_3_fields():
    names = [f.name for f in dataclasses.fields(SchemaDifference)]
    # §18.3 fixes the first five verbatim; `language` is the Task 1 sibling.
    assert names[:5] == ["kind", "object_kind", "identity", "old_def", "new_def"]
    assert "language" in names


def test_difference_is_frozen():
    difference = SchemaDifference("added", "routine", "pr.f()", None, "x")
    try:
        difference.kind = "removed"
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("SchemaDifference must be frozen")


# --- identity ---------------------------------------------------------------


def test_routine_identity_is_the_full_signature():
    assert routine_identity(_routine("f")) == "pr.f()"
    assert routine_identity(_routine("f", ["integer"])) == "pr.f(integer)"
    assert (
        routine_identity(_routine("f", ["integer", "text"])) == "pr.f(integer, text)"
    )


def test_trigger_identity_is_schema_table_name():
    assert trigger_identity(_trigger("trg", table="orders")) == "pr.orders.trg"


# --- routines ---------------------------------------------------------------


def test_routine_only_in_source_is_added():
    source = _schema(routines=[_routine("f", ["integer"], source="NEW")])
    result = diff_schemas(source, _schema())
    assert result == [
        SchemaDifference(
            kind="added",
            object_kind="routine",
            identity="pr.f(integer)",
            old_def=None,
            new_def="NEW",
            language="plpgsql",
        )
    ]


def test_routine_only_in_target_is_removed():
    target = _schema(routines=[_routine("f", ["integer"], source="OLD")])
    result = diff_schemas(_schema(), target)
    assert result == [
        SchemaDifference(
            kind="removed",
            object_kind="routine",
            identity="pr.f(integer)",
            old_def="OLD",
            new_def=None,
            language="plpgsql",
        )
    ]


def test_differing_source_is_changed_and_carries_both_defs():
    source = _schema(routines=[_routine("f", ["integer"], source="NEW")])
    target = _schema(routines=[_routine("f", ["integer"], source="OLD")])
    (difference,) = diff_schemas(source, target)
    assert difference.kind == "changed"
    assert difference.identity == "pr.f(integer)"
    assert difference.old_def == "OLD"
    assert difference.new_def == "NEW"


def test_identical_routines_produce_no_difference():
    source = _schema(routines=[_routine("f", ["integer"], source="SAME")])
    target = _schema(routines=[_routine("f", ["integer"], source="SAME")])
    assert diff_schemas(source, target) == []


def test_argument_type_change_is_removed_plus_added_never_changed():
    # R14: `calc_total(integer)` → `calc_total(bigint)` is two identities, not
    # one changed one. A bare CREATE OR REPLACE would leave the old function
    # live and create a second overload.
    source = _schema(routines=[_routine("calc_total", ["bigint"], source="NEW")])
    target = _schema(routines=[_routine("calc_total", ["integer"], source="OLD")])
    result = diff_schemas(source, target)
    assert {(d.kind, d.identity) for d in result} == {
        ("added", "pr.calc_total(bigint)"),
        ("removed", "pr.calc_total(integer)"),
    }
    assert all(d.kind != "changed" for d in result)


def test_overloads_of_one_name_are_independent_identities():
    source = _schema(
        routines=[
            _routine("f", ["integer"], source="INT"),
            _routine("f", ["text"], source="TEXT-NEW"),
        ]
    )
    target = _schema(routines=[_routine("f", ["text"], source="TEXT-OLD")])
    result = diff_schemas(source, target)
    assert [(d.kind, d.identity) for d in result] == [
        ("added", "pr.f(integer)"),
        ("changed", "pr.f(text)"),
    ]


def test_overloads_survive_a_diff_of_schemas_keyed_the_way_introspection_keys_them():
    """The realistic shape: both sides built with `RoutineInfo.signature` keys,
    exactly as `fetch_routines_and_triggers` now builds them (BUG-018).

    Only the changed overload may appear -- its sibling must not be dragged in.
    """

    def introspected(*routines):
        return DatabaseSchema(routines={r.signature: r for r in routines})

    untouched = _routine("f", ["integer"], source="SAME")
    source = introspected(untouched, _routine("f", ["text"], source="NEW"))
    target = introspected(untouched, _routine("f", ["text"], source="OLD"))

    assert set(source.routines) == {"pr.f(integer)", "pr.f(text)"}
    result = diff_schemas(source, target)
    assert [(d.kind, d.identity) for d in result] == [("changed", "pr.f(text)")]


def test_routine_identity_delegates_to_the_routine_infos_own_signature():
    # One implementation of the string, shared with the `routines` dict key and
    # `build_ddl_text`'s banner comment -- re-rendering it is how the four
    # spellings drifted apart in the first place (BUG-018).
    for routine in (_routine("f"), _routine("f", ["integer", "text"])):
        assert routine_identity(routine) == routine.signature


def test_identity_comes_from_the_object_not_the_schema_dict_key():
    # R14 again, from the other side: a schema handed to the diff can be keyed
    # by anything -- here by a bare "schema.name", which cannot represent an
    # overload. If `diff_schemas` ever keyed off those dict keys instead of
    # `arg_types`, an argument-type change would look like one `changed`
    # routine.
    source = DatabaseSchema(
        tables={},
        routines={"pr.f": _routine("f", ["bigint"], source="NEW")},
        triggers={},
    )
    target = DatabaseSchema(
        tables={},
        routines={"pr.f": _routine("f", ["integer"], source="OLD")},
        triggers={},
    )
    result = diff_schemas(source, target)
    assert [(d.kind, d.identity) for d in result] == [
        ("added", "pr.f(bigint)"),
        ("removed", "pr.f(integer)"),
    ]


def test_misleading_schema_dict_keys_do_not_reach_the_identity():
    source = DatabaseSchema(
        tables={},
        routines={"totally-bogus-key": _routine("f", ["text"], source="NEW")},
        triggers={"another-bogus-key": _trigger("trg", table="orders", definition="N")},
    )
    result = diff_schemas(source, _schema())
    assert [d.identity for d in result] == ["pr.f(text)", "pr.orders.trg"]


def test_argtype_change_pair_carries_each_side_definition_once():
    # The `removed` half must carry only `old_def` and the `added` half only
    # `new_def`: an emitter that saw both populated could mistake the pair for
    # a replaceable change.
    source = _schema(routines=[_routine("calc", ["bigint"], source="NEW")])
    target = _schema(routines=[_routine("calc", ["integer"], source="OLD")])
    added, removed = sorted(diff_schemas(source, target), key=lambda d: d.kind)
    assert (added.kind, added.old_def, added.new_def) == ("added", None, "NEW")
    assert (removed.kind, removed.old_def, removed.new_def) == ("removed", "OLD", None)


def test_language_is_threaded_onto_the_difference():
    source = _schema(routines=[_routine("f", source="NEW", language="sql")])
    target = _schema(routines=[_routine("f", source="OLD", language="sql")])
    (difference,) = diff_schemas(source, target)
    assert difference.language == "sql"


def test_removed_routine_carries_the_target_side_language():
    target = _schema(routines=[_routine("f", source="OLD", language="c")])
    (difference,) = diff_schemas(_schema(), target)
    assert difference.language == "c"


# --- triggers ---------------------------------------------------------------


def test_trigger_changed_on_the_same_table():
    source = _schema(triggers=[_trigger("trg", table="t", definition="NEW")])
    target = _schema(triggers=[_trigger("trg", table="t", definition="OLD")])
    assert diff_schemas(source, target) == [
        SchemaDifference(
            kind="changed",
            object_kind="trigger",
            identity="pr.t.trg",
            old_def="OLD",
            new_def="NEW",
            language="",
        )
    ]


def test_same_trigger_name_on_two_tables_is_two_identities():
    source = _schema(
        triggers=[
            _trigger("audit", table="orders", definition="A"),
            _trigger("audit", table="items", definition="B"),
        ]
    )
    result = diff_schemas(source, _schema())
    assert [d.identity for d in result] == ["pr.items.audit", "pr.orders.audit"]


def test_trigger_added_and_removed():
    source = _schema(triggers=[_trigger("new_trg", definition="N")])
    target = _schema(triggers=[_trigger("old_trg", definition="O")])
    result = diff_schemas(source, target)
    assert {(d.kind, d.identity) for d in result} == {
        ("added", "pr.t.new_trg"),
        ("removed", "pr.t.old_trg"),
    }


# --- the deliberately-unimplemented table/column half -----------------------


def test_tables_produce_no_differences_but_are_listed_unsupported():
    table = TableInfo(
        name="pr.a",
        kind="table",
        columns=[ColumnInfo("id", "integer", True, False, False, None)],
    )
    other = TableInfo(name="pr.b", kind="table", columns=[])
    source = _schema(tables=[table, other])
    target = _schema(tables=[table])
    result = diff_schemas(source, target)
    assert result == []
    assert result.unsupported == ["pr.a", "pr.b"]


def test_unsupported_is_empty_when_neither_side_has_tables():
    assert diff_schemas(_schema(), _schema()).unsupported == []


def test_empty_vs_empty_is_the_empty_list():
    result = diff_schemas(_schema(), _schema())
    assert result == []
    assert list(result) == []


def test_result_is_a_plain_list_carrying_the_unsupported_sidecar():
    # §18.3 fixes the return type as `list[SchemaDifference]`; the sidecar must
    # not cost the caller normal list behaviour (len/index/iterate/unpack).
    table = TableInfo(name="pr.a", kind="table", columns=[])
    source = _schema(routines=[_routine("f", source="NEW")], tables=[table])
    result = diff_schemas(source, _schema())
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].identity == "pr.f()"
    assert [d.identity for d in result] == ["pr.f()"]
    assert result.unsupported == ["pr.a"]


def test_tables_only_on_one_side_are_still_reported_unsupported():
    # A table added in the sandbox is precisely the case a table-blind diff
    # would hide; it must show up in `unsupported`, not vanish.
    source = _schema(tables=[TableInfo(name="pr.new_table", kind="table", columns=[])])
    result = diff_schemas(source, _schema())
    assert result == []
    assert result.unsupported == ["pr.new_table"]


def test_views_and_other_table_kinds_are_reported_unsupported_too():
    view = TableInfo(name="pr.v", kind="view", columns=[])
    result = diff_schemas(_schema(tables=[view]), _schema())
    assert result.unsupported == ["pr.v"]


# --- the sidecar must survive what a real caller does to the list -----------


def _result_with_unsupported():
    tables = [
        TableInfo(name="pr.a", kind="table", columns=[]),
        TableInfo(name="pr.b", kind="table", columns=[]),
    ]
    source = _schema(
        routines=[_routine("f", source="F"), _routine("g", source="G")],
        triggers=[_trigger("trg", definition="T")],
        tables=tables,
    )
    result = diff_schemas(source, _schema())
    assert result.unsupported == ["pr.a", "pr.b"]  # precondition
    return result


def test_unsupported_survives_slicing():
    # "show me the first N differences" must not silently drop the
    # "table changes were not compared" notice.
    result = _result_with_unsupported()
    assert result[:2].unsupported == ["pr.a", "pr.b"]
    assert [d.identity for d in result[:2]] == ["pr.f()", "pr.g()"]
    assert result[:].unsupported == ["pr.a", "pr.b"]


def test_unsupported_survives_copy():
    assert _result_with_unsupported().copy().unsupported == ["pr.a", "pr.b"]


def test_unsupported_survives_concatenation_in_either_operand_order():
    result = _result_with_unsupported()
    extra = [SchemaDifference("added", "routine", "pr.z()", None, "Z")]
    assert (result + extra).unsupported == ["pr.a", "pr.b"]
    assert (extra + result).unsupported == ["pr.a", "pr.b"]
    assert len(result + extra) == len(result) + 1
    assert len(extra + result) == len(result) + 1


def test_concatenating_two_results_unions_their_unsupported_names():
    first = diff_schemas(
        _schema(tables=[TableInfo(name="pr.a", kind="table", columns=[])]), _schema()
    )
    second = diff_schemas(
        _schema(tables=[TableInfo(name="pr.b", kind="table", columns=[])]), _schema()
    )
    assert (first + second).unsupported == ["pr.a", "pr.b"]


def test_indexing_one_element_still_returns_a_difference_not_a_result():
    result = _result_with_unsupported()
    assert isinstance(result[0], SchemaDifference)


def test_result_still_compares_equal_to_a_plain_list():
    # Load-bearing: it is why §18.3's `-> list[SchemaDifference]` is not
    # violated by the sidecar.
    result = diff_schemas(_schema(routines=[_routine("f", source="F")]), _schema())
    assert result == [
        SchemaDifference("added", "routine", "pr.f()", None, "F", "plpgsql")
    ]
    assert diff_schemas(_schema(), _schema()) == []


def test_comprehension_and_sorted_drop_the_sidecar_by_design():
    # Pinned, not accidental: the language always builds a plain `list` here,
    # so the defence is `diff_schemas`' docstring ("read .unsupported at the
    # call site, before filtering"), not code. If this ever starts passing,
    # the sidecar became free -- update the docs with it.
    result = _result_with_unsupported()
    assert not hasattr([d for d in result if d.kind == "added"], "unsupported")
    assert not hasattr(sorted(result, key=lambda d: d.identity), "unsupported")
    assert not hasattr(list(result), "unsupported")


# --- determinism ------------------------------------------------------------


def test_output_order_is_deterministic_routines_then_triggers():
    source = _schema(
        routines=[_routine("z"), _routine("a"), _routine("m")],
        triggers=[_trigger("z_trg", table="t"), _trigger("a_trg", table="t")],
    )
    result = diff_schemas(source, _schema())
    assert [d.identity for d in result] == [
        "pr.a()",
        "pr.m()",
        "pr.z()",
        "pr.t.a_trg",
        "pr.t.z_trg",
    ]


def test_two_runs_over_identical_input_agree():
    source = _schema(routines=[_routine("f", ["integer"], source="NEW")])
    target = _schema(routines=[_routine("g", source="OLD")])
    assert diff_schemas(source, target) == diff_schemas(source, target)


# --- purity guards ----------------------------------------------------------


def test_module_is_qt_free_and_psycopg_free():
    # Import lines only -- the docstring names both on purpose.
    offenders = [
        line
        for line in inspect.getsource(schema_diff).splitlines()
        if line.startswith(("import ", "from ")) and ("PySide6" in line or "psycopg" in line)
    ]
    assert offenders == []


def test_diff_schemas_takes_no_runner():
    parameters = list(inspect.signature(diff_schemas).parameters)
    assert parameters == ["source", "target"]
