"""Tests for pgtp_editor.diff.apply.apply_differences -- see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md §5.
"""
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
