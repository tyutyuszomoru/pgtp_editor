# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.ui.xml_editor import (
    XmlEditor,
    attribute_at_position,
    attribute_value_at_position,
)

_XML = '<Root><Item mode="4" caption="hi &gt; there"/></Root>'


def test_resolves_value_and_chain_on_value():
    pos = _XML.index('"4"') + 1
    assert attribute_value_at_position(_XML, pos) == ("Root/Item", "mode", "4")


def test_resolves_on_attribute_name_token():
    pos = _XML.index("mode")
    assert attribute_value_at_position(_XML, pos) == ("Root/Item", "mode", "4")


def test_none_outside_opening_tags():
    assert attribute_value_at_position(_XML, _XML.index("</Root>") + 2) is None
    assert attribute_value_at_position(_XML, _XML.index("<Root>") + 1) is None


def test_attribute_at_position_still_returns_pair():
    pos = _XML.index('"4"') + 1
    assert attribute_at_position(_XML, pos) == ("Root/Item", "mode")


def _entry(values, labels=None, **extra):
    entry = {
        "type": "integer",
        "values": values,
        "overflowed": values is None,
        "attr_seen_count": 1,
        "labels": labels or {},
    }
    entry.update(extra)
    return entry


def _model(paths_attrs):
    model = Model()
    model.paths = {
        chain: {
            "attributes": attrs,
            "children": {},
            "instance_count": 1,
            "order": [],
            "order_stable": True,
            "has_text": False,
        }
        for chain, attrs in paths_attrs.items()
    }
    return model


def test_resolves_second_attribute_with_entity_value():
    # The value comes back as the raw quoted text minus quotes — no entity
    # decoding (labels key on the literal document text).
    pos = _XML.index("caption")
    assert attribute_value_at_position(_XML, pos) == (
        "Root/Item", "caption", "hi &gt; there"
    )


def test_resolves_none_in_inter_attribute_gap():
    pos = _XML.index('" caption') + 1  # the space between the two attributes
    assert attribute_value_at_position(_XML, pos) is None


def test_prepare_context_menu_at_moves_caret_to_clicked_value(qtbot):
    # Reproduces the reported bug: caret sits on value "1" (attribute a) but
    # the right-click lands on value "2" (attribute b). The caret used to
    # resolve the context menu must reflect the clicked position, not the
    # stale caret.
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1" b="2"/>')
    editor.set_schema_model(
        _model({"Root": {"a": _entry(["1"]), "b": _entry(["2"])}})
    )
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)

    click_pos = editor.toPlainText().index('"2"') + 1
    editor._prepare_context_menu_at(click_pos)

    assert editor.textCursor().position() == click_pos
    request = attribute_value_at_position(
        editor.toPlainText(), editor.textCursor().position()
    )
    assert request == ("Root", "b", "2")


def test_prepare_context_menu_at_preserves_selection_containing_click(qtbot):
    # Right-clicking inside an existing selection must not collapse it: the
    # "Find" action depends on the selection surviving the right-click.
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1" b="2"/>')
    text = editor.toPlainText()
    sel_start = text.index('"1"') + 1
    sel_end = sel_start + 1  # spans the "1" value

    cursor = editor.textCursor()
    cursor.setPosition(sel_start)
    cursor.setPosition(sel_end, cursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    assert editor.textCursor().selectedText() == "1"

    click_pos = sel_start  # inside the selection
    editor._prepare_context_menu_at(click_pos)

    assert editor.textCursor().selectedText() == "1"
    assert editor.textCursor().selectionStart() == sel_start
    assert editor.textCursor().selectionEnd() == sel_end


def test_request_goto_xsd_emits_chain_and_attr(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1"/>')
    editor.set_schema_model(_model({"Root": {"a": _entry(["1"])}}))
    cursor = editor.textCursor()
    cursor.setPosition(editor.toPlainText().index('"1"') + 1)
    editor.setTextCursor(cursor)
    received = []
    editor.goto_xsd_requested.connect(lambda c, a: received.append((c, a)))
    assert editor.request_goto_xsd() is True
    assert received == [("Root", "a")]


def test_request_goto_xsd_element_only_when_not_on_attribute(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1"/>')
    editor.set_schema_model(_model({"Root": {"a": _entry(["1"])}}))
    cursor = editor.textCursor()
    cursor.setPosition(1)  # on the tag name
    editor.setTextCursor(cursor)
    received = []
    editor.goto_xsd_requested.connect(lambda c, a: received.append((c, a)))
    assert editor.request_goto_xsd() is True
    assert received == [("Root", "")]
