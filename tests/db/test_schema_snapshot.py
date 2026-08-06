# tests/db/test_schema_snapshot.py
"""Pure tests for `DatabaseSchema` ↔ JSON snapshot round-tripping (no Qt, no live DB).

Canned data throughout, in `test_schema_diff.py`'s style: `dump_schema` /
`load_schema` take no runner and open no connection. Only the two
`write_snapshot`/`read_snapshot` tests touch the filesystem (via `tmp_path`),
because the text seam is where the whole contract lives.
"""
import dataclasses
import json

import pytest

from pgtp_editor.db import schema_snapshot
from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
    TypeInfo,
)
from pgtp_editor.db.schema_diff import diff_schemas
from pgtp_editor.db.schema_snapshot import (
    SNAPSHOT_FORMAT,
    SNAPSHOT_VERSION,
    SnapshotError,
    SnapshotFormatError,
    UnsupportedSnapshotVersion,
    dump_schema,
    load_schema,
    read_snapshot,
    write_snapshot,
)


def _column(name, **kwargs):
    fields = {
        "data_type": "integer",
        "is_pk": False,
        "is_fk": False,
        "is_nullable": True,
        "default": None,
    }
    fields.update(kwargs)
    return ColumnInfo(name=name, **fields)


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


def _full_schema() -> DatabaseSchema:
    """One schema exercising every field, including the optional/defaulted ones."""
    orders = TableInfo(
        name="pr.orders",
        kind="table",
        columns=[
            _column("id", is_pk=True, is_nullable=False, default="nextval('s')"),
            _column(
                "customer_id",
                is_fk=True,
                fk_target="pr.customers.id",
                comment="the paying party",
            ),
            _column("note", data_type="text", comment=None),
        ],
    )
    order_view = TableInfo(
        name="pr.order_v",
        kind="view",
        columns=[_column("id")],
        view_definition="SELECT id FROM pr.orders;",
    )
    return DatabaseSchema(
        tables={orders.name: orders, order_view.name: order_view},
        routines={
            "pr.touch()": RoutineInfo(
                schema="pr",
                name="touch",
                arg_types=["integer", "text"],
                return_type="trigger",
                language="plpgsql",
                source="CREATE FUNCTION pr.touch(...) ...",
                kind="function",
                args=[("id", "integer"), ("label", "text")],
            ),
            "pr.reap()": RoutineInfo(
                schema="pr",
                name="reap",
                arg_types=[],
                return_type=None,
                language="sql",
                source="CREATE PROCEDURE pr.reap() ...",
                kind="procedure",
            ),
        },
        triggers={
            "pr.orders.t_touch": TriggerInfo(
                schema="pr",
                table="orders",
                name="t_touch",
                timing="after",
                events=["insert", "update"],
                function_name="pr.touch",
                definition="CREATE TRIGGER t_touch ...",
            )
        },
        types={
            "pr.email": TypeInfo(
                schema="pr", name="email", kind="domain", base_type="text",
                not_null=True,
            ),
            "pr.pair": TypeInfo(
                schema="pr",
                name="pair",
                kind="composite",
                attributes=[("left", "integer"), ("right", "text")],
            ),
        },
    )


# --- the serializer covers the real dataclasses ------------------------------


@pytest.mark.parametrize(
    "cls, field_names",
    [
        (ColumnInfo, schema_snapshot.COLUMN_FIELDS),
        (TableInfo, schema_snapshot.TABLE_FIELDS),
        (RoutineInfo, schema_snapshot.ROUTINE_FIELDS),
        (TriggerInfo, schema_snapshot.TRIGGER_FIELDS),
        (TypeInfo, schema_snapshot.TYPE_FIELDS),
    ],
)
def test_snapshot_covers_every_dataclass_field(cls, field_names):
    # Drift guard: a field added to introspect.py must be added to the snapshot
    # too, or a snapshot silently drops it and a later diff sees a phantom change.
    assert tuple(f.name for f in dataclasses.fields(cls)) == tuple(field_names)


def test_schema_sections_match_database_schema_fields():
    assert tuple(f.name for f in dataclasses.fields(DatabaseSchema)) == tuple(
        schema_snapshot.SCHEMA_SECTIONS
    )


# --- round trip --------------------------------------------------------------


def test_round_trip_of_a_fully_populated_schema_is_equal():
    schema = _full_schema()
    assert load_schema(dump_schema(schema)) == schema


def test_round_trip_preserves_optional_and_defaulted_column_fields():
    loaded = load_schema(dump_schema(_full_schema()))
    columns = {c.name: c for c in loaded.tables["pr.orders"].columns}
    assert columns["customer_id"].comment == "the paying party"
    assert columns["customer_id"].fk_target == "pr.customers.id"
    assert columns["note"].comment is None
    assert columns["id"].is_pk is True and columns["id"].is_nullable is False
    assert loaded.tables["pr.order_v"].view_definition == "SELECT id FROM pr.orders;"


