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

# tests/ui/test_coherence_panel.py
"""Rendering tests for the Database/XML Coherence panel.

Canned project + schema (the same fixture shape as ``tests/db/test_coherence.py``)
built into a real ``CoherenceTree``; the panel is then asserted purely through
its widgets. No live DB, no modal, no MainWindow.
"""
import pytest
from PySide6.QtCore import Qt

from pgtp_editor.db.coherence import (
    BADGE_MISSING_IN_DB,
    COLUMNS_GROUP_LABEL,
    PAGES_BRANCH_LABEL,
    REFERENCES_GROUP_LABEL,
    TABLES_BRANCH_LABEL,
    build_coherence_tree,
)
from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.model.nodes import ChildElement, ColumnNode, DetailNode, PageNode, ProjectModel
from pgtp_editor.ui.coherence_panel import (
    COHERENT_TEXT,
    NO_MATCHES_TEXT,
    NOT_COMPARED_TEXT,
    _HOST_KIND,
    _IDENTITY_HOST_KINDS,
    CoherencePanel,
)

SUMMARY = "app@db.example:5432/prod"


# --- canned data (mirrors tests/db/test_coherence.py) ------------------------


def _col(field_name):
    return ColumnNode(identity=field_name, attrib={"fieldName": field_name})


def _calc_col(field_name):
    return ColumnNode(
        identity=field_name,
        attrib={"fieldName": field_name, "isCalculated": "true"},
    )


def _lookup_col(field_name, lookup_table, *, with_insert=False, sourceline=None):
    class _FakeElement:
        def find(self, tag):
            return object() if (with_insert and tag == "OnTheFlyInsertPage") else None

    return ColumnNode(
        identity=field_name,
        attrib={"fieldName": field_name},
        sourceline=sourceline,
        lookup=ChildElement(attrib={"tableName": lookup_table}, element=_FakeElement()),
    )


def _info(name, data_type="text", *, pk=False, fk=False, nullable=True):
    return ColumnInfo(name, data_type, pk, fk, nullable, None)


def _make_project():
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
            _lookup_col("look_fk", "pr.look", sourceline=42),
            _lookup_col("insert_fk", "pr.look", with_insert=True, sourceline=43),
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
            "pr.v": TableInfo(name="pr.v", kind="view", columns=[_info("vc")]),
        }
    )


def _coherent_project():
    """A project/schema pair with nothing at all to flag."""
    project = ProjectModel(
        pages=[PageNode(identity="p", attrib={"tableName": "pr.a"}, columns=[_col("id")])]
    )
    schema = DatabaseSchema(
        tables={"pr.a": TableInfo(name="pr.a", kind="table", columns=[_info("id")])}
    )
    return project, schema


# --- helpers -----------------------------------------------------------------


@pytest.fixture
def panel(qtbot):
    widget = CoherencePanel()
    qtbot.addWidget(widget)
    return widget


def _populate(panel, project=None, schema=None):
    tree = build_coherence_tree(project or _make_project(), schema or _make_schema())
    panel.set_result(tree, SUMMARY)
    return tree


def _top_items(panel):
    return [panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())]


def _children(item):
    return [item.child(i) for i in range(item.childCount())]


def _find_item(item, needle):
    """First descendant (inclusive) whose column-0 text contains `needle`."""
    if needle in item.text(0):
        return item
    for child in _children(item):
        found = _find_item(child, needle)
        if found is not None:
            return found
    return None


def _find_in_panel(panel, needle):
    for top in _top_items(panel):
        found = _find_item(top, needle)
        if found is not None:
            return found
    return None


# --- both branches render ----------------------------------------------------


def test_both_branches_render_as_top_level_roots(panel):
    _populate(panel)
    tops = _top_items(panel)
    assert [item.text(0) for item in tops] == [TABLES_BRANCH_LABEL, PAGES_BRANCH_LABEL]
    assert panel.tree.isVisible() or not panel.empty_label.isVisible()
    assert not panel.empty_label.isVisible()

    tables, pages = tops
    assert [item.text(0) for item in _children(tables)] == [
        "✓ (T) pr.a",
        "✓ (T) pr.d1",
        "✓ (T) pr.d2",
        "✓ (T) pr.d3",
        "✓ (T) pr.look",
        "✗ (V) pr.v",  # a view nobody references
    ]
    relation = _children(tables)[0]
    assert [item.text(0) for item in _children(relation)] == [
        COLUMNS_GROUP_LABEL,
        REFERENCES_GROUP_LABEL,
    ]
    assert [item.text(0) for item in _children(pages)] == ["✓ Page 'Main'"]


