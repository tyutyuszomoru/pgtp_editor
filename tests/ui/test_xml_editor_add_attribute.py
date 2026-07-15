"""Phase 4 — offer unused keys: the pure insert_attribute and
enclosing_open_tag transforms plus the XmlEditor context-menu wiring
(driven directly, never via a live popup)."""
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.ui.xml_editor import (
    XmlEditor,
    enclosing_open_tag,
    insert_attribute,
)


# --- insert_attribute (pure) ----------------------------------------------


def test_insert_attribute_before_gt():
    text = '<Page x="1">'
    insert_pos = text.index(">")
    new_text, caret = insert_attribute(text, insert_pos, "y")
    assert new_text == '<Page x="1" y="">'
    # caret sits between the two quotes of y=""
    assert new_text[caret - 1] == '"'
    assert new_text[caret] == '"'
    assert new_text[:caret].endswith('y="')


def test_insert_attribute_before_self_closing_slash():
    text = "<Break/>"
    insert_pos = text.index("/")
    new_text, caret = insert_attribute(text, insert_pos, "kind")
    assert new_text == '<Break kind=""/>'
    assert new_text[caret - 1] == '"'
    assert new_text[caret] == '"'
    assert new_text[:caret].endswith('kind="')


# --- enclosing_open_tag (pure) --------------------------------------------


def test_enclosing_open_tag_on_tag_name():
    text = '<Page x="1"></Page>'
    pos = text.index("Page") + 1
    chain, present, insert_pos = enclosing_open_tag(text, pos)
    assert chain == "Page"
    assert present == {"x"}
    assert text[insert_pos] == ">"


def test_enclosing_open_tag_in_whitespace_before_gt():
    text = '<Page x="1" ></Page>'
    pos = text.index(" >")  # the space just before '>'
    chain, present, insert_pos = enclosing_open_tag(text, pos)
    assert chain == "Page"
    assert present == {"x"}
    assert text[insert_pos] == ">"


def test_enclosing_open_tag_on_existing_attr():
    text = '<Page x="1" y="2"></Page>'
    pos = text.index("y=") + 1
    chain, present, insert_pos = enclosing_open_tag(text, pos)
    assert chain == "Page"
    assert present == {"x", "y"}
    assert text[insert_pos] == ">"


def test_enclosing_open_tag_nested_chain_and_present():
    text = (
        "<PGTPProject>\n"
        "  <Pages>\n"
        "    <Page>\n"
        '      <Editor editFormMode="1" caption="Hi"></Editor>\n'
        "    </Page>\n"
        "  </Pages>\n"
        "</PGTPProject>\n"
    )
    pos = text.index("editFormMode") + 2
    chain, present, insert_pos = enclosing_open_tag(text, pos)
    assert chain == "PGTPProject/Pages/Page/Editor"
    assert present == {"editFormMode", "caption"}
    assert text[insert_pos] == ">"


def test_enclosing_open_tag_self_closing():
    text = '<Root>\n  <Break kind="x"/>\n</Root>'
    pos = text.index("kind") + 1
    chain, present, insert_pos = enclosing_open_tag(text, pos)
    assert chain == "Root/Break"
    assert present == {"kind"}
    assert text[insert_pos] == "/"


def test_enclosing_open_tag_value_containing_gt():
    text = '<Node expr="a > b" other="2"></Node>'
    pos = text.index("Node") + 1
    chain, present, insert_pos = enclosing_open_tag(text, pos)
    assert chain == "Node"
    assert present == {"expr", "other"}
    # insert_pos is the real tag-closing '>' after the quoted value, not the
    # '>' inside the value.
    assert text[insert_pos] == ">"
    assert insert_pos == text.index('"2"') + len('"2"')


def test_enclosing_open_tag_in_text_content_returns_none():
    text = "<Page>hello</Page>"
    pos = text.index("hello") + 1
    assert enclosing_open_tag(text, pos) is None


def test_enclosing_open_tag_in_close_tag_returns_none():
    text = "<Page></Page>"
    pos = text.index("</Page>") + 3
    assert enclosing_open_tag(text, pos) is None


# --- XmlEditor wiring: unused_attributes_at + _insert_attribute -----------


def _model_settings(tag_chain, names):
    model = Model()
    attributes = {}
    for name in names:
        attributes[name] = {
            "type": "integer",
            "values": ["1", "2"],
            "overflowed": False,
            "attr_seen_count": 2,
            "labels": {},
            "kind": "setting",
        }
    model.paths[tag_chain] = {
        "attributes": attributes,
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def test_unused_attributes_at_returns_expected(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page editFormMode="1"></Page>'
    editor.setPlainText(text)
    editor.set_schema_model(
        _model_settings("Page", ["editFormMode", "pageMode", "layout"])
    )
    pos = text.index("Page") + 1
    assert editor.unused_attributes_at(pos) == ["layout", "pageMode"]


def test_unused_attributes_at_none_without_model(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page editFormMode="1"></Page>'
    editor.setPlainText(text)
    pos = text.index("Page") + 1
    assert editor.unused_attributes_at(pos) == []


def test_unused_attributes_at_empty_when_read_only(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page editFormMode="1"></Page>'
    editor.setPlainText(text)
    editor.set_schema_model(_model_settings("Page", ["pageMode"]))
    editor.setReadOnly(True)
    pos = text.index("Page") + 1
    assert editor.unused_attributes_at(pos) == []


def test_unused_attributes_at_empty_outside_tag(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = "<Page>body</Page>"
    editor.setPlainText(text)
    editor.set_schema_model(_model_settings("Page", ["pageMode"]))
    pos = text.index("body") + 1
    assert editor.unused_attributes_at(pos) == []


def test_insert_attribute_applies_and_positions_caret(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page editFormMode="1"></Page>'
    editor.setPlainText(text)
    editor.set_schema_model(_model_settings("Page", ["pageMode"]))
    # put cursor inside the opening tag (on the tag name)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("Page") + 1)
    editor.setTextCursor(cursor)

    editor._insert_attribute("pageMode")

    new_text = editor.toPlainText()
    assert new_text == '<Page editFormMode="1" pageMode=""></Page>'
    caret = editor.textCursor().position()
    assert new_text[caret - 1] == '"'
    assert new_text[caret] == '"'
    assert new_text[:caret].endswith('pageMode="')


def test_insert_attribute_is_undoable(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    text = '<Page editFormMode="1"></Page>'
    editor.setPlainText(text)
    editor.set_schema_model(_model_settings("Page", ["pageMode"]))
    cursor = editor.textCursor()
    cursor.setPosition(text.index("Page") + 1)
    editor.setTextCursor(cursor)

    editor._insert_attribute("pageMode")
    assert "pageMode" in editor.toPlainText()
    editor.undo()
    assert editor.toPlainText() == text
