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


def test_diff_project_duplicate_sibling_details_paired_positionally_and_flagged_ambiguous():
    # Two source Details and two target Details share the same
    # (tableName, caption) = ("pr.operation", "Operation"). They should be
    # paired positionally (1st with 1st, 2nd with 2nd) and every resulting
    # Difference record marked ambiguous=True.
    source_first = make_detail("pr.operation", "Operation")
    source_first.attrib["ability"] = "first-source-ability"
    source_second = make_detail("pr.operation", "Operation")
    source_second.attrib["ability"] = "second-source-ability"

    target_first = make_detail("pr.operation", "Operation")
    target_first.attrib["ability"] = "first-target-ability"
    target_second = make_detail("pr.operation", "Operation")
    target_second.attrib["ability"] = "second-target-ability"

    source_page = make_page("shared_page")
    source_page.details = [source_first, source_second]
    target_page = make_page("shared_page")
    target_page.details = [target_first, target_second]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 2
    for diff in result:
        assert diff.ambiguous is True
        assert diff.kind == "changed"
        assert diff.node_kind == "detail"
        assert diff.attribute == "ability"

    by_old_value = {d.old_value: d for d in result}
    assert by_old_value["first-target-ability"].new_value == "first-source-ability"
    assert by_old_value["second-target-ability"].new_value == "second-source-ability"


def test_diff_project_duplicate_sibling_details_extra_on_source_side_marked_ambiguous():
    # 2 source Details, 1 target Detail sharing the same key: the 1st pair
    # matches (ambiguous, since the group has size > 1), the 2nd source
    # Detail has no target counterpart and is an ambiguous Added record.
    source_first = make_detail("pr.operation", "Operation")
    source_second = make_detail("pr.operation", "Operation")
    target_first = make_detail("pr.operation", "Operation")

    source_page = make_page("shared_page")
    source_page.details = [source_first, source_second]
    target_page = make_page("shared_page")
    target_page.details = [target_first]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.node_kind == "detail"
    assert diff.new_value is source_second
    assert diff.ambiguous is True


def test_diff_project_single_detail_per_key_not_marked_ambiguous():
    # Sanity check: a group of size 1 on both sides (the normal case,
    # already covered by Task 7's tests) must NOT be flagged ambiguous.
    source_detail = make_detail("pr.attachment", "Sub-item")
    source_detail.attrib["ability"] = "new-ability"
    target_detail = make_detail("pr.attachment", "Sub-item")
    target_detail.attrib["ability"] = "old-ability"

    source_page = make_page("shared_page")
    source_page.details = [source_detail]
    target_page = make_page("shared_page")
    target_page.details = [target_detail]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    assert result[0].ambiguous is False


def test_diff_project_nested_details_two_levels_deep_change_detected():
    # top_page -> Detail(pr.level1) -> Detail(pr.level2) with a changed
    # column caption at the deepest level.
    source_level2 = make_detail("pr.level2", "Level2")
    source_level2.columns = [make_column("deep_field", caption="New Deep Caption")]
    source_level1 = make_detail("pr.level1", "Level1")
    source_level1.details = [source_level2]
    source_page = make_page("top_page")
    source_page.details = [source_level1]

    target_level2 = make_detail("pr.level2", "Level2")
    target_level2.columns = [make_column("deep_field", caption="Old Deep Caption")]
    target_level1 = make_detail("pr.level1", "Level1")
    target_level1.details = [target_level2]
    target_page = make_page("top_page")
    target_page.details = [target_level1]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["top_page", "pr.level1/Level1", "pr.level2/Level2", "deep_field"]
    assert diff.node_kind == "column"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Deep Caption"
    assert diff.new_value == "New Deep Caption"


def test_diff_project_nested_detail_added_at_second_level():
    source_level1 = make_detail("pr.level1", "Level1")
    source_level1.details = [make_detail("pr.level2", "Level2")]
    source_page = make_page("top_page")
    source_page.details = [source_level1]

    target_level1 = make_detail("pr.level1", "Level1")
    target_page = make_page("top_page")
    target_page.details = [target_level1]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["top_page", "pr.level1/Level1", "pr.level2/Level2"]
    assert diff.node_kind == "detail"


def test_diff_project_identical_nested_details_no_differences():
    def build_tree():
        level2 = make_detail("pr.level2", "Level2")
        level2.columns = [make_column("deep_field", caption="Same")]
        level1 = make_detail("pr.level1", "Level1")
        level1.details = [level2]
        page = make_page("top_page")
        page.details = [level1]
        return page

    assert diff_project(ProjectModel(pages=[build_tree()]), ProjectModel(pages=[build_tree()])) == []


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
    # Sanity check: a single event per base name on both sides (the normal
    # case) must NOT be flagged ambiguous, even though the tag names differ.
    assert diff.ambiguous is False