def test_round_trip_restores_args_as_tuples_not_lists():
    # `[("id", "integer")] != [["id", "integer"]]`, so the frozen dataclass would
    # never compare equal if the pairs came back as lists.
    loaded = load_schema(dump_schema(_full_schema()))
    assert loaded.routines["pr.touch()"].args == [("id", "integer"), ("label", "text")]
    assert loaded.types["pr.pair"].attributes == [("left", "integer"), ("right", "text")]


def test_round_trip_preserves_column_order():
    schema = _full_schema()
    reversed_columns = DatabaseSchema(
        tables={
            "pr.orders": dataclasses.replace(
                schema.tables["pr.orders"],
                columns=list(reversed(schema.tables["pr.orders"].columns)),
            )
        }
    )
    loaded = load_schema(dump_schema(reversed_columns))
    assert [c.name for c in loaded.tables["pr.orders"].columns] == [
        "note",
        "customer_id",
        "id",
    ]


def test_round_trip_of_an_empty_schema():
    assert load_schema(dump_schema(DatabaseSchema())) == DatabaseSchema()


def test_mapping_keys_are_preserved_verbatim_not_recomputed():
    # `diff_schemas` recomputes identity from each object, so a schema handed to
    # the snapshot may be keyed by anything; the snapshot must not "fix" keys.
    routine = _routine("f", ["integer"])
    schema = DatabaseSchema(routines={"whatever#0": routine})
    assert load_schema(dump_schema(schema)).routines == {"whatever#0": routine}


# --- determinism -------------------------------------------------------------


def test_two_dumps_of_equal_schemas_are_byte_identical():
    assert dump_schema(_full_schema()) == dump_schema(_full_schema())


def test_output_is_independent_of_dict_insertion_order():
    schema = _full_schema()
    shuffled = DatabaseSchema(
        tables=dict(reversed(list(schema.tables.items()))),
        routines=dict(reversed(list(schema.routines.items()))),
        triggers=dict(reversed(list(schema.triggers.items()))),
        types=dict(reversed(list(schema.types.items()))),
    )
    assert dump_schema(shuffled) == dump_schema(schema)


def test_output_is_indented_sorted_and_newline_terminated():
    text = dump_schema(_full_schema())
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert "\n  " in text  # indented, not a single line
    keys = list(json.loads(text)["schema"]["routines"])
    assert keys == sorted(keys)
    # Top-level keys sorted too, so the marker block is stable in a git diff.
    assert text.splitlines()[1].strip().startswith('"format"')


def test_snapshot_carries_no_connection_identity():
    schema = _full_schema()
    text = dump_schema(schema)
    payload = json.loads(text)
    assert set(payload) == {"format", "version", "schema"}
    for forbidden in ("password", "host", "port", "dsn", "user@"):
        assert forbidden not in text


# --- the version / format marker --------------------------------------------


def test_payload_announces_format_and_version():
    payload = json.loads(dump_schema(DatabaseSchema()))
    assert payload["format"] == SNAPSHOT_FORMAT
    assert payload["version"] == SNAPSHOT_VERSION


def test_unknown_version_is_rejected_by_name():
    payload = json.loads(dump_schema(_full_schema()))
    payload["version"] = SNAPSHOT_VERSION + 1
    with pytest.raises(UnsupportedSnapshotVersion) as excinfo:
        load_schema(json.dumps(payload))
    assert str(SNAPSHOT_VERSION + 1) in str(excinfo.value)


def test_unsupported_version_is_a_snapshot_error():
    # One `except SnapshotError` at a call site must catch both refusal kinds.
    assert issubclass(UnsupportedSnapshotVersion, SnapshotError)
    assert issubclass(SnapshotFormatError, SnapshotError)


def test_non_integer_version_is_a_format_error():
    payload = json.loads(dump_schema(DatabaseSchema()))
    payload["version"] = True  # a bool is an int in Python; must not read as 1
    with pytest.raises(SnapshotFormatError):
        load_schema(json.dumps(payload))


def test_foreign_format_marker_is_rejected():
    payload = json.loads(dump_schema(DatabaseSchema()))
    payload["format"] = "some-other-tool"
    with pytest.raises(SnapshotFormatError):
        load_schema(json.dumps(payload))


# --- rejection paths ---------------------------------------------------------


def test_malformed_json_is_rejected():
    with pytest.raises(SnapshotFormatError):
        load_schema("{not json")


