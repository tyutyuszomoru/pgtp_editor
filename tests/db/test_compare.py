# tests/db/test_compare.py
"""Pure tests for XML↔DB comparison (no Qt, no live DB)."""
from pgtp_editor.db.compare import (
    ColumnCheck,
    TableCheck,
    check_db_against_xml,
    check_xml_against_db,
    xml_table_columns,
    xml_table_invocations,
    xml_table_role_counts,
)
from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.model.nodes import (
    ChildElement,
    ColumnNode,
    DetailNode,
    PageNode,
    ProjectModel,
)


def _col(field_name):
    return ColumnNode(identity=field_name, attrib={"fieldName": field_name})


def _lookup_col(field_name, lookup_table):
    # BUG-026: a column whose <Lookup> targets another table — a reference that
    # `xml_table_columns` deliberately never records, but which still counts as
    # "the XML uses this table".
    return ColumnNode(
        identity=field_name,
        attrib={"fieldName": field_name},
        lookup=ChildElement(attrib={"tableName": lookup_table}),
    )


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


# -- role-split reference counts (BUG-026) --------------------------------


def _role_project():
    # pr.a: two page bindings + one lookup from a detail column.
    # pr.b: one detail binding + one lookup from a page column.
    # pr.look: lookup target only (never bound to a page/detail).
    page1 = PageNode(
        identity="p1",
        attrib={"tableName": "pr.a"},
        columns=[_col("id"), _lookup_col("b_ref", "pr.b")],
        details=[
            DetailNode(
                identity="d1",
                attrib={"tableName": "pr.b"},
                columns=[_lookup_col("a_ref", "pr.a"), _lookup_col("l", "pr.look")],
            )
        ],
    )
    page2 = PageNode(
        identity="p2",
        attrib={"tableName": "pr.a"},
        columns=[_lookup_col("l2", "pr.look")],
    )
    return ProjectModel(pages=[page1, page2])


def test_xml_table_role_counts_splits_by_role():
    roles = xml_table_role_counts(_role_project())
    assert roles["pr.a"] == {"page": 2, "detail": 0, "lookup": 1}
    assert roles["pr.b"] == {"page": 0, "detail": 1, "lookup": 1}
    assert roles["pr.look"] == {"page": 0, "detail": 0, "lookup": 2}
    # The split always sums to the aggregate.
    inv = xml_table_invocations(_role_project())
    for name, counts in roles.items():
        assert sum(counts.values()) == inv[name]


def test_xml_table_role_counts_empty_for_unreferenced_project():
    assert xml_table_role_counts(ProjectModel(pages=[])) == {}


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
    assert (a.page_count, a.detail_count, a.lookup_count) == (2, 0, 0)
    a_cols = {c.name: c for c in a.columns}
    assert a_cols["id"].ok is True  # id present in XML
    assert a_cols["id"].info is not None
    assert a_cols["db_only"].ok is False  # db column not in XML
    assert a_cols["db_only"].info is not None  # DB metadata attached
    assert a_cols["db_only"].info.is_fk is True

    v = by_name["pr.v"]
    assert v.ok is False  # view not referenced in XML at all
    assert v.kind == "view"
    assert v.invocations == 0
    assert (v.page_count, v.detail_count, v.lookup_count) == (0, 0, 0)


def test_check_db_against_xml_lookup_only_table_is_not_a_mismatch():
    # BUG-026 regression: pr.v is referenced ONLY as a column-lookup target.
    # `xml_table_columns` never records lookups, so the old
    # `ok = name in columns_by_table` rule painted it red while it still showed
    # a nonzero invocation count.
    project = ProjectModel(
        pages=[
            PageNode(
                identity="p",
                attrib={"tableName": "pr.a"},
                columns=[_col("id"), _lookup_col("v_ref", "pr.v")],
            )
        ]
    )
    checks = {c.name: c for c in check_db_against_xml(project, _make_schema())}

    v = checks["pr.v"]
    assert v.ok is True  # referenced via a lookup → not a mismatch
    assert v.lookup_count == 1
    assert v.page_count == 0 and v.detail_count == 0
    # Its columns are legitimately all absent on the XML side (informational).
    assert all(c.ok is False for c in v.columns)

    a = checks["pr.a"]
    assert a.ok is True
    assert (a.page_count, a.detail_count, a.lookup_count) == (1, 0, 0)


def test_check_db_against_xml_unreferenced_table_stays_a_mismatch():
    # The other half of the BUG-026 rule: red only when ALL roles are 0.
    project = ProjectModel(
        pages=[PageNode(identity="p", attrib={"tableName": "pr.a"}, columns=[_col("id")])]
    )
    checks = {c.name: c for c in check_db_against_xml(project, _make_schema())}
    v = checks["pr.v"]
    assert v.ok is False
    assert (v.page_count, v.detail_count, v.lookup_count) == (0, 0, 0)


def test_check_db_against_xml_detail_only_table_is_ok():
    schema = DatabaseSchema(
        tables={
            "pr.b": TableInfo(
                name="pr.b",
                kind="table",
                columns=[ColumnInfo("b_id", "integer", True, False, False, None)],
            )
        }
    )
    checks = {c.name: c for c in check_db_against_xml(_make_project(), schema)}
    b = checks["pr.b"]
    assert b.ok is True
    assert (b.page_count, b.detail_count, b.lookup_count) == (0, 1, 0)


def test_check_db_against_xml_table_in_all_three_roles():
    # BUG-026 completeness: the three counters are independent — a table bound
    # to a page, bound to a detail AND used as a lookup target reports all
    # three, and they still sum to the aggregate invocation count.
    project = ProjectModel(
        pages=[
            PageNode(
                identity="p1",
                attrib={"tableName": "pr.a"},
                columns=[_lookup_col("self_ref", "pr.a")],
                details=[
                    DetailNode(
                        identity="d1",
                        attrib={"tableName": "pr.a"},
                        columns=[_col("id")],
                    )
                ],
            )
        ]
    )
    schema = DatabaseSchema(
        tables={
            "pr.a": TableInfo(
                name="pr.a",
                kind="table",
                columns=[ColumnInfo("id", "integer", True, False, False, None)],
            )
        }
    )
    a = {c.name: c for c in check_db_against_xml(project, schema)}["pr.a"]
    assert a.ok is True
    assert (a.page_count, a.detail_count, a.lookup_count) == (1, 1, 1)
    assert a.page_count + a.detail_count + a.lookup_count == a.invocations


def test_check_xml_against_db_leaves_role_counts_at_zero():
    # The XML → Database direction keeps the aggregate `(×N)` rendering, so it
    # deliberately does not populate the role fields; DbCheckPanel keys the
    # `(P# D# L#)` form off the direction, not off these values (BUG-026).
    for check in check_xml_against_db(_make_project(), _make_schema()):
        assert (check.page_count, check.detail_count, check.lookup_count) == (0, 0, 0)


def test_table_check_role_counts_default_to_zero():
    # Back-compat: callers constructing a TableCheck without the new fields
    # (every pre-BUG-026 call site) still work.
    check = TableCheck(name="pr.x", ok=True, kind="table", invocations=1)
    assert (check.page_count, check.detail_count, check.lookup_count) == (0, 0, 0)