def test_header_states_what_was_compared_and_the_flagged_count(panel):
    tree = _populate(panel)
    text = panel.header_label.text()
    assert SUMMARY in text
    assert f"{tree.flagged_count} mismatches" in text
    # No direction wording anywhere: the toggle is gone, not merged.
    assert "→" not in text


# --- badges ------------------------------------------------------------------


def test_role_count_badge_appears_on_a_relation(panel):
    _populate(panel)
    relation = _find_in_panel(panel, "pr.look")
    assert relation.text(1).startswith("(P0 D0 L3)")
    page_bound = _find_in_panel(panel, "pr.a")
    assert page_bound.text(1).startswith("(P1 D0 L0)")


def test_lookup_with_insert_badge_is_visible_and_distinct(panel):
    _populate(panel)
    pages = _top_items(panel)[1]
    page = _children(pages)[0]
    plain, with_insert = _children(page)[0], _children(page)[1]
    assert plain.text(0) == "✓ Column 'look_fk'"
    assert with_insert.text(0) == "✓ Column 'insert_fk'"
    assert plain.text(1).startswith("lookup ·")
    assert with_insert.text(1).startswith("lookup with insert ·")


def test_column_glyphs_keep_the_three_way_convention(panel):
    _populate(panel)
    columns = _children(_find_in_panel(panel, "pr.a"))[0]
    texts = [item.text(0) for item in _children(columns)]
    assert "✓ id" in texts  # bound
    assert "✗ db_only" in texts  # DB column no page binds
    assert "~ computed" in texts  # calculated: never a mismatch


# --- depth -------------------------------------------------------------------


def test_deeply_nested_detail_renders_at_its_real_depth(panel):
    _populate(panel)
    pages = _top_items(panel)[1]
    page = _children(pages)[0]
    level1 = _children(page)[-1]
    assert level1.text(0) == "✓ Detail 'Level one'"
    level2 = _children(level1)[0]
    assert level2.text(0) == "✓ Detail 'Level two'"
    level3 = _children(level2)[0]
    assert level3.text(0) == "✓ Detail 'Level three'"
    lookup = _children(level3)[0]
    assert lookup.text(0) == "✓ Column 'deep_fk'"
    # Five levels below the branch root — not flattened to a fixed shape.
    depth = 0
    walker = lookup
    while walker.parent() is not None:
        depth += 1
        walker = walker.parent()
    assert depth == 5


# --- the mismatch toggle -----------------------------------------------------


def test_mismatch_toggle_prunes_and_restores(panel):
    schema = _make_schema()
    del schema.tables["pr.look"]  # renamed away: three dangling lookups
    _populate(panel, schema=schema)
    full_pages = _children(_top_items(panel)[1])
    assert len(full_pages) == 1

    panel.filter_checkbox.setChecked(True)
    tables, pages = _top_items(panel)
    # Nothing coherent survives in Tables and Views except what needs attention.
    assert "pr.a" not in [item.text(0) for item in _children(tables)]
    # ...and the deep flagged lookup is still reachable through its ancestors.
    page = _children(pages)[0]
    assert page.text(0) == "✓ Page 'Main'"  # kept as ancestor, not flagged
    level3 = _children(_children(_children(page)[-1])[0])[0]
    assert level3.text(0) == "✓ Detail 'Level three'"
    assert _children(level3)[0].text(0) == "✗ Column 'deep_fk'"
    assert BADGE_MISSING_IN_DB in _children(level3)[0].text(1)

    panel.filter_checkbox.setChecked(False)
    assert "✓ (T) pr.a" in [item.text(0) for item in _children(_top_items(panel)[0])]


