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
    NOT_COMPARED_TEXT,
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
