"""Tests for the retained-lxml-element fields added to the model dataclasses
for the Diff/Merge write-back feature. See
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md §3.2.

Also covers DetailNode.inner_sourceline, added for the Properties panel
sub-project. See
docs/superpowers/specs/2026-07-12-pgtp-editor-properties-panel-design.md.
"""
from lxml import etree

from pgtp_editor.model.nodes import ColumnNode, DetailNode, EventNode, PageNode, ProjectModel


def test_page_node_element_defaults_to_none():
    page = PageNode(identity="p", attrib={})
    assert page.element is None


def test_page_node_element_can_be_set():
    el = etree.fromstring("<Page fileName='p'/>")
    page = PageNode(identity="p", attrib={}, element=el)
    assert page.element is el


def test_detail_node_has_element_and_inner_page_element_fields():
    detail_el = etree.fromstring("<Detail/>")
    inner_page_el = etree.fromstring("<Page tableName='t'/>")
    detail = DetailNode(
        identity="d", attrib={}, element=detail_el, inner_page_element=inner_page_el
    )
    assert detail.element is detail_el
    assert detail.inner_page_element is inner_page_el


def test_detail_node_element_fields_default_to_none():
    detail = DetailNode(identity="d", attrib={})
    assert detail.element is None
    assert detail.inner_page_element is None


def test_column_node_element_defaults_to_none_and_can_be_set():
    col = ColumnNode(identity="c", attrib={})
    assert col.element is None
    el = etree.fromstring("<ColumnPresentation fieldName='c'/>")
    col2 = ColumnNode(identity="c", attrib={}, element=el)
    assert col2.element is el


def test_event_node_element_defaults_to_none_and_can_be_set():
    event = EventNode(identity="e", tag_name="OnRowProcess", side="S", text="")
    assert event.element is None
    el = etree.fromstring("<OnRowProcess>echo 1;</OnRowProcess>")
    event2 = EventNode(identity="e", tag_name="OnRowProcess", side="S", text="", element=el)
    assert event2.element is el


def test_project_model_tree_defaults_to_none_and_can_be_set():
    project = ProjectModel(pages=[])
    assert project.tree is None
    tree = etree.ElementTree(etree.fromstring("<Project/>"))
    project2 = ProjectModel(pages=[], tree=tree)
    assert project2.tree is tree


def test_detail_node_inner_sourceline_defaults_to_none():
    detail = DetailNode(identity="x", attrib={}, sourceline=10)
    assert detail.inner_sourceline is None


def test_detail_node_inner_sourceline_can_be_set():
    detail = DetailNode(identity="x", attrib={}, sourceline=10, inner_sourceline=25)
    assert detail.sourceline == 10
    assert detail.inner_sourceline == 25


from pgtp_editor.model.nodes import ChildElement, ColumnNode


def test_child_element_holds_attrib_sourceline_element():
    child = ChildElement(attrib={"type": "number"}, sourceline=42, element=None)
    assert child.attrib == {"type": "number"}
    assert child.sourceline == 42
    assert child.element is None


def test_child_element_defaults_sourceline_and_element_to_none():
    child = ChildElement(attrib={"type": "text"})
    assert child.sourceline is None
    assert child.element is None


def test_column_node_sub_element_fields_default_to_none():
    col = ColumnNode(identity="tag", attrib={"fieldName": "tag"})
    assert col.format is None
    assert col.lookup is None
    assert col.view_properties is None
    assert col.edit_properties is None


def test_column_node_accepts_sub_element_fields():
    fmt = ChildElement(attrib={"type": "number", "decimalSeparator": "."})
    edit = ChildElement(attrib={"type": "textBox", "placeholder": "Hi"})
    col = ColumnNode(
        identity="tag",
        attrib={"fieldName": "tag"},
        format=fmt,
        edit_properties=edit,
    )
    assert col.format is fmt
    assert col.edit_properties is edit
    # placeholder is reached through edit_properties.attrib, no dedicated field:
    assert col.edit_properties.attrib.get("placeholder") == "Hi"
    assert col.lookup is None
    assert col.view_properties is None
