"""Tests for pgtp_editor.diff.apply.apply_differences -- see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md §5.
"""
import copy

from lxml import etree

from pgtp_editor.diff.apply import ApplyFailure, ApplyResult, apply_differences
from pgtp_editor.diff.records import Difference
from pgtp_editor.model.parser import _build_project_model


def build_project(xml_text):
    tree = etree.fromstring(xml_text.encode("utf-8")).getroottree()
    return _build_project_model(tree, source_description="<test fixture>")


SIMPLE_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Old Caption"/>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_result_dataclass_shape():
    result = ApplyResult(applied=[], failed=[])
    assert result.applied == []
    assert result.failed == []


def test_apply_failure_dataclass_shape():
    diff = Difference(kind="changed", path=["p"], node_kind="page", attribute="x", old_value=None, new_value=None)
    failure = ApplyFailure(difference=diff, message="boom")
    assert failure.difference is diff
    assert failure.message == "boom"


def test_apply_changed_page_attribute_sets_value_on_real_element():
    target = build_project(SIMPLE_TARGET)
    diff = Difference(
        kind="changed",
        path=["development_equipment"],
        node_kind="page",
        attribute="caption",
        old_value="Old Caption",
        new_value="New Caption",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    assert result.applied == [diff]
    page_el = target.tree.getroot().find("Presentation/Pages/Page")
    assert page_el.get("caption") == "New Caption"


def test_apply_changed_page_attribute_leaves_other_attributes_untouched():
    target = build_project(SIMPLE_TARGET)
    diff = Difference(
        kind="changed",
        path=["development_equipment"],
        node_kind="page",
        attribute="caption",
        old_value="Old Caption",
        new_value="New Caption",
    )

    apply_differences(target, [diff])

    page_el = target.tree.getroot().find("Presentation/Pages/Page")
    assert page_el.get("fileName") == "development_equipment"
    assert page_el.get("tableName") == "pr.equipment"


def test_apply_changed_attribute_with_none_new_value_deletes_attribute():
    xml = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p" ability="view,edit"/>
    </Pages>
  </Presentation>
</Project>
"""
    target = build_project(xml)
    diff = Difference(
        kind="changed", path=["p"], node_kind="page", attribute="ability",
        old_value="view,edit", new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    page_el = target.tree.getroot().find("Presentation/Pages/Page")
    assert "ability" not in page_el.attrib


DETAIL_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <Details>
          <Detail caption="Equipment\\Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item" ability="view"/>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_changed_detail_attribute_on_nested_page_element():
    target = build_project(DETAIL_TARGET)
    diff = Difference(
        kind="changed",
        path=["development_equipment", "pr.attachment/Sub-item"],
        node_kind="detail",
        attribute="ability",
        old_value="view",
        new_value="insert,edit",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    detail = target.pages[0].details[0]
    assert detail.inner_page_element.get("ability") == "insert,edit"
    # The outer <Detail> element itself carries no "ability" attribute in
    # this fixture and must remain untouched.
    assert "ability" not in detail.element.attrib


def test_apply_changed_detail_attribute_on_outer_detail_element_when_key_lives_there():
    xml = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p">
        <Details>
          <Detail caption="Sub-item" outerOnlyFlag="old-value">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item"/>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""
    target = build_project(xml)
    diff = Difference(
        kind="changed",
        path=["p", "pr.attachment/Sub-item"],
        node_kind="detail",
        attribute="outerOnlyFlag",
        old_value="old-value",
        new_value="new-value",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    detail = target.pages[0].details[0]
    assert detail.element.get("outerOnlyFlag") == "new-value"
    assert "outerOnlyFlag" not in detail.inner_page_element.attrib


def test_apply_changed_detail_attribute_new_key_defaults_to_inner_page_element():
    xml = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p">
        <Details>
          <Detail caption="Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item"/>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""
    target = build_project(xml)
    # brandNewKey exists on neither real element yet (Source added it) --
    # per spec §5.1, defaults to inner_page_element (the substantive-data element).
    diff = Difference(
        kind="changed",
        path=["p", "pr.attachment/Sub-item"],
        node_kind="detail",
        attribute="brandNewKey",
        old_value=None,
        new_value="brand-new-value",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    detail = target.pages[0].details[0]
    assert detail.inner_page_element.get("brandNewKey") == "brand-new-value"
    assert "brandNewKey" not in detail.element.attrib


COLUMN_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p">
        <ColumnPresentations>
          <ColumnPresentation fieldName="tag" caption="Old Tag Caption"/>
        </ColumnPresentations>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_changed_column_attribute():
    target = build_project(COLUMN_TARGET)
    diff = Difference(
        kind="changed",
        path=["p", "tag"],
        node_kind="column",
        attribute="caption",
        old_value="Old Tag Caption",
        new_value="New Tag Caption",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    column_el = target.tree.getroot().find("Presentation/Pages/Page/ColumnPresentations/ColumnPresentation")
    assert column_el.get("caption") == "New Tag Caption"


def test_apply_changed_column_attribute_fails_when_field_name_not_found():
    target = build_project(COLUMN_TARGET)
    diff = Difference(
        kind="changed",
        path=["p", "does_not_exist"],
        node_kind="column",
        attribute="caption",
        old_value="Old",
        new_value="New",
    )

    result = apply_differences(target, [diff])

    assert result.applied == []
    assert len(result.failed) == 1
    assert result.failed[0].difference is diff


EVENT_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p">
        <EventHandlers>
          <OnRowProcess>echo 'old';</OnRowProcess>
        </EventHandlers>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_changed_event_text_replaces_element_text():
    target = build_project(EVENT_TARGET)
    diff = Difference(
        kind="changed",
        path=["p", "OnRowProcess"],
        node_kind="event",
        attribute=None,
        old_value="echo 'old';",
        new_value="echo 'new';",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    event_el = target.tree.getroot().find("Presentation/Pages/Page/EventHandlers/OnRowProcess")
    assert event_el.text == "echo 'new';"


def test_apply_changed_event_text_fails_when_tag_not_found():
    target = build_project(EVENT_TARGET)
    diff = Difference(
        kind="changed",
        path=["p", "OnDoesNotExist"],
        node_kind="event",
        attribute=None,
        old_value="echo 'old';",
        new_value="echo 'new';",
    )

    result = apply_differences(target, [diff])

    assert result.applied == []
    assert len(result.failed) == 1


REMOVE_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="keep_me" tableName="pr.keep"/>
      <Page fileName="remove_me" tableName="pr.remove">
        <ColumnPresentations>
          <ColumnPresentation fieldName="doomed_column" caption="Doomed"/>
        </ColumnPresentations>
        <EventHandlers>
          <OnRowProcess>echo 'doomed';</OnRowProcess>
        </EventHandlers>
        <Details>
          <Detail caption="Doomed\\Sub">
            <Page fileName="" tableName="pr.doomed_sub" caption="Sub"/>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_removed_page_deletes_element_from_parent():
    target = build_project(REMOVE_TARGET)
    doomed_page = next(p for p in target.pages if p.file_name == "remove_me")
    diff = Difference(
        kind="removed", path=["remove_me"], node_kind="page",
        attribute=None, old_value=doomed_page, new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    remaining = target.tree.getroot().findall("Presentation/Pages/Page")
    assert [p.get("fileName") for p in remaining] == ["keep_me"]


def test_apply_removed_column_deletes_element():
    target = build_project(REMOVE_TARGET)
    page = next(p for p in target.pages if p.file_name == "remove_me")
    column = page.columns[0]
    diff = Difference(
        kind="removed", path=["remove_me", "doomed_column"], node_kind="column",
        attribute=None, old_value=column, new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    columns_container = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='remove_me']/ColumnPresentations"
    )
    assert columns_container.findall("ColumnPresentation") == []


def test_apply_removed_event_deletes_element():
    target = build_project(REMOVE_TARGET)
    page = next(p for p in target.pages if p.file_name == "remove_me")
    event = page.events[0]
    diff = Difference(
        kind="removed", path=["remove_me", "OnRowProcess"], node_kind="event",
        attribute=None, old_value=event, new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    events_container = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='remove_me']/EventHandlers"
    )
    assert list(events_container) == []


def test_apply_removed_detail_deletes_whole_outer_element_including_nested_page():
    target = build_project(REMOVE_TARGET)
    page = next(p for p in target.pages if p.file_name == "remove_me")
    detail = page.details[0]
    diff = Difference(
        kind="removed", path=["remove_me", "pr.doomed_sub/Sub"], node_kind="detail",
        attribute=None, old_value=detail, new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    details_container = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='remove_me']/Details"
    )
    assert details_container.findall("Detail") == []


ADD_SOURCE = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="existing_page" tableName="pr.existing">
        <ColumnPresentations>
          <ColumnPresentation fieldName="new_field" caption="Brand New Field"/>
        </ColumnPresentations>
        <EventHandlers>
          <OnRowProcess>echo 'new handler';</OnRowProcess>
        </EventHandlers>
        <Details>
          <Detail caption="Existing\\NewSub">
            <Page fileName="" tableName="pr.new_sub" caption="NewSub">
              <Details>
                <Detail caption="Existing\\NewSub\\Deeper">
                  <Page fileName="" tableName="pr.deeper" caption="Deeper"/>
                </Detail>
              </Details>
            </Page>
          </Detail>
        </Details>
      </Page>
      <Page fileName="brand_new_page" tableName="pr.brand_new" caption="Brand New Page"/>
    </Pages>
  </Presentation>
</Project>
"""

ADD_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="existing_page" tableName="pr.existing"/>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_added_page_appends_deepcopy_to_pages_container():
    source = build_project(ADD_SOURCE)
    target = build_project(ADD_TARGET)
    new_page = next(p for p in source.pages if p.file_name == "brand_new_page")
    diff = Difference(
        kind="added", path=["brand_new_page"], node_kind="page",
        attribute=None, old_value=None, new_value=new_page,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    pages = target.tree.getroot().findall("Presentation/Pages/Page")
    assert [p.get("fileName") for p in pages] == ["existing_page", "brand_new_page"]
    assert pages[1].get("caption") == "Brand New Page"
    # Confirm it's a deep copy, not a reference into Source's own tree.
    assert pages[1] is not new_page.element


def test_apply_added_column_appends_to_column_presentations():
    source = build_project(ADD_SOURCE)
    target = build_project(ADD_TARGET)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_column = source_page.columns[0]
    diff = Difference(
        kind="added", path=["existing_page", "new_field"], node_kind="column",
        attribute=None, old_value=None, new_value=new_column,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    columns = target.tree.getroot().findall(
        "Presentation/Pages/Page[@fileName='existing_page']/ColumnPresentations/ColumnPresentation"
    )
    assert len(columns) == 1
    assert columns[0].get("fieldName") == "new_field"
    assert columns[0].get("caption") == "Brand New Field"


def test_apply_added_column_creates_column_presentations_container_if_absent():
    # ADD_TARGET's existing_page has no ColumnPresentations element at all.
    target = build_project(ADD_TARGET)
    page_el = target.tree.getroot().find("Presentation/Pages/Page[@fileName='existing_page']")
    assert page_el.find("ColumnPresentations") is None

    source = build_project(ADD_SOURCE)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_column = source_page.columns[0]
    diff = Difference(
        kind="added", path=["existing_page", "new_field"], node_kind="column",
        attribute=None, old_value=None, new_value=new_column,
    )

    apply_differences(target, [diff])

    assert page_el.find("ColumnPresentations") is not None


def test_apply_added_event_appends_to_event_handlers_creating_container_if_absent():
    target = build_project(ADD_TARGET)
    source = build_project(ADD_SOURCE)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_event = source_page.events[0]
    diff = Difference(
        kind="added", path=["existing_page", "OnRowProcess"], node_kind="event",
        attribute=None, old_value=None, new_value=new_event,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    event_el = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='existing_page']/EventHandlers/OnRowProcess"
    )
    assert event_el is not None
    assert event_el.text == "echo 'new handler';"


def test_apply_added_detail_with_nested_details_survives_intact():
    target = build_project(ADD_TARGET)
    source = build_project(ADD_SOURCE)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_detail = source_page.details[0]
    diff = Difference(
        kind="added", path=["existing_page", "pr.new_sub/NewSub"], node_kind="detail",
        attribute=None, old_value=None, new_value=new_detail,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    detail_el = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='existing_page']/Details/Detail"
    )
    assert detail_el is not None
    inner_page = detail_el.find("Page")
    assert inner_page.get("tableName") == "pr.new_sub"
    # The whole nested subtree (a second level of Details/Detail/Page) must
    # have survived the deepcopy+insert intact.
    deeper_inner_page = inner_page.find("Details/Detail/Page")
    assert deeper_inner_page is not None
    assert deeper_inner_page.get("tableName") == "pr.deeper"


def test_apply_added_detail_creates_details_container_if_absent():
    target = build_project(ADD_TARGET)
    page_el = target.tree.getroot().find("Presentation/Pages/Page[@fileName='existing_page']")
    assert page_el.find("Details") is None

    source = build_project(ADD_SOURCE)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_detail = source_page.details[0]
    diff = Difference(
        kind="added", path=["existing_page", "pr.new_sub/NewSub"], node_kind="detail",
        attribute=None, old_value=None, new_value=new_detail,
    )

    apply_differences(target, [diff])

    assert page_el.find("Details") is not None