def test_header_count_is_independent_of_the_filter(panel):
    _populate(panel)
    before = panel.header_label.text()
    panel.filter_checkbox.setChecked(True)
    assert panel.header_label.text() == before


# --- navigation --------------------------------------------------------------


def test_double_click_emits_the_xml_line(panel, qtbot):
    _populate(panel)
    pages = _top_items(panel)[1]
    lookup = _children(_children(pages)[0])[0]
    assert panel.node_for(lookup).line == 42

    with qtbot.waitSignal(panel.jump_requested, timeout=1000) as blocker:
        panel.tree.itemDoubleClicked.emit(lookup, 0)
    assert blocker.args == [42]


def test_double_click_on_a_relation_emits_the_name_signal(panel, qtbot):
    """The emitted kind is the HOST vocabulary ("table"), not the internal node
    kind ("relation") — MainWindow._on_db_jump_requested tests `kind == "table"`
    to pick the tableName= search token, so emitting "relation" made every
    relation double-click search for fieldName="<table>" and always miss
    (BUG-032 facet A). Same normalization `contextual_rename` already does."""
    _populate(panel)
    relation = _find_in_panel(panel, "pr.v")
    with qtbot.waitSignal(panel.name_jump_requested, timeout=1000) as blocker:
        panel.tree.itemDoubleClicked.emit(relation, 0)
    assert blocker.args == ["table", "pr.v"]


def test_a_relation_rows_row_role_uses_the_host_kind(panel):
    """§17 binds the carried-over 4-tuple `(kind, name, ok, is_calculated)` to
    DbCheckPanel's shape, where a relation was "table". Keeping "relation" in it
    is the same latent mismatch that produced BUG-032 facet A."""
    _populate(panel)
    relation = _find_in_panel(panel, "pr.v")
    kind, name, ok, is_calculated = relation.data(0, Qt.ItemDataRole.UserRole)
    assert (kind, name) == ("table", "pr.v")
    # Column rows keep their kind unchanged.
    column = _children(_children(relation)[0])[0]
    assert column.data(0, Qt.ItemDataRole.UserRole)[0] == "column"


def test_selection_emits_the_owning_model_node(panel, qtbot):
    _populate(panel)
    pages = _top_items(panel)[1]
    lookup = _children(_children(pages)[0])[0]
    with qtbot.waitSignal(panel.selection_changed, timeout=1000) as blocker:
        panel.tree.setCurrentItem(lookup)
    node, kind = blocker.args
    assert kind == "lookup"
    # A lookup row's model node is its owning ColumnNode (Properties semantic).
    assert isinstance(node, ColumnNode)
    assert node.field_name == "look_fk"


def test_selecting_a_reference_row_emits_the_owning_nodes_properties_kind(panel, qtbot):
    """A "References" row's model node is the Page/Detail/Column doing the
    referencing, so Properties must be told THAT kind — `TableReference.kind`.
    Emitting the row's own "reference" kind left the panel empty (BUG-032)."""
    _populate(panel)
    relation = _find_in_panel(panel, "pr.look")
    references = _children(
        next(child for child in _children(relation) if REFERENCES_GROUP_LABEL in child.text(0))
    )
    assert references
    kinds = []
    for item in references:
        with qtbot.waitSignal(panel.selection_changed, timeout=1000) as blocker:
            panel.tree.setCurrentItem(item)
        node, kind = blocker.args
        assert node is not None
        kinds.append(kind)
    # The lookups on pr.a's columns and the deep detail's column: all column
    # references here, and never the internal "reference" kind.
    assert "reference" not in kinds
    assert set(kinds) <= {"page", "detail", "column"}
    assert "column" in kinds


# --- empty states ------------------------------------------------------------


def test_the_two_empty_states_differ(panel):
    # 1. Nothing compared yet.
    assert panel.empty_label.isVisible() or not panel.tree.isVisible()
    assert panel.empty_label.text() == NOT_COMPARED_TEXT
    assert not panel.tree.isVisible()

    # 2. Compared, and fully coherent.
    project, schema = _coherent_project()
    _populate(panel, project=project, schema=schema)
    panel.filter_checkbox.setChecked(True)
    assert not panel.tree.isVisible()
    assert panel.empty_label.text() == COHERENT_TEXT
    assert COHERENT_TEXT != NOT_COMPARED_TEXT
    assert SUMMARY in panel.header_label.text()  # ...and it says what it compared

    # 3. Clearing returns to the first state, not the second.
    panel.clear()
    assert panel.empty_label.text() == NOT_COMPARED_TEXT
    assert panel.result is None


