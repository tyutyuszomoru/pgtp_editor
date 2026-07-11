from pgtp_editor.diff.resolve import ResolutionError


def test_resolution_error_holds_segment_index_and_message():
    error = ResolutionError(segment_index=0, message="no Page named 'missing_page'")
    assert error.segment_index == 0
    assert error.message == "no Page named 'missing_page'"


from pgtp_editor.model.nodes import PageNode, ProjectModel
from pgtp_editor.diff.resolve import resolve_path


def make_page(file_name, **extra_attrib):
    attrib = {"fileName": file_name}
    attrib.update(extra_attrib)
    return PageNode(identity=file_name, attrib=attrib)


def test_resolve_path_finds_page_at_depth_one():
    page = make_page("development_equipment", tableName="pr.equipment", caption="Equipment")
    project = ProjectModel(pages=[page])

    result = resolve_path(project, ["development_equipment"])

    assert result is page


def test_resolve_path_page_not_found_at_depth_one():
    project = ProjectModel(pages=[make_page("existing_page")])

    result = resolve_path(project, ["missing_page"])

    assert isinstance(result, ResolutionError)
    assert result.segment_index == 0
    assert result.message == "no Page named 'missing_page'"


from pgtp_editor.model.nodes import DetailNode


def make_detail(table_name, caption, details=None):
    return DetailNode(
        identity=f"{table_name}/{caption}",
        attrib={"tableName": table_name, "caption": caption},
        details=details or [],
    )


def test_resolve_path_finds_detail_at_depth_two():
    sub_item = make_detail("pr.attachment", "Sub-item")
    page = make_page("development_equipment", tableName="pr.equipment")
    page.details = [sub_item]
    project = ProjectModel(pages=[page])

    result = resolve_path(project, ["development_equipment", "pr.attachment/Sub-item"])

    assert result is sub_item


def test_resolve_path_finds_nested_detail_at_depth_three():
    level2 = make_detail("pr.level2", "Level2")
    level1 = make_detail("pr.level1", "Level1", details=[level2])
    page = make_page("top_page")
    page.details = [level1]
    project = ProjectModel(pages=[page])

    result = resolve_path(
        project,
        ["top_page", "pr.level1/Level1", "pr.level2/Level2"],
    )

    assert result is level2


def test_resolve_path_detail_not_found_at_depth_two():
    page = make_page("development_equipment")
    page.details = [make_detail("pr.attachment", "Sub-item")]
    project = ProjectModel(pages=[page])

    result = resolve_path(
        project,
        ["development_equipment", "pr.r_characteristic/Attachment"],
    )

    assert isinstance(result, ResolutionError)
    assert result.segment_index == 1
    assert result.message == (
        "no Detail matching (tableName='pr.r_characteristic', caption='Attachment') "
        "under development_equipment"
    )


def test_resolve_path_detail_not_found_at_depth_three_names_full_resolved_prefix():
    level1 = make_detail("pr.level1", "Level1", details=[])
    page = make_page("top_page")
    page.details = [level1]
    project = ProjectModel(pages=[page])

    result = resolve_path(
        project,
        ["top_page", "pr.level1/Level1", "pr.level2/Level2"],
    )

    assert isinstance(result, ResolutionError)
    assert result.segment_index == 2
    assert result.message == (
        "no Detail matching (tableName='pr.level2', caption='Level2') "
        "under top_page/pr.level1/Level1"
    )


def test_resolve_path_duplicate_sibling_details_first_match_wins():
    first = make_detail("pr.operation", "Operation")
    first.attrib["ability"] = "first"
    second = make_detail("pr.operation", "Operation")
    second.attrib["ability"] = "second"
    page = make_page("shared_page")
    page.details = [first, second]
    project = ProjectModel(pages=[page])

    result = resolve_path(project, ["shared_page", "pr.operation/Operation"])

    assert result is first
