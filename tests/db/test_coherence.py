# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# tests/db/test_coherence.py
"""Pure tests for the Database/XML Coherence model (no Qt, no live DB)."""
from pgtp_editor.db.coherence import (
    BADGE_CALCULATED,
    BADGE_MISSING_IN_DB,
    BADGE_NOT_IN_XML,
    BADGE_UNREFERENCED,
    COLUMNS_GROUP_LABEL,
    PAGES_BRANCH_LABEL,
    REFERENCES_GROUP_LABEL,
    TABLES_BRANCH_LABEL,
    build_coherence_tree,
    filter_flagged,
)
from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.model.nodes import (
    ChildElement,
    ColumnNode,
    DetailNode,
    PageNode,
    ProjectModel,
)


# --- canned data ------------------------------------------------------------


def _col(field_name):
    return ColumnNode(identity=field_name, attrib={"fieldName": field_name})


def _calc_col(field_name):
    return ColumnNode(
        identity=field_name,
        attrib={"fieldName": field_name, "isCalculated": "true"},
    )


def _lookup_col(field_name, lookup_table, *, with_insert=False):
    class _FakeElement:
        """Stands in for the retained lxml <Lookup>; only `find` is consulted
        by `reused_tables._lookup_ref_type`."""

        def find(self, tag):
            return object() if (with_insert and tag == "OnTheFlyInsertPage") else None

    return ColumnNode(
        identity=field_name,
        attrib={"fieldName": field_name},
        lookup=ChildElement(attrib={"tableName": lookup_table}, element=_FakeElement()),
    )


def _info(name, data_type="text", *, pk=False, fk=False, nullable=True):
    return ColumnInfo(name, data_type, pk, fk, nullable, None)


def _find(node, label):
    """First descendant (inclusive) with this label."""
    if node.label == label:
        return node
    for child in node.children:
        found = _find(child, label)
        if found is not None:
            return found
    return None


def _labels(nodes):
    return [node.label for node in nodes]


def _make_project():
    """One page bound to pr.a, holding:

    * a plain column, a calculated column and two lookups (one with insert),
    * a Detail chain nested three levels deep, the deepest carrying its own
      lookup — the anti-flattening fixture.
    """
    deepest = DetailNode(
        identity="d3",
        attrib={"tableName": "pr.d3", "caption": "Level three"},
        columns=[_lookup_col("deep_fk", "pr.look")],
    )
    middle = DetailNode(
        identity="d2",
        attrib={"tableName": "pr.d2", "caption": "Level two"},
        details=[deepest],
    )
    top = DetailNode(
        identity="d1",
        attrib={"tableName": "pr.d1", "caption": "Level one"},
        details=[middle],
    )
    page = PageNode(
        identity="p1",
        attrib={"tableName": "pr.a", "caption": "Main"},
        columns=[
            _col("id"),
            _calc_col("computed"),
            _lookup_col("look_fk", "pr.look"),
            _lookup_col("insert_fk", "pr.look", with_insert=True),
        ],
        details=[top],
    )
    return ProjectModel(pages=[page])


def _make_schema():
    return DatabaseSchema(
        tables={
            "pr.a": TableInfo(
                name="pr.a",
                kind="table",
                columns=[_info("id", "integer", pk=True, nullable=False), _info("db_only")],
            ),
            "pr.look": TableInfo(name="pr.look", kind="table", columns=[_info("id")]),
            "pr.d1": TableInfo(name="pr.d1", kind="table", columns=[]),
            "pr.d2": TableInfo(name="pr.d2", kind="table", columns=[]),
            "pr.d3": TableInfo(name="pr.d3", kind="table", columns=[]),
            # A view, referenced nowhere in the XML.
            "pr.v": TableInfo(name="pr.v", kind="view", columns=[_info("vc")]),
        }
    )


def _tree():
    return build_coherence_tree(_make_project(), _make_schema())


# --- both branches build ----------------------------------------------------


def test_both_branches_build():
    tree = _tree()
    assert tree.tables_and_views.label == TABLES_BRANCH_LABEL
    assert tree.pages.label == PAGES_BRANCH_LABEL
    assert _labels(tree.tables_and_views.children) == [
        "pr.a",
        "pr.d1",
        "pr.d2",
        "pr.d3",
        "pr.look",
        "pr.v",
    ]
    assert _labels(tree.pages.children) == ["Page 'Main'"]
    relation = tree.tables_and_views.children[0]
    assert _labels(relation.children) == [COLUMNS_GROUP_LABEL, REFERENCES_GROUP_LABEL]


def test_views_are_treated_like_tables():
    tree = _tree()
    view = _find(tree.tables_and_views, "pr.v")
    table = _find(tree.tables_and_views, "pr.a")
    assert view.kind == table.kind == "relation"
    assert view.badges == ("view",)
    assert table.badges == ("table",)
    # Same two sub-sections, no kind-based special-casing.
    assert _labels(view.children) == _labels(table.children)


def test_reference_badges_come_from_role_rollups():
    tree = _tree()
    references = _find(tree.tables_and_views, "pr.a").children[1]
    assert references.badges == ("1 page",)
    look_refs = _find(tree.tables_and_views, "pr.look").children[1]
    assert look_refs.badges == ("3 lookups",)
    # ...expandable to the full breadcrumb detail.
    assert len(look_refs.children) == 3
    assert look_refs.children[0].label.startswith("Page 'Main' ▸ Column 'look_fk'")


# --- Pages branch: recursion depth (the anti-flattening guard) --------------