# --- context-menu contents (pure, no popup) ----------------------------------


def test_create_actions_offered_on_relations_only(panel):
    _populate(panel)
    relation = _find_in_panel(panel, "pr.a")
    assert [what for what, _label in panel.create_menu_items(relation)] == [
        "page",
        "detail",
        "lookup",
    ]
    assert panel.create_menu_items(_children(relation)[0]) == []  # a group row
    assert panel.create_menu_items(None) == []


def test_rename_is_offered_for_a_dangling_reference_but_not_a_calculated_column(panel, qtbot):
    schema = _make_schema()
    del schema.tables["pr.look"]
    _populate(panel, schema=schema)
    lookup = _children(_children(_top_items(panel)[1])[0])[0]
    assert panel.rename_menu_label(lookup) == "Rename table in XML…"
    with qtbot.waitSignal(panel.rename_requested, timeout=1000) as blocker:
        panel.contextual_rename(lookup)
    assert blocker.args == ["table", "pr.look"]

    calculated = _find_in_panel(panel, "~ computed")
    assert panel.rename_menu_label(calculated) is None


# --- the P>1/D>1/L>1 role filters (FQ-008) -----------------------------------


def _role_project():
    """Role counts that differ per table, so the three filters can be told
    apart: ``pr.hot`` P2 D2 L2, ``pr.pages`` P2, ``pr.looks`` L2, ``pr.one``
    P1, and ``pr.cold`` referenced nowhere at all."""
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
            # `orphan` is a DB column no page binds: a flagged row sitting UNDER
            # a P>1 relation, which is what makes the composition testable.
            "pr.hot": TableInfo(name="pr.hot", kind="table", columns=[_info("orphan")]),
            "pr.pages": TableInfo(name="pr.pages", kind="table", columns=[]),
            "pr.looks": TableInfo(name="pr.looks", kind="table", columns=[]),
            "pr.one": TableInfo(
                name="pr.one",
                kind="table",
                columns=[_info("l1"), _info("l2"), _info("h1"), _info("h2")],
            ),
            "pr.cold": TableInfo(name="pr.cold", kind="table", columns=[]),
        }
    )


def _populate_roles(panel):
    return _populate(panel, project=_role_project(), schema=_role_schema())


def _relation_labels(panel):
    """Relation labels currently shown in the Tables and Views branch, with the
    glyph/prefix decoration stripped."""
    return [item.text(0).split()[-1] for item in _children(_top_items(panel)[0])]


def _check(panel, *roles, mismatches=False):
    panel.filter_checkbox.setChecked(mismatches)
    for role, box in panel.role_checkboxes.items():
        box.setChecked(role in roles)


def test_the_three_role_checkboxes_exist_with_the_badge_wording(panel):
    assert list(panel.role_checkboxes) == ["page", "detail", "lookup"]
    assert [box.text() for box in panel.role_checkboxes.values()] == ["P>1", "D>1", "L>1"]
    # The tooltip spells out what the abbreviation means and how it composes.
    tip = panel.role_checkboxes["page"].toolTip()
    assert "more than one Page" in tip
    assert "must hold" in tip


@pytest.mark.parametrize(
    "roles, expected",
    [
        (("page",), ["pr.hot", "pr.pages"]),
        (("detail",), ["pr.hot"]),
        (("lookup",), ["pr.hot", "pr.looks"]),
        # Every combination narrows (AND), never widens (OR would have kept
        # pr.pages and pr.looks here).
        (("page", "detail"), ["pr.hot"]),
        (("page", "lookup"), ["pr.hot"]),
        (("detail", "lookup"), ["pr.hot"]),
        (("page", "detail", "lookup"), ["pr.hot"]),
    ],
)
def test_role_checkboxes_filter_and_compose_with_and(panel, roles, expected):
    _populate_roles(panel)
    _check(panel, *roles)
    assert _relation_labels(panel) == expected


