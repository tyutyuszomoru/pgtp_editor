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


def test_diff_project_page_removed_from_target():
    page = make_page("old_page", tableName="pr.old", caption="Old Page")
    source = ProjectModel(pages=[])
    target = ProjectModel(pages=[page])

    result = diff_project(source, target)

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "removed"
    assert diff.path == ["old_page"]
    assert diff.node_kind == "page"
    assert diff.attribute is None
    assert diff.old_value is page
    assert diff.new_value is None
    assert diff.ambiguous is False


def test_diff_project_page_attribute_changed():
    source_page = make_page("shared_page", tableName="pr.shared", caption="New Caption")
    target_page = make_page("shared_page", tableName="pr.shared", caption="Old Caption")
    source = ProjectModel(pages=[source_page])
    target = ProjectModel(pages=[target_page])

    result = diff_project(source, target)

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page"]
    assert diff.node_kind == "page"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Caption"
    assert diff.new_value == "New Caption"
    assert diff.ambiguous is False


def test_diff_project_matched_pages_no_differences():
    source_page = make_page("shared_page", tableName="pr.shared", caption="Same")
    target_page = make_page("shared_page", tableName="pr.shared", caption="Same")
    source = ProjectModel(pages=[source_page])
    target = ProjectModel(pages=[target_page])

    assert diff_project(source, target) == []
