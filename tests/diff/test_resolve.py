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
