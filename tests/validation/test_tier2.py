"""Unit tests for the Qt-free Tier-2 structural-sanity validator.

Projects are built from XML text via load_project_from_text so the lxml
sourceline numbers line up with the literal lines of the string.
"""
from pathlib import Path

import pytest

from pgtp_editor.model.parser import load_project_from_text
from pgtp_editor.validation.tier2 import ValidationIssue, validate_project

SAMPLE = Path(__file__).resolve().parents[2] / "sample" / "dev_Ferrara.pgtp"


def _errors(issues):
    return [i for i in issues if i.severity == "error"]


def _warnings(issues):
    return [i for i in issues if i.severity == "warning"]


def test_none_project_returns_empty():
    assert validate_project(None) == []


def test_project_with_none_tree_returns_empty():
    from pgtp_editor.model.nodes import ProjectModel

    assert validate_project(ProjectModel(pages=[], tree=None)) == []


def test_clean_project_returns_empty():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="a.php" tableName="t_a"/>\n'
        '      <Page fileName="b.php" tableName="t_b"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    assert validate_project(project) == []


def test_duplicate_filename_emits_one_error_per_colliding_page():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="dup.php" tableName="t1"/>\n'
        '      <Page fileName="unique.php" tableName="t2"/>\n'
        '      <Page fileName="dup.php" tableName="t3"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    issues = validate_project(project)
    errors = _errors(issues)
    assert len(errors) == 2
    assert all(e.message == 'duplicate Page fileName "dup.php"' for e in errors)
    # Correct lines: the two <Page fileName="dup.php"> sit on source lines 4 and 6.
    assert sorted(e.line for e in errors) == [4, 6]


def test_two_top_level_pages_sharing_filename_emit_two_errors():
    # Genuine collision: two DIRECT children of <Pages> share a fileName.
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="event" tableName="t1"/>\n'
        '      <Page fileName="event" tableName="t2"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    errors = _errors(validate_project(project))
    assert len(errors) == 2
    assert all(e.message == 'duplicate Page fileName "event"' for e in errors)
    assert sorted(e.line for e in errors) == [4, 5]


def test_nested_detail_page_reusing_master_filename_emits_no_error():
    # Regression: a top-level <Page fileName="event"> containing a nested
    # <Detail><Page fileName="event"> legitimately reuses the master page's
    # fileName. The dup check is scoped to top-level pages, so this must NOT
    # produce any ERROR-severity issue.
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="event" tableName="t">\n'
        '        <Details>\n'
        '          <Detail tableName="d">\n'
        '            <Page fileName="event" tableName="d"/>\n'
        '          </Detail>\n'
        '        </Details>\n'
        '      </Page>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    assert _errors(validate_project(project)) == []


def test_unique_filenames_emit_no_duplicate_error():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="a.php" tableName="t1"/>\n'
        '      <Page fileName="b.php" tableName="t2"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    assert _errors(validate_project(project)) == []


def test_top_level_page_missing_filename_and_tablename_warned():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page caption="no attrs"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    warnings = _warnings(validate_project(project))
    messages = {w.message for w in warnings}
    assert "Page missing fileName" in messages
    assert "Page missing tableName" in messages
    assert all(w.line == 4 for w in warnings)


def test_top_level_page_empty_filename_warned():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="" tableName="t"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    messages = {w.message for w in _warnings(validate_project(project))}
    assert "Page missing fileName" in messages
    assert "Page missing tableName" not in messages


def test_nested_detail_page_missing_filename_not_warned():
    # A <Page> nested under a <Detail> is NOT a top-level page (its parent
    # tag is not "Pages"), so a missing fileName there must NOT be warned.
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="top.php" tableName="t">\n'
        '        <Details>\n'
        '          <Detail tableName="d">\n'
        '            <Page caption="nested"/>\n'
        '          </Detail>\n'
        '        </Details>\n'
        '      </Page>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    warnings = _warnings(validate_project(project))
    # No "Page missing fileName" for the nested page on line 7.
    assert not any(
        w.message == "Page missing fileName" and w.line == 7 for w in warnings
    )
    assert not any(w.message == "Page missing fileName" for w in warnings)


def test_column_presentation_missing_fieldname_warned():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="a.php" tableName="t">\n'
        '        <ColumnPresentations>\n'
        '          <ColumnPresentation caption="c"/>\n'
        '          <ColumnPresentation fieldName="ok"/>\n'
        '        </ColumnPresentations>\n'
        '      </Page>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    warnings = _warnings(validate_project(project))
    missing = [w for w in warnings if w.message == "ColumnPresentation missing fieldName"]
    assert len(missing) == 1
    assert missing[0].line == 6


def test_unexpected_child_in_pages():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="a.php" tableName="t"/>\n'
        '      <Widget/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    warnings = _warnings(validate_project(project))
    assert any(
        w.message == "unexpected <Widget> inside <Pages>" and w.line == 5
        for w in warnings
    )


def test_unexpected_child_in_details():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="a.php" tableName="t">\n'
        '        <Details>\n'
        '          <Detail tableName="d">\n'
        '            <Page fileName="d.php" tableName="d"/>\n'
        '          </Detail>\n'
        '          <Bogus/>\n'
        '        </Details>\n'
        '      </Page>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    warnings = _warnings(validate_project(project))
    assert any(
        w.message == "unexpected <Bogus> inside <Details>" and w.line == 9
        for w in warnings
    )


def test_unexpected_child_in_column_presentations():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="a.php" tableName="t">\n'
        '        <ColumnPresentations>\n'
        '          <ColumnPresentation fieldName="ok"/>\n'
        '          <NotAColumn/>\n'
        '        </ColumnPresentations>\n'
        '      </Page>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    warnings = _warnings(validate_project(project))
    assert any(
        w.message == "unexpected <NotAColumn> inside <ColumnPresentations>" and w.line == 7
        for w in warnings
    )


def test_comments_inside_container_ignored():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <!-- a comment -->\n'
        '      <Page fileName="a.php" tableName="t"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    warnings = _warnings(validate_project(project))
    assert not any("unexpected" in w.message for w in warnings)


def test_issues_are_ordered_by_line():
    text = (
        '<Project>\n'
        '  <Presentation>\n'
        '    <Pages>\n'
        '      <Page fileName="dup.php" tableName="t1"/>\n'
        '      <Page caption="no attrs"/>\n'
        '      <Page fileName="dup.php" tableName="t3"/>\n'
        '    </Pages>\n'
        '  </Presentation>\n'
        '</Project>\n'
    )
    project = load_project_from_text(text)
    issues = validate_project(project)
    lines = [i.line for i in issues if i.line is not None]
    assert lines == sorted(lines)


def test_validation_issue_is_frozen_dataclass():
    issue = ValidationIssue(severity="error", message="x", line=3)
    with pytest.raises(Exception):
        issue.line = 4  # frozen


def test_real_sample_has_no_errors():
    if not SAMPLE.exists():
        pytest.skip(f"sample fixture not present on disk: {SAMPLE}")
    from pgtp_editor.model.parser import load_project

    project = load_project(str(SAMPLE))
    issues = validate_project(project)
    errors = _errors(issues)
    assert errors == [], f"known-good sample produced ERRORs: {errors}"
