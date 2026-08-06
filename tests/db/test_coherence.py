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
import pytest

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
    filter_nodes,
    row_count,
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


def test_reference_rows_carry_the_owning_nodes_properties_kind():
    """`TableReference.kind` IS the Properties-panel node kind, so a reference
    row must carry it — dropping it left the Properties panel empty for every
    row under a References group (BUG-032)."""
    tree = _tree()
    page_ref = _find(tree.tables_and_views, "pr.a").children[1].children[0]
    assert page_ref.kind == "reference"  # the row's own kind is unchanged
    assert page_ref.node_kind == "page"
    look_refs = _find(tree.tables_and_views, "pr.look").children[1]
    assert [ref.node_kind for ref in look_refs.children] == ["column", "column", "column"]


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


# --- role-count scoping (FQ-008) --------------------------------------------


def _role_project():
    """A project whose role counts differ per table, so P>1/D>1/L>1 can be told
    apart:

    * ``pr.hot``   — 2 pages, 2 details, 2 lookups  (P2 D2 L2)
    * ``pr.pages`` — 2 pages                        (P2 D0 L0)
    * ``pr.looks`` — 2 lookups                      (P0 D0 L2)
    * ``pr.one``   — 1 page                         (P1 D0 L0)
    """
    host = PageNode(
        identity="host",
        attrib={"tableName": "pr.one", "caption": "Host"},
        columns=[
            _lookup_col("l1", "pr.looks"),
            _lookup_col("l2", "pr.looks"),
            _lookup_col("h1", "pr.hot"),
            _lookup_col("h2", "pr.hot"),
        ],
        details=[
            DetailNode(identity="da", attrib={"tableName": "pr.hot", "caption": "Hot A"}),
            DetailNode(identity="db", attrib={"tableName": "pr.hot", "caption": "Hot B"}),
        ],
    )
    return ProjectModel(
        pages=[
            PageNode(identity="h1", attrib={"tableName": "pr.hot", "caption": "Hot one"}),
            PageNode(identity="h2", attrib={"tableName": "pr.hot", "caption": "Hot two"}),
            PageNode(identity="p1", attrib={"tableName": "pr.pages", "caption": "Pages one"}),
            PageNode(identity="p2", attrib={"tableName": "pr.pages", "caption": "Pages two"}),
            host,
        ]
    )


def _role_schema():
    return DatabaseSchema(
        tables={
            # `orphan` is a DB column nothing in the XML binds: the one flagged
            # row that sits *under* a P>1 relation.
            "pr.hot": TableInfo(name="pr.hot", kind="table", columns=[_info("orphan")]),
            "pr.pages": TableInfo(name="pr.pages", kind="table", columns=[]),
            "pr.looks": TableInfo(name="pr.looks", kind="table", columns=[]),
            "pr.one": TableInfo(
                name="pr.one",
                kind="table",
                columns=[_info("l1"), _info("l2"), _info("h1"), _info("h2")],
            ),
            # Referenced nowhere: flagged, and qualifying for no role.
            "pr.cold": TableInfo(name="pr.cold", kind="table", columns=[]),
        }
    )


def _role_tree():
    return build_coherence_tree(_role_project(), _role_schema())


def test_role_counts_in_the_fixture_are_what_the_badges_say():
    """Guard the fixture itself: the filters are only as trustworthy as the
    BUG-026 rollups they read."""
    tree = _role_tree()
    counts = {
        relation.label: (
            relation.payload.page_count,
            relation.payload.detail_count,
            relation.payload.lookup_count,
        )
        for relation in tree.tables_and_views.children
    }
    assert counts == {
        "pr.cold": (0, 0, 0),
        "pr.hot": (2, 2, 2),
        "pr.looks": (0, 0, 2),
        "pr.one": (1, 0, 0),
        "pr.pages": (2, 0, 0),
    }


@pytest.mark.parametrize(
    "roles, expected",
    [
        ((), {"pr.cold", "pr.hot", "pr.looks", "pr.one", "pr.pages"}),
        (("page",), {"pr.hot", "pr.pages"}),
        (("detail",), {"pr.hot"}),
        (("lookup",), {"pr.hot", "pr.looks"}),
        # ...and every combination narrows, never widens (AND, not OR).
        (("page", "detail"), {"pr.hot"}),
        (("page", "lookup"), {"pr.hot"}),
        (("detail", "lookup"), {"pr.hot"}),
        (("page", "detail", "lookup"), {"pr.hot"}),
    ],
)
def test_role_qualifying_tables_combine_with_and(roles, expected):
    assert _role_tree().role_qualifying_tables(roles) == expected


