# tests/db/test_schema_index.py
"""Tests for pgtp_editor.db.schema_index -- pure, Qt-free lookup over a
`DatabaseSchema` (spec §18.6). No Qt import, no live database."""
from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
)
from pgtp_editor.db.schema_index import SchemaIndex


def _schema():
    tables = {
        "pr.equipment": TableInfo(
            name="pr.equipment",
            kind="table",
            columns=[
                ColumnInfo(
                    name="id", data_type="integer", is_pk=True, is_fk=False,
                    is_nullable=False, default=None,
                ),
                ColumnInfo(
                    name="tag", data_type="varchar", is_pk=False, is_fk=False,
                    is_nullable=True, default=None,
                ),
            ],
        ),
        "pr.eq_view": TableInfo(name="pr.eq_view", kind="view", columns=[]),
        "hr.employee": TableInfo(
            name="hr.employee",
            kind="table",
            columns=[
                ColumnInfo(
                    name="name", data_type="text", is_pk=False, is_fk=False,
                    is_nullable=True, default=None,
                ),
            ],
        ),
    }
    routines = {
        "pr.audit_log()": RoutineInfo(
            schema="pr", name="audit_log", arg_types=[], return_type="trigger",
            language="plpgsql", source="CREATE FUNCTION pr.audit_log() ...",
            kind="function",
        ),
        "pr.calc_total(integer)": RoutineInfo(
            schema="pr", name="calc_total", arg_types=["integer"],
            return_type="numeric", language="plpgsql", source="...",
            kind="function",
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


def test_known_schemas_sorted():
    index = SchemaIndex(_schema())
    assert index.known_schemas() == ["hr", "pr"]


def test_known_schemas_empty_when_no_tables():
    index = SchemaIndex(DatabaseSchema())
    assert index.known_schemas() == []


def test_known_tables_lists_bare_names_for_schema():
    index = SchemaIndex(_schema())
    assert index.known_tables("pr") == ["eq_view", "equipment"]


def test_known_tables_prefix_filters_case_insensitive():
    index = SchemaIndex(_schema())
    assert index.known_tables("pr", "Eq") == ["eq_view", "equipment"]
    assert index.known_tables("pr", "equi") == ["equipment"]


def test_known_tables_unknown_schema_is_empty():
    index = SchemaIndex(_schema())
    assert index.known_tables("nosuch") == []


def test_known_columns_schema_qualified_key():
    index = SchemaIndex(_schema())
    assert index.known_columns("pr.equipment") == ["id", "tag"]


def test_known_columns_unknown_table_is_empty():
    index = SchemaIndex(_schema())
    assert index.known_columns("pr.nosuch") == []


def test_known_columns_view_with_no_columns():
    index = SchemaIndex(_schema())
    assert index.known_columns("pr.eq_view") == []


def test_column_entries_pairs_the_bare_name_with_a_typed_display():
    """The popup's `(key, display)` shape: the key is exactly what
    `known_columns` returns (it is what gets inserted), the display carries
    the type so `id integer` is distinguishable from `id text`."""
    index = SchemaIndex(_schema())
    entries = index.column_entries("pr.equipment")
    assert [key for key, _ in entries] == index.known_columns("pr.equipment")
    assert entries[0] == ("id", "id  integer · PK · NOT NULL")
    assert entries[1] == ("tag", "tag  varchar")


def test_column_entries_prefix_filters_case_insensitive():
    index = SchemaIndex(_schema())
    assert [key for key, _ in index.column_entries("pr.equipment", "T")] == ["tag"]


def test_column_entries_unknown_table_is_empty():
    index = SchemaIndex(_schema())
    assert index.column_entries("pr.nosuch") == []


def test_column_entries_unknown_column_prefix_is_empty():
    index = SchemaIndex(_schema())
    assert index.column_entries("pr.equipment", "nosuch") == []


def test_column_entries_view_with_no_columns():
    index = SchemaIndex(_schema())
    assert index.column_entries("pr.eq_view") == []


def test_column_entries_renders_every_interesting_attribute():
    schema = _schema()
    schema.tables["hr.jobcard"] = TableInfo(
        name="hr.jobcard",
        kind="table",
        columns=[
            ColumnInfo(
                name="id", data_type="integer", is_pk=True, is_fk=False,
                is_nullable=False, default="nextval('hr.jobcard_id_seq')",
            ),
            ColumnInfo(
                name="dept_id", data_type="integer", is_pk=False, is_fk=True,
                is_nullable=False, default=None, fk_target="hr.dept.id",
            ),
            ColumnInfo(
                name="note", data_type="text", is_pk=False, is_fk=False,
                is_nullable=True, default=None, comment="free-text remark",
            ),
            ColumnInfo(
                name="orphan_fk", data_type="integer", is_pk=False, is_fk=True,
                is_nullable=True, default=None, fk_target=None,
            ),
        ],
    )
    displays = dict(SchemaIndex(schema).column_entries("hr.jobcard"))
    assert displays["id"] == (
        "id  integer · PK · NOT NULL · default nextval('hr.jobcard_id_seq')"
    )
    assert displays["dept_id"] == "dept_id  integer · → hr.dept.id · NOT NULL"
    assert displays["note"] == "note  text · free-text remark"
    # An FK whose target could not be resolved still says it is one.
    assert displays["orphan_fk"] == "orphan_fk  integer · FK"


def test_column_entries_elides_an_overlong_attribute():
    schema = _schema()
    schema.tables["hr.wordy"] = TableInfo(
        name="hr.wordy",
        kind="table",
        columns=[
            ColumnInfo(
                name="c", data_type="text", is_pk=False, is_fk=False,
                is_nullable=True, default=None, comment="x" * 200,
            ),
        ],
    )
    display = dict(SchemaIndex(schema).column_entries("hr.wordy"))["c"]
    assert display.endswith("…")
    assert len(display) < 80


def test_known_columns_is_unchanged_by_the_richer_accessor():
    """The regression that matters: the two live callers
    (`ui/ddl_object_editor.py`, `ui/sql_console_panel.py`) still get bare
    name strings, in table order, from the same `"schema.table"` key."""
    index = SchemaIndex(_schema())
    names = index.known_columns("pr.equipment")
    assert names == ["id", "tag"]
    assert all(isinstance(name, str) for name in names)
    assert index.known_columns("hr.employee") == ["name"]
    assert index.known_columns("pr.eq_view") == []
    assert index.known_columns("pr.nosuch") == []


def test_column_infos_returns_real_column_objects():
    """BUG-045: the accessor publishes `ColumnInfo`, not names and not display
    strings -- `fk_target`/`is_pk`/`default` are reachable through it."""
    schema = _schema()
    schema.tables["pr.equipment"].columns.append(
        ColumnInfo(
            name="owner_id", data_type="integer", is_pk=False, is_fk=True,
            is_nullable=False, default="0", fk_target="hr.employee.id",
        )
    )
    columns = SchemaIndex(schema).column_infos("pr.equipment")
    assert [column.name for column in columns] == ["id", "tag", "owner_id"]
    assert columns[0].is_pk is True
    assert columns[2].fk_target == "hr.employee.id"
    assert columns[2].default == "0"


def test_column_infos_empty_for_unknown_table():
    index = SchemaIndex(_schema())
    assert index.column_infos("pr.nosuch") == []
    assert index.column_infos("pr.eq_view") == []


def test_column_infos_returns_a_copy_the_caller_cannot_damage():
    """The list is the caller's to sort or trim; the fetch behind
    `known_columns`/`column_entries` must not move with it."""
    index = SchemaIndex(_schema())
    columns = index.column_infos("pr.equipment")
    columns.clear()
    assert index.column_infos("pr.equipment") != []
    assert index.known_columns("pr.equipment") == ["id", "tag"]
    assert [key for key, _ in index.column_entries("pr.equipment")] == ["id", "tag"]


def test_column_entries_is_unchanged_by_the_richer_accessor():
    """The sibling of `test_known_columns_is_unchanged_by_the_richer_accessor`:
    §18.6 completion still gets `(key, display)` pairs with bare-name keys."""
    entries = SchemaIndex(_schema()).column_entries("pr.equipment")
    assert [key for key, _ in entries] == ["id", "tag"]
    assert all(isinstance(display, str) for _, display in entries)


def test_routines_returns_every_fetched_routine_in_order():
    routines = SchemaIndex(_schema()).routines()
    assert isinstance(routines, tuple)
    assert [routine.name for routine in routines] == ["audit_log", "calc_total"]
    assert routines[1].return_type == "numeric"


def test_routines_keeps_overloads_as_separate_entries():
    """`DatabaseSchema.routines` is keyed by the full signature (§18.1), so two
    overloads of one name are two entries -- signature help ranks them."""
    schema = _schema()
    schema.routines["pr.calc_total(text)"] = RoutineInfo(
        schema="pr", name="calc_total", arg_types=["text"],
        return_type="numeric", language="plpgsql", source="...",
        kind="function",
    )
    routines = SchemaIndex(schema).routines()
    overloads = [r for r in routines if r.name == "calc_total"]
    assert [r.arg_types for r in overloads] == [["integer"], ["text"]]


def test_routines_empty_for_a_tables_only_schema():
    """`fetch_schema`'s shape: tables but no routines."""
    schema = DatabaseSchema(tables=_schema().tables)
    assert SchemaIndex(schema).routines() == ()


def test_trigger_for_function_finds_attached_trigger():
    index = SchemaIndex(_schema())
    trigger = index.trigger_for_function("pr", "audit_log")
    assert trigger is not None
    assert trigger.table == "equipment"
    assert trigger.name == "trg_audit"


def test_trigger_for_function_none_when_unattached():
    index = SchemaIndex(_schema())
    assert index.trigger_for_function("pr", "calc_total") is None


def test_trigger_for_function_none_when_name_unknown():
    index = SchemaIndex(_schema())
    assert index.trigger_for_function("pr", "nosuch") is None


def test_trigger_for_function_disambiguates_by_schema():
    schema = _schema()
    schema.triggers["hr.employee.trg_other"] = TriggerInfo(
        schema="hr", table="employee", name="trg_other", timing="before",
        events=["update"], function_name="audit_log", definition="...",
    )
    index = SchemaIndex(schema)
    assert index.trigger_for_function("pr", "audit_log").schema == "pr"
    assert index.trigger_for_function("hr", "audit_log").schema == "hr"


def test_trigger_for_function_falls_back_when_schema_not_matched():
    """No candidate matches `schema` exactly (stale/mismatched caller data) --
    returns the first candidate rather than silently reporting unattached."""
    index = SchemaIndex(_schema())
    trigger = index.trigger_for_function("other_schema", "audit_log")
    assert trigger is not None
    assert trigger.function_name == "audit_log"
