from pgtp_editor.model.line_index import node_at_line
from pgtp_editor.model.nodes import (
    ColumnNode,
    DetailNode,
    EventNode,
    PageNode,
    ProjectModel,
)


def _nested_depth_project():
    """Page (line 5) > Detail (line 10, inner Page line 11)
    > nested Detail (line 15, inner Page line 16) > Column (line 18).
    The next node after the Column is the second top-level Page at line 30.
    """
    column = ColumnNode(identity="c", attrib={"fieldName": "c"}, sourceline=18)
    nested_detail = DetailNode(
        identity="d/nd",
        attrib={"tableName": "nd"},
        sourceline=15,
        inner_sourceline=16,
        columns=[column],
    )
    outer_detail = DetailNode(
        identity="d",
        attrib={"tableName": "d"},
        sourceline=10,
        inner_sourceline=11,
        details=[nested_detail],
    )
    page = PageNode(
        identity="p",
        attrib={"tableName": "p"},
        sourceline=5,
        details=[outer_detail],
    )
    second_page = PageNode(identity="p2", attrib={"tableName": "p2"}, sourceline=30)
    return ProjectModel(pages=[page, second_page]), page, outer_detail, nested_detail, column


def test_click_on_page_open_line_returns_page():
    project, page, _outer, _nested, _column = _nested_depth_project()
    assert node_at_line(project, 5) is page


def test_click_in_outer_detail_whitespace_returns_outer_detail():
    project, _page, outer, _nested, _column = _nested_depth_project()
    # Line 12: inside the outer Detail (open line 10, inner Page line 11)
    # but before the nested Detail (line 15) — resolves to the outer Detail.
    assert node_at_line(project, 12) is outer


def test_click_on_nested_detail_line_returns_nested_detail():
    project, _page, _outer, nested, _column = _nested_depth_project()
    assert node_at_line(project, 16) is nested


def test_click_on_column_line_returns_column():
    project, _page, _outer, _nested, column = _nested_depth_project()
    assert node_at_line(project, 18) is column


def test_click_inside_column_subelement_returns_column():
    """A Column at line 20 with the next node (a sibling Column) at line 30.
    Lines 21-29 are the Column's <Format>/<Lookup> body — no node of their
    own — and all resolve to the Column."""
    first_col = ColumnNode(identity="c1", attrib={"fieldName": "c1"}, sourceline=20)
    second_col = ColumnNode(identity="c2", attrib={"fieldName": "c2"}, sourceline=30)
    page = PageNode(
        identity="p", attrib={"tableName": "p"}, sourceline=5, columns=[first_col, second_col]
    )
    project = ProjectModel(pages=[page])
    for line in range(21, 30):
        assert node_at_line(project, line) is first_col, f"line {line}"


def test_click_in_detail_whitespace_before_first_column_returns_detail():
    """A Detail at line 10 whose first child Column starts at line 14.
    Lines 11-13 (whitespace / <ColumnPresentations> open before any Column
    node) resolve to the Detail, not to any Column."""
    column = ColumnNode(identity="c", attrib={"fieldName": "c"}, sourceline=14)
    detail = DetailNode(
        identity="d", attrib={"tableName": "d"}, sourceline=10, inner_sourceline=11, columns=[column]
    )
    page = PageNode(identity="p", attrib={"tableName": "p"}, sourceline=5, details=[detail])
    project = ProjectModel(pages=[page])
    for line in (11, 12, 13):
        assert node_at_line(project, line) is detail, f"line {line}"
    assert node_at_line(project, 14) is column


def test_line_above_first_page_returns_none():
    page = PageNode(identity="p", attrib={"tableName": "p"}, sourceline=5)
    project = ProjectModel(pages=[page])
    for line in (1, 2, 3, 4):
        assert node_at_line(project, line) is None, f"line {line}"


def test_duplicate_table_details_disambiguated_by_line_identity():
    """Two Details with the same tableName at different document positions.
    node_at_line returns the specific instance whose range contains the line,
    verified by object identity (`is`), not table name."""
    first = DetailNode(identity="d1", attrib={"tableName": "dup"}, sourceline=10, inner_sourceline=11)
    second = DetailNode(identity="d2", attrib={"tableName": "dup"}, sourceline=40, inner_sourceline=41)
    page = PageNode(
        identity="p", attrib={"tableName": "p"}, sourceline=5, details=[first, second]
    )
    project = ProjectModel(pages=[page])
    assert node_at_line(project, 12) is first
    assert node_at_line(project, 42) is second


def test_node_with_none_sourceline_is_dropped():
    good = ColumnNode(identity="good", attrib={"fieldName": "good"}, sourceline=10)
    bad = ColumnNode(identity="bad", attrib={"fieldName": "bad"}, sourceline=None)
    page = PageNode(identity="p", attrib={"tableName": "p"}, sourceline=5, columns=[bad, good])
    project = ProjectModel(pages=[page])
    # The None-sourceline column is never returned; line 10 resolves to `good`.
    assert node_at_line(project, 10) is good
    result = node_at_line(project, 999)
    assert result is not bad


def test_project_none_returns_none():
    assert node_at_line(None, 5) is None


def test_empty_project_returns_none():
    assert node_at_line(ProjectModel(pages=[]), 5) is None


def test_event_node_resolved_at_its_line():
    event = EventNode(identity="e", tag_name="OnRowProcess", side="C", text="", sourceline=8)
    page = PageNode(identity="p", attrib={"tableName": "p"}, sourceline=5, events=[event])
    project = ProjectModel(pages=[page])
    assert node_at_line(project, 8) is event
