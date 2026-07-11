from pgtp_editor.model.nodes import PageNode, ProjectModel
from pgtp_editor.diff.differ import diff_project


def make_page(file_name, **extra_attrib):
    attrib = {"fileName": file_name}
    attrib.update(extra_attrib)
    return PageNode(identity=file_name, attrib=attrib)


def test_diff_project_two_empty_projects_returns_empty_list():
    source = ProjectModel(pages=[])
    target = ProjectModel(pages=[])
    assert diff_project(source, target) == []


def test_diff_project_page_added_in_source():
    page = make_page("new_page", tableName="pr.new", caption="New Page")
    source = ProjectModel(pages=[page])
    target = ProjectModel(pages=[])

    result = diff_project(source, target)

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["new_page"]
    assert diff.node_kind == "page"
    assert diff.attribute is None
    assert diff.old_value is None
    assert diff.new_value is page
    assert diff.ambiguous is False
