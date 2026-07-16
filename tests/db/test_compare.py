# tests/db/test_compare.py
"""Pure tests for XML↔DB comparison (no Qt, no live DB)."""
from pgtp_editor.db.compare import (
    ColumnCheck,
    TableCheck,
    check_db_against_xml,
    check_xml_against_db,
    xml_table_columns,
    xml_table_invocations,
)
from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.model.nodes import ColumnNode, DetailNode, PageNode, ProjectModel


def _col(field_name):
    return ColumnNode(identity=field_name, attrib={"fieldName": field_name})


def _make_project():
    # Page bound to pr.a with columns id, name.
    # Nested detail bound to pr.b with column b_id.
    # Second page also bound to pr.a with column extra (columns union).
    page1 = PageNode(
        identity="p1",
        attrib={"tableName": "pr.a"},
        columns=[_col("id"), _col("name")],
        details=[
            DetailNode(
                identity="d1",
                attrib={"tableName": "pr.b"},
                columns=[_col("b_id")],
            )
        ],
    )
    page2 = PageNode(
        identity="p2",
        attrib={"tableName": "pr.a"},
        columns=[_col("extra")],
    )
    return ProjectModel(pages=[page1, page2])


def _make_schema():
    a = TableInfo(
        name="pr.a",
        kind="table",
        columns=[
            ColumnInfo("id", "integer", True, False, False, "nextval('s')"),
            ColumnInfo("name", "varchar(255)", False, False, True, None),
            ColumnInfo("db_only", "text", False, True, True, None),
        ],
    )
    v = TableInfo(
        name="pr.v",
        kind="view",
        columns=[ColumnInfo("vc", "integer", False, False, True, None)],
    )
    return DatabaseSchema(tables={"pr.a": a, "pr.v": v})


def test_xml_table_columns_unions_and_recurses():
    cols = xml_table_columns(_make_project())
    assert cols == {"pr.a": {"id", "name", "extra"}, "pr.b": {"b_id"}}


def test_xml_table_columns_skips_empty_names():
    project = ProjectModel(
        pages=[PageNode(identity="p", attrib={}, columns=[_col("x")])]
    )
    assert xml_table_columns(project) == {}


def test_xml_table_invocations_counts_references():
    inv = xml_table_invocations(_make_project())
    # pr.a referenced by two pages; pr.b by one detail.
    assert inv["pr.a"] == 2
    assert inv["pr.b"] == 1


def test_check_xml_against_db_directions():
    checks = check_xml_against_db(_make_project(), _make_schema())
    by_name = {c.name: c for c in checks}
    # Sorted by table name.
    assert [c.name for c in checks] == sorted(by_name)

    a = by_name["pr.a"]
    assert a.ok is True
    assert a.kind == "table"
    assert a.invocations == 2
    a_cols = {c.name: c for c in a.columns}
    # Columns sorted.
    assert [c.name for c in a.columns] == sorted(a_cols)
    assert a_cols["id"].ok is True
    assert a_cols["id"].info is not None
    assert a_cols["id"].info.is_pk is True
    assert a_cols["extra"].ok is False  # not in DB
    assert a_cols["extra"].info is None

    b = by_name["pr.b"]
    assert b.ok is False  # table missing in DB
    assert b.kind is None
    assert b.invocations == 1
    # Columns under a missing table are all ok=False with no info.
    assert all(c.ok is False and c.info is None for c in b.columns)


def test_check_db_against_xml_directions():
    checks = check_db_against_xml(_make_project(), _make_schema())
    by_name = {c.name: c for c in checks}
    assert [c.name for c in checks] == sorted(by_name)

    a = by_name["pr.a"]
    assert a.ok is True  # pr.a is referenced in XML
    assert a.kind == "table"
    assert a.invocations == 2
    a_cols = {c.name: c for c in a.columns}
    assert a_cols["id"].ok is True  # id present in XML
    assert a_cols["id"].info is not None
    assert a_cols["db_only"].ok is False  # db column not in XML
    assert a_cols["db_only"].info is not None  # DB metadata attached
    assert a_cols["db_only"].info.is_fk is True

    v = by_name["pr.v"]
    assert v.ok is False  # view not referenced in XML
    assert v.kind == "view"
    assert v.invocations == 0