def test_deeply_nested_detail_keeps_its_depth_and_lookups():
    tree = _tree()
    page = tree.pages.children[0]
    # Page > Detail(1) > Detail(2) > Detail(3) > Lookup — not flattened.
    level1 = page.children[-1]
    assert level1.label == "Detail 'Level one'"
    level2 = level1.children[0]
    assert level2.label == "Detail 'Level two'"
    level3 = level2.children[0]
    assert level3.label == "Detail 'Level three'"
    assert level3.badges[0] == "pr.d3"
    assert _labels(level3.children) == ["Column 'deep_fk'"]
    assert level3.children[0].kind == "lookup"


def test_page_carries_its_own_lookups_and_bound_table():
    page = _tree().pages.children[0]
    assert page.table_name == "pr.a"
    assert page.badges == ("pr.a",)
    # Only lookup columns become rows; plain/calculated columns are not refs.
    assert _labels(page.children[:2]) == ["Column 'look_fk'", "Column 'insert_fk'"]


def test_lookup_with_insert_keeps_its_own_badge():
    page = _tree().pages.children[0]
    plain, with_insert = page.children[0], page.children[1]
    assert plain.badges[0] == "lookup"
    assert with_insert.badges[0] == "lookup with insert"


# --- the mismatch predicate -------------------------------------------------


def test_dangling_reference_flags_at_the_reference_point_only():
    # pr.look is renamed away in the DB: the three lookups pointing at it must
    # each flag, and NO phantom row may appear under "Tables and Views".
    schema = _make_schema()
    del schema.tables["pr.look"]
    tree = build_coherence_tree(_make_project(), schema)

    assert "pr.look" not in _labels(tree.tables_and_views.children)
    assert _find(tree.tables_and_views, "pr.look") is None

    page = tree.pages.children[0]
    for lookup in page.children[:2]:
        assert lookup.flagged
        assert BADGE_MISSING_IN_DB in lookup.badges
    deep_lookup = page.children[-1].children[0].children[0].children[0]
    assert deep_lookup.label == "Column 'deep_fk'"
    assert deep_lookup.flagged


def test_dangling_page_binding_flags_the_page():
    schema = _make_schema()
    del schema.tables["pr.a"]
    tree = build_coherence_tree(_make_project(), schema)
    page = tree.pages.children[0]
    assert page.flagged
    assert page.badges == ("pr.a", BADGE_MISSING_IN_DB)
    assert _find(tree.tables_and_views, "pr.a") is None


def test_unreferenced_relation_flags():
    tree = _tree()
    view = _find(tree.tables_and_views, "pr.v")
    assert view.flagged
    assert view.children[1].badges == (BADGE_UNREFERENCED,)
    # A referenced relation does not.
    assert not _find(tree.tables_and_views, "pr.a").flagged


def test_calculated_columns_are_shown_but_never_flagged():
    columns = _find(_tree().tables_and_views, "pr.a").children[0]
    computed = _find(columns, "computed")
    assert computed is not None
    assert BADGE_CALCULATED in computed.badges
    assert not computed.flagged
    assert BADGE_MISSING_IN_DB not in computed.badges


def test_failing_column_check_flags():
    columns = _find(_tree().tables_and_views, "pr.a").children[0]
    # A DB column no page/detail binds.
    db_only = _find(columns, "db_only")
    assert db_only.flagged
    assert BADGE_NOT_IN_XML in db_only.badges
    # A bound DB column does not, and carries its DB facts as badges.
    bound = _find(columns, "id")
    assert not bound.flagged
    assert bound.badges == ("integer", "pk", "not null")


def test_xml_column_missing_from_db_flags():
    project = ProjectModel(
        pages=[PageNode(identity="p", attrib={"tableName": "pr.a"}, columns=[_col("ghost")])]
    )
    tree = build_coherence_tree(project, _make_schema())
    ghost = _find(_find(tree.tables_and_views, "pr.a").children[0], "ghost")
    assert ghost.flagged
    assert BADGE_MISSING_IN_DB in ghost.badges


# --- filtering --------------------------------------------------------------


def test_filter_preserves_ancestors_of_flagged_leaves():
    schema = _make_schema()
    del schema.tables["pr.look"]
    filtered = build_coherence_tree(_make_project(), schema).filtered()

    page = filtered.pages.children[0]
    assert not page.flagged  # kept only as an ancestor
    # The deep lookup is still reachable at its original depth...
    level3 = page.children[-1].children[0].children[0]
    assert level3.label == "Detail 'Level three'"
    assert _labels(level3.children) == ["Column 'deep_fk'"]
    # ...while unflagged siblings along the way are gone.
    assert level3.children[0].flagged


def test_filter_drops_unflagged_subtrees_but_keeps_branch_roots():
    filtered = _tree().filtered()
    assert filtered.pages.label == PAGES_BRANCH_LABEL
    assert filtered.pages.children == ()  # nothing dangling in the XML
    # Tables-and-Views keeps only what needs attention.
    assert "pr.v" in _labels(filtered.tables_and_views.children)
    view = _find(filtered.tables_and_views, "pr.v")
    # Its unflagged "References" group is dropped; the columns group survives
    # only because `vc` is itself flagged (a DB column no page binds).
    assert _labels(view.children) == [COLUMNS_GROUP_LABEL]
    assert _labels(view.children[0].children) == ["vc"]
    # A relation with nothing flagged anywhere below it disappears entirely.
    assert _find(filtered.tables_and_views, "pr.d1") is None


def test_filter_flagged_returns_none_when_nothing_flagged():
    clean = build_coherence_tree(ProjectModel(pages=[]), DatabaseSchema(tables={}))
    assert filter_flagged(clean.pages) is None
    assert clean.flagged_count == 0
    assert _tree().flagged_count > 0
