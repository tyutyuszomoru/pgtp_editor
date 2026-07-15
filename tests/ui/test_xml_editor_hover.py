"""Phase 3 — editor value-hover: the pure position→(tag_chain, attr)
resolver and the XmlEditor hint wiring (via a synthetic schema model)."""
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.ui.xml_editor import XmlEditor, attribute_at_position


# --- attribute_at_position (pure) -----------------------------------------


def test_cursor_on_attr_name():
    text = '<Page editFormMode="1"></Page>'
    pos = text.index("editFormMode") + 2
    assert attribute_at_position(text, pos) == ("Page", "editFormMode")


def test_cursor_on_attr_value():
    text = '<Page editFormMode="1"></Page>'
    pos = text.index('"1"') + 1
    assert attribute_at_position(text, pos) == ("Page", "editFormMode")


def test_cursor_outside_any_tag_returns_none():
    text = "<Page>hello world</Page>"
    pos = text.index("hello") + 1
    assert attribute_at_position(text, pos) is None


def test_cursor_inside_close_tag_returns_none():
    text = '<Page editFormMode="1"></Page>'
    pos = text.index("</Page>") + 3
    assert attribute_at_position(text, pos) is None


def test_cursor_on_tag_name_returns_none():
    text = '<Page editFormMode="1"></Page>'
    pos = text.index("Page") + 1  # on the tag name itself
    assert attribute_at_position(text, pos) is None


def test_nested_elements_produce_correct_chain():
    text = (
        "<PGTPProject>\n"
        "  <Pages>\n"
        "    <Page>\n"
        '      <Editor editFormMode="1"></Editor>\n'
        "    </Page>\n"
        "  </Pages>\n"
        "</PGTPProject>\n"
    )
    pos = text.index("editFormMode") + 2
    assert attribute_at_position(text, pos) == (
        "PGTPProject/Pages/Page/Editor",
        "editFormMode",
    )


def test_self_closing_sibling_does_not_corrupt_stack():
    text = (
        "<Root>\n"
        '  <Break kind="x"/>\n'
        '  <Node setting="2"></Node>\n'
        "</Root>\n"
    )
    pos = text.index("setting") + 2
    assert attribute_at_position(text, pos) == ("Root/Node", "setting")


def test_value_containing_gt_inside_quotes():
    text = '<Node expr="a > b" other="2"></Node>'
    pos = text.index("other") + 1
    assert attribute_at_position(text, pos) == ("Node", "other")


def test_cursor_in_gap_between_attrs_returns_none():
    text = '<Node a="1"  b="2"></Node>'
    # position on the double space between attributes
    pos = text.index('"1"') + 4
    assert attribute_at_position(text, pos) is None


def test_self_closing_tag_own_attribute():
    text = '<Root>\n  <Node setting="2"/>\n</Root>'
    pos = text.index("setting") + 2
    assert attribute_at_position(text, pos) == ("Root/Node", "setting")


def test_cursor_past_end_returns_none():
    text = "<Page></Page>"
    assert attribute_at_position(text, len(text) + 5) is None


# --- XmlEditor wiring (_hint_for_help_pos + set_schema_model) --------------


def _model_setting(tag_chain, attr, values, labels, kind="setting"):
    model = Model()
    entry = {
        "type": "integer",
        "values": values,
        "overflowed": False,
        "attr_seen_count": len(values) if values else 0,
        "labels": labels,
        "kind": kind,
    }
    model.paths[tag_chain] = {
        "attributes": {attr: entry},
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def test_hint_for_help_pos_returns_none_without_model(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page editFormMode="1"></Page>'
    editor.setPlainText(text)
    pos = text.index("editFormMode") + 2
    assert editor._hint_for_help_pos(pos) is None


def test_hint_for_help_pos_returns_hint_for_setting(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page editFormMode="1"></Page>'
    editor.setPlainText(text)
    model = _model_setting(
        "Page", "editFormMode", ["1", "2", "3"],
        {"1": "modal", "2": "new page", "3": "inline"},
    )
    editor.set_schema_model(model)
    pos = text.index("editFormMode") + 2
    assert (
        editor._hint_for_help_pos(pos)
        == "editFormMode — 1 = modal · 2 = new page · 3 = inline"
    )


def test_hint_for_help_pos_none_for_content_attr(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page caption="Hi"></Page>'
    editor.setPlainText(text)
    model = _model_setting("Page", "caption", ["Hi"], {}, kind="content")
    editor.set_schema_model(model)
    pos = text.index("caption") + 2
    assert editor._hint_for_help_pos(pos) is None


def test_hint_for_help_pos_none_outside_attr(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page editFormMode="1">body</Page>'
    editor.setPlainText(text)
    model = _model_setting("Page", "editFormMode", ["1"], {"1": "modal"})
    editor.set_schema_model(model)
    pos = text.index("body") + 1
    assert editor._hint_for_help_pos(pos) is None


def test_set_schema_model_default_none(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    assert editor._schema_model is None
