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


def _calc_col(field_name):
    # BUG-006: a generator-computed column with no physical DB counterpart.
    return ColumnNode(
        identity=field_name,
        attrib={"fieldName": field_name, "isCalculated": "true"},
    )


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
    # BUG-006: field names now map to their is_calculated flag (all False
    # here); name membership (`in`) still works as before.
    cols = xml_table_columns(_make_project())
    assert cols == {
        "pr.a": {"id": False, "name": False, "extra": False},
        "pr.b": {"b_id": False},
    }


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


# -- calculated columns (BUG-006) -----------------------------------------


def test_xml_table_columns_carries_calculated_flag():
    project = ProjectModel(
        pages=[
            PageNode(
                identity="p",
                attrib={"tableName": "pr.a"},
                columns=[_col("id"), _calc_col("total")],
            )
        ]
    )
    assert xml_table_columns(project) == {"pr.a": {"id": False, "total": True}}


def test_xml_table_columns_ors_calculated_across_union():
    # One page marks the field calculated, another references the same field
    # without the attribute → still calculated (OR precedence), regardless of
    # page order.
    calc_first = ProjectModel(
        pages=[
            PageNode(identity="p1", attrib={"tableName": "pr.a"},
                     columns=[_calc_col("total")]),
            PageNode(identity="p2", attrib={"tableName": "pr.a"},
                     columns=[_col("total")]),
        ]
    )
    plain_first = ProjectModel(
        pages=[
            PageNode(identity="p1", attrib={"tableName": "pr.a"},
                     columns=[_col("total")]),
            PageNode(identity="p2", attrib={"tableName": "pr.a"},
                     columns=[_calc_col("total")]),
        ]
    )
    assert xml_table_columns(calc_first) == {"pr.a": {"total": True}}
    assert xml_table_columns(plain_first) == {"pr.a": {"total": True}}


def test_xml_table_columns_calculated_in_nested_detail():
    project = ProjectModel(
        pages=[
            PageNode(
                identity="p",
                attrib={"tableName": "pr.a"},
                columns=[_col("id")],
                details=[
                    DetailNode(
                        identity="d",
                        attrib={"tableName": "pr.b"},
                        columns=[_calc_col("derived")],
                    )
                ],
            )
        ]
    )
    assert xml_table_columns(project)["pr.b"] == {"derived": True}


def test_check_xml_against_db_flags_calculated_columns():
    project = ProjectModel(
        pages=[
            PageNode(
                identity="p",
                attrib={"tableName": "pr.a"},
                # "total" is calculated and has no DB column; "name" is
                # calculated but shadows a real DB column; "id" is plain.
                columns=[_col("id"), _calc_col("total"), _calc_col("name")],
            )
        ]
    )
    checks = check_xml_against_db(project, _make_schema())
    a_cols = {c.name: c for c in checks[0].columns}

    assert a_cols["id"].is_calculated is False
    assert a_cols["id"].ok is True

    # `ok` stays "does a matching DB column literally exist" (informational);
    # is_calculated is carried alongside for consumers to override with.
    assert a_cols["total"].is_calculated is True
    assert a_cols["total"].ok is False
    assert a_cols["total"].info is None

    assert a_cols["name"].is_calculated is True
    assert a_cols["name"].ok is True
    assert a_cols["name"].info is not None


def test_check_db_against_xml_never_flags_calculated():
    # DB→XML iterates real DB columns; a calculated XML column with no DB
    # counterpart never appears, and DB rows default to is_calculated=False.
    project = ProjectModel(
        pages=[
            PageNode(
                identity="p",
                attrib={"tableName": "pr.a"},
                columns=[_col("id"), _calc_col("total")],
            )
        ]
    )
    checks = check_db_against_xml(project, _make_schema())
    a = next(c for c in checks if c.name == "pr.a")
    names = [c.name for c in a.columns]
    assert "total" not in names
    assert all(c.is_calculated is False for c in a.columns)


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