def test_a_role_filter_keeps_the_relations_columns_and_references(panel):
    _populate_roles(panel)
    _check(panel, "detail")
    relation = _children(_top_items(panel)[0])[0]
    assert [item.text(0) for item in _children(relation)] == [
        COLUMNS_GROUP_LABEL,
        REFERENCES_GROUP_LABEL,
    ]
    assert _find_item(relation, "orphan") is not None


def test_a_role_filter_prunes_the_pages_branch_too(panel):
    _populate_roles(panel)
    _check(panel, "detail")  # only pr.hot qualifies
    pages = _top_items(panel)[1]
    labels = [item.text(0) for item in _children(pages)]
    assert labels == ["✓ Page 'Hot one'", "✓ Page 'Hot two'", "✓ Page 'Host'"]
    host = _children(pages)[-1]
    # Only the reference points that target an in-scope table survive: the
    # pr.hot lookups and details, not the pr.looks ones.
    assert [item.text(0) for item in _children(host)] == [
        "✓ Column 'h1'",
        "✓ Column 'h2'",
        "✓ Detail 'Hot A'",
        "✓ Detail 'Hot B'",
    ]


def test_role_filter_composes_with_the_mismatch_toggle(panel):
    """Roles scope, the mismatch toggle then selects within that scope. The
    flagged row here is a column, which has no role counts of its own — a naive
    per-row AND would have silently hidden it."""
    _populate_roles(panel)
    _check(panel, "page", mismatches=True)
    assert _relation_labels(panel) == ["pr.hot"]
    relation = _children(_top_items(panel)[0])[0]
    assert [item.text(0) for item in _children(relation)] == [COLUMNS_GROUP_LABEL]
    assert [item.text(0) for item in _children(_children(relation)[0])] == ["✗ orphan"]
    # pr.cold is flagged (unreferenced) but out of the P>1 scope.
    assert _find_in_panel(panel, "pr.cold") is None

    # The mismatch toggle alone would have shown pr.cold as well.
    _check(panel, mismatches=True)
    assert "pr.cold" in _relation_labels(panel)


def test_role_filter_that_matches_nothing_says_so_without_blaming_the_toggle(panel):
    _populate(panel)  # base fixture: no table is used on more than one page
    _check(panel, "page")
    assert not panel.tree.isVisible()
    assert panel.empty_label.text() == NO_MATCHES_TEXT
    assert "Show only mismatches" not in NO_MATCHES_TEXT
    # ...and the banner still says what is filtering, next to that message.
    assert panel.filter_banner.isVisibleTo(panel)


# --- the active-filter banner ------------------------------------------------


def test_banner_is_hidden_until_a_filter_is_active(panel):
    _populate_roles(panel)
    assert not panel.filter_banner.isVisibleTo(panel)
    panel.role_checkboxes["page"].setChecked(True)
    assert panel.filter_banner.isVisibleTo(panel)
    panel.role_checkboxes["page"].setChecked(False)
    assert not panel.filter_banner.isVisibleTo(panel)


@pytest.mark.parametrize(
    "roles, mismatches, expected",
    [
        ((), True, "mismatches only"),
        (("page",), False, "more than one Page (P>1)"),
        (("detail",), False, "more than one Detail (D>1)"),
        (("lookup",), False, "more than one Lookup (L>1)"),
        (
            ("page", "lookup"),
            False,
            "more than one Page (P>1) AND more than one Lookup (L>1)",
        ),
        (
            ("page", "detail", "lookup"),
            False,
            "more than one Page (P>1) AND more than one Detail (D>1) "
            "AND more than one Lookup (L>1)",
        ),
        (
            ("page",),
            True,
            "mismatches only AND more than one Page (P>1)",
        ),
        (
            ("page", "detail", "lookup"),
            True,
            "mismatches only AND more than one Page (P>1) AND more than one Detail (D>1) "
            "AND more than one Lookup (L>1)",
        ),
    ],
)
def test_banner_names_every_active_filter_and_the_combination(
    panel, roles, mismatches, expected
):
    tree = _populate_roles(panel)
    _check(panel, *roles, mismatches=mismatches)
    assert panel.filter_description() == expected
    text = panel.filter_banner_label.text()
    assert text.startswith(f"Filtered: {expected} — showing ")
    assert text.endswith(f" of {tree.row_count} rows")