def test_truncated_json_is_rejected():
    text = dump_schema(_full_schema())
    with pytest.raises(SnapshotFormatError):
        load_schema(text[: len(text) // 2])


@pytest.mark.parametrize("text", ["", "null", "[]", '"schema"', "42"])
def test_non_object_payloads_are_rejected(text):
    with pytest.raises(SnapshotFormatError):
        load_schema(text)


def test_missing_top_level_key_is_rejected():
    payload = json.loads(dump_schema(DatabaseSchema()))
    del payload["schema"]
    with pytest.raises(SnapshotFormatError, match="schema"):
        load_schema(json.dumps(payload))


def test_missing_schema_section_is_rejected_rather_than_defaulted():
    # The dangerous case: dropping "routines" must NOT load as an empty schema,
    # which would diff as "every routine was removed" and generate DROPs.
    payload = json.loads(dump_schema(_full_schema()))
    del payload["schema"]["routines"]
    with pytest.raises(SnapshotFormatError, match="routines"):
        load_schema(json.dumps(payload))


def test_missing_record_key_is_rejected():
    payload = json.loads(dump_schema(_full_schema()))
    del payload["schema"]["routines"]["pr.touch()"]["source"]
    with pytest.raises(SnapshotFormatError, match="source"):
        load_schema(json.dumps(payload))


def test_unrecognized_record_key_is_rejected():
    payload = json.loads(dump_schema(_full_schema()))
    payload["schema"]["triggers"]["pr.orders.t_touch"]["deferrable"] = True
    with pytest.raises(SnapshotFormatError, match="deferrable"):
        load_schema(json.dumps(payload))


def test_unrecognized_top_level_key_is_rejected():
    payload = json.loads(dump_schema(DatabaseSchema()))
    payload["connection"] = {"host": "db01"}
    with pytest.raises(SnapshotFormatError, match="connection"):
        load_schema(json.dumps(payload))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["schema"].__setitem__("tables", []),
        lambda p: p["schema"]["tables"]["pr.orders"].__setitem__("columns", {}),
        lambda p: p["schema"]["tables"]["pr.orders"].__setitem__("name", 7),
        lambda p: p["schema"]["tables"]["pr.orders"]["columns"][0].__setitem__(
            "is_pk", "true"
        ),
        lambda p: p["schema"]["tables"]["pr.orders"]["columns"][0].__setitem__(
            "comment", 3
        ),
        lambda p: p["schema"]["routines"]["pr.touch()"].__setitem__(
            "arg_types", "integer"
        ),
        lambda p: p["schema"]["routines"]["pr.touch()"].__setitem__("arg_types", [1]),
        lambda p: p["schema"]["routines"]["pr.touch()"].__setitem__("args", [["only"]]),
        lambda p: p["schema"]["routines"]["pr.touch()"].__setitem__("args", [["a", 2]]),
        lambda p: p["schema"]["triggers"]["pr.orders.t_touch"].__setitem__(
            "events", [None]
        ),
        lambda p: p["schema"]["triggers"]["pr.orders.t_touch"].__setitem__(
            "definition", None
        ),
        lambda p: p["schema"]["types"]["pr.email"].__setitem__("not_null", 1),
        lambda p: p["schema"]["types"]["pr.pair"].__setitem__("attributes", [["a"]]),
        lambda p: p["schema"]["routines"].__setitem__("pr.bad()", "CREATE FUNCTION"),
    ],
)
def test_wrong_types_are_rejected(mutate):
    payload = json.loads(dump_schema(_full_schema()))
    mutate(payload)
    with pytest.raises(SnapshotFormatError):
        load_schema(json.dumps(payload))


# --- the fidelity proof: a snapshot diffs clean against its source -----------


def test_dumped_then_loaded_schema_diffs_clean_against_the_original():
    schema = _full_schema()
    result = diff_schemas(load_schema(dump_schema(schema)), schema)
    assert list(result) == []
    # Tables are still reported as not-compared by the engine, unchanged by us.
    assert result.unsupported == ["pr.order_v", "pr.orders"]


def test_a_real_change_still_shows_up_through_a_snapshot():
    # The clean diff above is only meaningful if the snapshot can also carry a
    # difference: guard against "equal because both sides came out empty".
    schema = _full_schema()
    edited = DatabaseSchema(
        tables=schema.tables,
        routines={
            **schema.routines,
            "pr.reap()": dataclasses.replace(
                schema.routines["pr.reap()"], source="CREATE PROCEDURE pr.reap() v2"
            ),
        },
        triggers=schema.triggers,
        types=schema.types,
    )
    result = diff_schemas(load_schema(dump_schema(edited)), schema)
    assert [(d.kind, d.identity) for d in result] == [("changed", "pr.reap()")]


# --- the file seam -----------------------------------------------------------


def test_write_then_read_snapshot_round_trips(tmp_path):
    path = tmp_path / "schema.json"
    write_snapshot(_full_schema(), path)
    assert read_snapshot(path) == _full_schema()
    # LF only, so the committed file is byte-stable across Windows and Linux.
    assert b"\r\n" not in path.read_bytes()


def test_read_snapshot_of_a_missing_file_is_a_snapshot_format_error(tmp_path):
    with pytest.raises(SnapshotFormatError):
        read_snapshot(tmp_path / "nope.json")
