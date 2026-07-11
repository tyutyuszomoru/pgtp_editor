import textwrap

import pytest

from pgtp_editor.model.parser import PgtpParseError, load_project


def write_pgtp(tmp_path, xml_text, name="test.pgtp"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(xml_text), encoding="utf-8")
    return path


SIMPLE_PROJECT = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <ColumnPresentations>
          <ColumnPresentation fieldName="tag" caption="Tag"/>
          <ColumnPresentation fieldName="description" caption="Description"/>
        </ColumnPresentations>
        <EventHandlers>
          <OnPreparePage>echo 'hi';</OnPreparePage>
          <OnRowProcess>echo 'row';</OnRowProcess>
        </EventHandlers>
        <Details>
          <Detail caption="Equipment\\Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item">
              <ColumnPresentations>
                <ColumnPresentation fieldName="cvalue" caption="Value"/>
              </ColumnPresentations>
              <EventHandlers>
                <OnPreparePage>echo 'nested';</OnPreparePage>
              </EventHandlers>
            </Page>
          </Detail>
        </Details>
      </Page>
      <Page fileName="work_orders" tableName="pr.x_workorder" caption="Work Orders">
        <EventHandlers>
          <OnRowProcess>echo 'wo';</OnRowProcess>
        </EventHandlers>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_load_project_returns_expected_page_count(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    assert len(project.pages) == 2


def test_page_identity_and_attribs(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    page = project.pages[0]
    assert page.identity == "development_equipment"
    assert page.attrib["tableName"] == "pr.equipment"
    assert page.attrib["caption"] == "Equipment"
    assert page.sourceline is not None
    assert page.sourceline > 0


def test_page_columns_parsed(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    page = project.pages[0]
    assert [c.attrib["fieldName"] for c in page.columns] == ["tag", "description"]
    assert page.columns[0].identity == "development_equipment/tag"


def test_page_events_parsed_with_side(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    page = project.pages[0]
    events_by_name = {e.tag_name: e for e in page.events}
    assert events_by_name["OnPreparePage"].side == "S"
    assert events_by_name["OnRowProcess"].side == "S"
    assert events_by_name["OnPreparePage"].text.strip() == "echo 'hi';"


def test_page_details_parsed(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    page = project.pages[0]
    assert len(page.details) == 1
    detail = page.details[0]
    assert detail.attrib["tableName"] == "pr.attachment"
    assert detail.identity == "development_equipment/pr.attachment"


def test_detail_columns_and_events(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    detail = project.pages[0].details[0]
    assert [c.attrib["fieldName"] for c in detail.columns] == ["cvalue"]
    assert detail.columns[0].identity == "development_equipment/pr.attachment/cvalue"
    assert len(detail.events) == 1
    assert detail.events[0].tag_name == "OnPreparePage"


def test_second_page_no_columns_no_details(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    page = project.pages[1]
    assert page.columns == []
    assert page.details == []
    assert len(page.events) == 1


NESTED_DETAILS_PROJECT = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="top_page" tableName="pr.top" caption="Top">
        <Details>
          <Detail caption="Top\\Level1">
            <Page fileName="" tableName="pr.level1" caption="Level1">
              <Details>
                <Detail caption="Top\\Level1\\Level2">
                  <Page fileName="" tableName="pr.level2" caption="Level2">
                    <ColumnPresentations>
                      <ColumnPresentation fieldName="deep_field" caption="Deep"/>
                    </ColumnPresentations>
                    <EventHandlers>
                      <OnPreparePage>echo 'deep';</OnPreparePage>
                    </EventHandlers>
                  </Page>
                </Detail>
              </Details>
            </Page>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_deeply_nested_details_recurse_at_least_two_levels(tmp_path):
    path = write_pgtp(tmp_path, NESTED_DETAILS_PROJECT)
    project = load_project(path)
    top = project.pages[0]
    level1 = top.details[0]
    assert level1.attrib["tableName"] == "pr.level1"
    assert level1.identity == "top_page/pr.level1"

    level2 = level1.details[0]
    assert level2.attrib["tableName"] == "pr.level2"
    assert level2.identity == "top_page/pr.level1/pr.level2"
    assert level2.columns[0].attrib["fieldName"] == "deep_field"
    assert level2.events[0].tag_name == "OnPreparePage"


CLIENT_SERVER_EVENTS_PROJECT = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="events_page" tableName="pr.events" caption="Events">
        <EventHandlers>
          <OnBeforePageLoad>a();</OnBeforePageLoad>
          <OnAfterPageLoad>b();</OnAfterPageLoad>
          <OnInsertFormLoaded>c();</OnInsertFormLoaded>
          <OnEditFormLoaded>d();</OnEditFormLoaded>
          <OnInsertFormEditorValueChanged>e();</OnInsertFormEditorValueChanged>
          <OnEditFormEditorValueChanged>f();</OnEditFormEditorValueChanged>
          <OnInsertFormValidate>g();</OnInsertFormValidate>
          <OnEditFormValidate>h();</OnEditFormValidate>
          <OnCalculateControlValues>i();</OnCalculateControlValues>
          <OnPreparePage>j();</OnPreparePage>
          <CustomDrawRow_SimpleHandler>k();</CustomDrawRow_SimpleHandler>
          <SomeUnknownHandler>l();</SomeUnknownHandler>
        </EventHandlers>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_client_side_events_classified_correctly(tmp_path):
    path = write_pgtp(tmp_path, CLIENT_SERVER_EVENTS_PROJECT)
    project = load_project(path)
    page = project.pages[0]
    sides = {e.tag_name: e.side for e in page.events}
    client_names = [
        "OnBeforePageLoad", "OnAfterPageLoad", "OnInsertFormLoaded", "OnEditFormLoaded",
        "OnInsertFormEditorValueChanged", "OnEditFormEditorValueChanged",
        "OnInsertFormValidate", "OnEditFormValidate", "OnCalculateControlValues",
    ]
    for name in client_names:
        assert sides[name] == "C", name


def test_server_side_default_and_suffix_normalization(tmp_path):
    path = write_pgtp(tmp_path, CLIENT_SERVER_EVENTS_PROJECT)
    project = load_project(path)
    page = project.pages[0]
    sides = {e.tag_name: e.side for e in page.events}
    assert sides["OnPreparePage"] == "S"
    assert sides["SomeUnknownHandler"] == "S"
    # Suffix-variant tag names normalize to their base name for classification,
    # but the base name itself (CustomDrawRow) isn't in the client list either,
    # so it should default to server-side.
    assert sides["CustomDrawRow_SimpleHandler"] == "S"


def test_parse_failure_raises_clear_error(tmp_path):
    path = tmp_path / "broken.pgtp"
    path.write_text("<Project><Presentation><Pages><Page></Pages></Presentation></Project>", encoding="utf-8")
    with pytest.raises(Exception):
        load_project(path)


def test_missing_file_raises_pgtp_parse_error_not_os_error(tmp_path):
    missing_path = tmp_path / "does_not_exist.pgtp"
    assert not missing_path.exists()
    with pytest.raises(PgtpParseError) as excinfo:
        load_project(missing_path)
    # The underlying OSError should still be visible as the chained cause.
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, OSError)


DETAIL_MISSING_NESTED_PAGE_PROJECT = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="top_page" tableName="pr.top" caption="Top">
        <Details>
          <Detail caption="Top\\Broken">
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_detail_missing_nested_page_raises_pgtp_parse_error_with_sourceline(tmp_path):
    path = write_pgtp(tmp_path, DETAIL_MISSING_NESTED_PAGE_PROJECT)
    with pytest.raises(PgtpParseError) as excinfo:
        load_project(path)
    message = str(excinfo.value)
    # The ValueError raised by _parse_detail includes "(line N)"; ensure the
    # sourceline information survives being wrapped into PgtpParseError.
    assert "line" in message.lower()


def test_missing_optional_attributes_handled(tmp_path):
    xml = """\
    <?xml version="1.0" encoding="UTF-8"?>
    <Project>
      <Presentation>
        <Pages>
          <Page fileName="minimal_page">
          </Page>
        </Pages>
      </Presentation>
    </Project>
    """
    path = write_pgtp(tmp_path, xml)
    project = load_project(path)
    page = project.pages[0]
    assert page.identity == "minimal_page"
    assert page.columns == []
    assert page.details == []
    assert page.events == []