def test_role_qualifying_tables_is_empty_when_no_table_qualifies():
    tree = build_coherence_tree(_make_project(), _make_schema())
    # In the base fixture no table is used on more than one page.
    assert tree.role_qualifying_tables(("page",)) == set()


def test_scoping_keeps_a_relations_whole_subtree():
    tree = _role_tree()
    scoped = tree.scoped_to_tables(tree.role_qualifying_tables(("page",)))
    assert _labels(scoped.tables_and_views.children) == ["pr.hot", "pr.pages"]
    hot = _find(scoped.tables_and_views, "pr.hot")
    # Columns AND References survive verbatim — a scoped relation still answers
    # "where is it used", which is the whole point of narrowing to it.
    assert _labels(hot.children) == [COLUMNS_GROUP_LABEL, REFERENCES_GROUP_LABEL]
    assert _labels(hot.children[0].children) == ["orphan"]
    assert len(hot.children[1].children) == 6  # 2 pages + 2 details + 2 lookups


def test_scoping_prunes_the_pages_branch_to_the_matching_reference_points():
    tree = _role_tree()
    scoped = tree.scoped_to_tables(tree.role_qualifying_tables(("detail",)))
    # Only pr.hot qualifies: its two pages, plus the host page kept purely as
    # the ancestor of its lookups and details.
    assert _labels(scoped.pages.children) == ["Page 'Hot one'", "Page 'Hot two'", "Page 'Host'"]
    host = _find(scoped.pages, "Page 'Host'")
    assert _labels(host.children) == [
        "Column 'h1'",
        "Column 'h2'",
        "Detail 'Hot A'",
        "Detail 'Hot B'",
    ]
    # The pr.looks lookups pointed at a table out of scope: gone from BOTH
    # branches, so the two never disagree about what is in scope.
    assert _find(scoped.pages, "Column 'l1'") is None
    assert _find(scoped.tables_and_views, "pr.looks") is None


def test_scoping_then_mismatch_filtering_keeps_flagged_rows_under_a_scoped_table():
    """The composition the panel uses: scope by role, then select mismatches
    within that scope. `orphan` has no role counts of its own, so a per-row AND
    would have silently dropped it."""
    tree = _role_tree()
    combined = tree.scoped_to_tables(tree.role_qualifying_tables(("page",))).filtered()
    assert _labels(combined.tables_and_views.children) == ["pr.hot"]
    hot = combined.tables_and_views.children[0]
    assert _labels(hot.children) == [COLUMNS_GROUP_LABEL]
    assert _labels(hot.children[0].children) == ["orphan"]
    # pr.cold is flagged but out of scope; nothing in the Pages branch is flagged.
    assert _find(combined.tables_and_views, "pr.cold") is None
    assert combined.pages.children == ()


def test_scoping_to_nothing_keeps_both_branch_roots():
    tree = _role_tree()
    scoped = tree.scoped_to_tables(set())
    assert scoped.tables_and_views.label == TABLES_BRANCH_LABEL
    assert scoped.pages.label == PAGES_BRANCH_LABEL
    assert scoped.tables_and_views.children == ()
    assert scoped.pages.children == ()


def test_filter_nodes_keep_subtree_stops_pruning_at_a_match():
    tree = _role_tree()
    hot = _find(tree.tables_and_views, "pr.hot")

    def is_hot(node):
        return node.table_name == "pr.hot"

    pruned = filter_nodes(tree.tables_and_views, is_hot, keep_subtree=True)
    assert pruned.children == (hot,)  # the very same node object, untouched
    # Without keep_subtree the match's children are pruned too, and nothing
    # below pr.hot matches.
    shallow = filter_nodes(tree.tables_and_views, is_hot)
    assert _labels(shallow.children) == ["pr.hot"]
    assert shallow.children[0].children == ()


def test_row_count_counts_every_row_but_the_branch_roots():
    tree = _role_tree()
    expected = sum(row_count(branch) for branch in tree.branches) - 2
    assert tree.row_count == expected
    # A filter can only ever shrink it.
    assert tree.filtered().row_count < tree.row_count
