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
from pgtp_editor.ui import xml_structure
from pgtp_editor.ui.xml_editor import (
    XmlEditor,
    attribute_at_position,
    attribute_value_at_position,
    unlabeled_value_spans,
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


def test_unlabeled_value_spans_finds_only_unlabeled_enum_values():
    text = '<Root mode="1" mode2="2" free="x"/>'
    model = _model({
        "Root": {
            "mode": _entry(["1", "2"], labels={"1": "A"}),   # "1" labeled -> skip
            "mode2": _entry(["2"]),                          # unlabeled -> span
            # "free" not in schema -> skip
        }
    })
    spans = unlabeled_value_spans(text, xml_structure.scan(text), model)
    start = text.index('"2"') + 1
    assert spans == [(start, start + 1)]


def test_unlabeled_value_spans_skips_content_kind():
    text = '<Root caption="Hello"/>'
    model = _model({"Root": {"caption": _entry(["Hello"], kind="content")}})
    assert unlabeled_value_spans(text, xml_structure.scan(text), model) == []


def test_editor_renders_underlines_and_navigates(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1" b="2"/>')
    model = _model({"Root": {"a": _entry(["1"]), "b": _entry(["2"])}})
    editor.set_schema_model(model)
    assert len(editor._unlabeled_value_selections) == 2

    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    assert editor.goto_next_unlabeled_value() is True
    assert editor.textCursor().selectedText() == "1"
    assert editor.goto_next_unlabeled_value() is True
    assert editor.textCursor().selectedText() == "2"
    assert editor.goto_next_unlabeled_value() is True  # wraps
    assert editor.textCursor().selectedText() == "1"


def test_goto_next_unlabeled_returns_false_without_model(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText('<Root a="1"/>')
    assert editor.goto_next_unlabeled_value() is False