def test_banner_row_count_reflects_what_survived_the_filter(panel):
    tree = _populate_roles(panel)
    _check(panel, "detail")
    shown = tree.scoped_to_tables(tree.role_qualifying_tables(("detail",))).row_count
    assert f"showing {shown} of {tree.row_count} rows" in panel.filter_banner_label.text()
    assert 0 < shown < tree.row_count


def test_clear_filters_unticks_everything_and_restores_the_full_tree(panel):
    _populate_roles(panel)
    _check(panel, "page", "detail", "lookup", mismatches=True)
    assert panel.filter_banner.isVisibleTo(panel)
    full = ["pr.cold", "pr.hot", "pr.looks", "pr.one", "pr.pages"]
    assert _relation_labels(panel) != full

    panel.clear_filters()
    assert not panel.filter_checkbox.isChecked()
    assert not any(box.isChecked() for box in panel.role_checkboxes.values())
    assert not panel.filter_banner.isVisibleTo(panel)
    assert panel.filter_description() == ""
    assert _relation_labels(panel) == full
    assert [item.text(0) for item in _children(_top_items(panel)[1])] == [
        "✓ Page 'Hot one'",
        "✓ Page 'Hot two'",
        "✓ Page 'Pages one'",
        "✓ Page 'Pages two'",
        "✓ Page 'Host'",
    ]


def test_clear_filters_rebuilds_once(panel, monkeypatch):
    """Unticking four boxes must not rebuild the tree four times — the boxes'
    signals are blocked and one rebuild follows."""
    _populate_roles(panel)
    _check(panel, "page", "detail", "lookup", mismatches=True)
    calls = []
    original = panel._rebuild
    monkeypatch.setattr(panel, "_rebuild", lambda: (calls.append(1), original())[1])
    panel.clear_filters()
    assert len(calls) == 1


def test_the_header_count_ignores_the_role_filters_too(panel):
    _populate_roles(panel)
    before = panel.header_label.text()
    _check(panel, "page", "detail", "lookup", mismatches=True)
    assert panel.header_label.text() == before


# --- host-kind mapping totality (BUG-032's bug class) ------------------------

#: Every `CoherenceNode.kind` the model documents (see `CoherenceNode`'s
#: docstring in `db/coherence.py`). Kept here as the explicit contract the host
#: mapping must be total over.
DOCUMENTED_KINDS = frozenset(
    {"branch", "relation", "group", "column", "reference", "page", "detail", "lookup"}
)


def _emitted_kinds():
    """Kinds a real tree actually contains, across both fixtures."""
    kinds = set()

    def walk(node):
        kinds.add(node.kind)
        for child in node.children:
            walk(child)

    for project, schema in (
        (_make_project(), _make_schema()),
        (_role_project(), _role_schema()),
    ):
        for branch in build_coherence_tree(project, schema).branches:
            walk(branch)
    return kinds


@pytest.mark.parametrize("kind", sorted(DOCUMENTED_KINDS))
def test_host_kind_mapping_is_total_over_every_emitted_kind(kind):
    """BUG-032 facet A was an internal kind reaching MainWindow untranslated.
    `_HOST_KIND` is now the one translation — so every kind the panel can emit
    must be either mapped by it or *deliberately* identity-passed, and never
    silently neither."""
    assert (kind in _HOST_KIND) ^ (kind in _IDENTITY_HOST_KINDS), kind


def test_the_two_host_kind_sets_cover_exactly_the_documented_vocabulary():
    assert set(_HOST_KIND) | set(_IDENTITY_HOST_KINDS) == DOCUMENTED_KINDS
    assert _HOST_KIND == {"relation": "table"}


def test_the_fixtures_exercise_the_documented_kind_vocabulary():
    """Keeps the totality test honest: if the model grows a kind the fixtures
    never build, this is what notices."""
    assert _emitted_kinds() == DOCUMENTED_KINDS