def test_diff_project_duplicate_sibling_events_paired_positionally_and_flagged_ambiguous():
    # Two source events (CustomDrawRow, CustomDrawRow_SimpleHandler) both
    # normalize to base name "CustomDrawRow", as do two target events
    # (CustomDrawRow, CustomDrawRow_OtherHandler). They should be paired
    # positionally (1st with 1st, 2nd with 2nd) and every resulting
    # Difference record marked ambiguous=True -- not a spurious single
    # record comparing the wrong two events' text.
    source_page = make_page("shared_page")
    source_page.events = [
        make_event("CustomDrawRow", "first_new_impl();"),
        make_event("CustomDrawRow_SimpleHandler", "second_new_impl();"),
    ]
    target_page = make_page("shared_page")
    target_page.events = [
        make_event("CustomDrawRow", "first_old_impl();"),
        make_event("CustomDrawRow_OtherHandler", "second_old_impl();"),
    ]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 2
    for diff in result:
        assert diff.ambiguous is True
        assert diff.kind == "changed"
        assert diff.node_kind == "event"

    by_old_value = {d.old_value: d for d in result}
    assert by_old_value["first_old_impl();"].new_value == "first_new_impl();"
    assert by_old_value["second_old_impl();"].new_value == "second_new_impl();"


def test_diff_project_duplicate_sibling_events_extra_on_source_side_marked_ambiguous():
    # 2 source events sharing a base name ("CustomDrawRow"), 1 target event
    # with that base name: the 1st pair matches (ambiguous, since the group
    # has size > 1), the 2nd source event has no target counterpart and is
    # an ambiguous Added record.
    source_page = make_page("shared_page")
    source_first = make_event("CustomDrawRow", "first_impl();")
    source_second = make_event("CustomDrawRow_SimpleHandler", "second_impl();")
    source_page.events = [source_first, source_second]
    target_page = make_page("shared_page")
    target_page.events = [make_event("CustomDrawRow", "first_impl();")]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.node_kind == "event"
    assert diff.new_value is source_second
    assert diff.ambiguous is True


from pgtp_editor.model.nodes import DetailNode


def make_detail(table_name, caption, **extra_attrib):
    attrib = {"tableName": table_name, "caption": caption}
    attrib.update(extra_attrib)
    return DetailNode(identity=f"{table_name}/{caption}", attrib=attrib)


def test_diff_project_detail_added():
    detail = make_detail("pr.attachment", "Sub-item")
    source_page = make_page("shared_page")
    source_page.details = [detail]
    target_page = make_page("shared_page")

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["shared_page", "pr.attachment/Sub-item"]
    assert diff.node_kind == "detail"
    assert diff.attribute is None
    assert diff.old_value is None
    assert diff.new_value is detail


def test_diff_project_detail_removed():
    detail = make_detail("pr.attachment", "Sub-item")
    source_page = make_page("shared_page")
    target_page = make_page("shared_page")
    target_page.details = [detail]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "removed"
    assert diff.path == ["shared_page", "pr.attachment/Sub-item"]
    assert diff.node_kind == "detail"
    assert diff.old_value is detail
    assert diff.new_value is None


def test_diff_project_detail_attribute_changed():
    source_detail = make_detail("pr.attachment", "Sub-item")
    source_detail.attrib["ability"] = "insert,edit"
    target_detail = make_detail("pr.attachment", "Sub-item")
    target_detail.attrib["ability"] = "view"

    source_page = make_page("shared_page")
    source_page.details = [source_detail]
    target_page = make_page("shared_page")
    target_page.details = [target_detail]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page", "pr.attachment/Sub-item"]
    assert diff.node_kind == "detail"
    assert diff.attribute == "ability"
    assert diff.old_value == "view"
    assert diff.new_value == "insert,edit"


def test_diff_project_detail_recurses_columns_and_events():
    source_detail = make_detail("pr.attachment", "Sub-item")
    source_detail.columns = [make_column("cvalue", caption="New Caption")]
    target_detail = make_detail("pr.attachment", "Sub-item")
    target_detail.columns = [make_column("cvalue", caption="Old Caption")]

    source_page = make_page("shared_page")
    source_page.details = [source_detail]
    target_page = make_page("shared_page")
    target_page.details = [target_detail]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page", "pr.attachment/Sub-item", "cvalue"]
    assert diff.node_kind == "column"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Caption"
    assert diff.new_value == "New Caption"


def test_diff_project_matched_details_no_differences():
    source_detail = make_detail("pr.attachment", "Sub-item")
    target_detail = make_detail("pr.attachment", "Sub-item")

    source_page = make_page("shared_page")
    source_page.details = [source_detail]
    target_page = make_page("shared_page")
    target_page.details = [target_detail]

    assert diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page])) == []
