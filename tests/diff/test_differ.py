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


from pgtp_editor.model.nodes import ColumnNode


def make_column(field_name, **extra_attrib):
    attrib = {"fieldName": field_name}
    attrib.update(extra_attrib)
    return ColumnNode(identity=field_name, attrib=attrib)


def test_diff_project_column_added():
    col = make_column("new_field", caption="New Field")
    source_page = make_page("shared_page")
    source_page.columns = [col]
    target_page = make_page("shared_page")

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["shared_page", "new_field"]
    assert diff.node_kind == "column"
    assert diff.attribute is None
    assert diff.old_value is None
    assert diff.new_value is col


def test_diff_project_column_removed():
    col = make_column("old_field", caption="Old Field")
    source_page = make_page("shared_page")
    target_page = make_page("shared_page")
    target_page.columns = [col]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "removed"
    assert diff.path == ["shared_page", "old_field"]
    assert diff.node_kind == "column"
    assert diff.attribute is None
    assert diff.old_value is col
    assert diff.new_value is None


def test_diff_project_column_attribute_changed():
    source_page = make_page("shared_page")
    source_page.columns = [make_column("tag", caption="New Caption")]
    target_page = make_page("shared_page")
    target_page.columns = [make_column("tag", caption="Old Caption")]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page", "tag"]
    assert diff.node_kind == "column"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Caption"
    assert diff.new_value == "New Caption"


def test_diff_project_matched_columns_no_differences():
    source_page = make_page("shared_page")
    source_page.columns = [make_column("tag", caption="Same")]
    target_page = make_page("shared_page")
    target_page.columns = [make_column("tag", caption="Same")]

    assert diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page])) == []


from pgtp_editor.model.nodes import EventNode


def make_event(tag_name, text, side="S"):
    return EventNode(identity=tag_name, tag_name=tag_name, side=side, text=text)


def test_diff_project_event_added():
    event = make_event("OnRowProcess", "echo 'new';")
    source_page = make_page("shared_page")
    source_page.events = [event]
    target_page = make_page("shared_page")

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["shared_page", "OnRowProcess"]
    assert diff.node_kind == "event"
    assert diff.attribute is None
    assert diff.old_value is None
    assert diff.new_value is event


def test_diff_project_event_removed():
    event = make_event("OnRowProcess", "echo 'old';")
    source_page = make_page("shared_page")
    target_page = make_page("shared_page")
    target_page.events = [event]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "removed"
    assert diff.path == ["shared_page", "OnRowProcess"]
    assert diff.node_kind == "event"
    assert diff.attribute is None
    assert diff.old_value is event
    assert diff.new_value is None


def test_diff_project_event_text_changed():
    source_page = make_page("shared_page")
    source_page.events = [make_event("OnRowProcess", "echo 'new text';")]
    target_page = make_page("shared_page")
    target_page.events = [make_event("OnRowProcess", "echo 'old text';")]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page", "OnRowProcess"]
    assert diff.node_kind == "event"
    assert diff.attribute is None
    assert diff.old_value == "echo 'old text';"
    assert diff.new_value == "echo 'new text';"


def test_diff_project_matched_events_no_differences():
    source_page = make_page("shared_page")
    source_page.events = [make_event("OnRowProcess", "same();")]
    target_page = make_page("shared_page")
    target_page.events = [make_event("OnRowProcess", "same();")]

    assert diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page])) == []


def test_diff_project_event_suffix_variants_match_by_base_name():
    # CustomDrawRow_SimpleHandler and CustomDrawRow_OtherHandler both
    # normalize to base name "CustomDrawRow" and should be matched as the
    # same event (base-name matching, per classify_event_side's suffix rule).
    source_page = make_page("shared_page")
    source_page.events = [make_event("CustomDrawRow_SimpleHandler", "new_impl();")]
    target_page = make_page("shared_page")
    target_page.events = [make_event("CustomDrawRow_OtherHandler", "old_impl();")]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.node_kind == "event"
    assert diff.old_value == "old_impl();"
    assert diff.new_value == "new_impl();"
