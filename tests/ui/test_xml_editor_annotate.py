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

from pgtp_editor.ui.xml_editor import (
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
