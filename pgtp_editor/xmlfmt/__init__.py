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

"""XML selection indenter core -- the SECOND engine behind `Ctrl+Alt+F` (§18.4 part C).

One gesture, two engines, dispatched by **host surface** and never by
sniffing the selected text: `Ctrl+Alt+F` on the three `XmlEditor` instances
(Raw XML, Edit XSD, the FQ-006 draft fragment tab) answers here, while the SQL
authoring surfaces answer in `pgtp_editor.sql`. A text-sniffing dispatcher
would eventually guess wrong on `<x>select 1</x>`, and a formatter that
guesses is the one thing §18.4 forbids.

Pure and Qt-free (§5's dependency rule): no PySide6, no database, no I/O, and
specifically no `lxml` -- see `scanner.py` for why the already-present XML
parser is the wrong tool for a formatter whose normal input is a fragment.
Guarded by `tests/xmlfmt/test_package_purity.py`, the twin of `sql`'s.

`FormatResult` and `Issue` are **re-exported from `pgtp_editor.sql`, not
re-declared**: the refusal shape belongs to the gesture rather than to the
dialect, and a second `Issue` type would mean a second renderer for one
user-visible behaviour. The dependency runs one way only -- `xmlfmt` imports
`sql`, `sql` never imports `xmlfmt` -- so if a third engine ever appears,
lifting both types into a shared `formatting/` package is a pure refactor.

`.xsd` files are a first-class target, not an incidental one: `.xsd` is XML and
the identical element-depth engine formats it on identical terms.
"""
from __future__ import annotations

from ..sql import FormatResult, Issue
from .config import DEFAULT_XML_FORMAT_CONFIG, XmlFormatConfig
from .formatter import format_xml_selection

__all__ = [
    "DEFAULT_XML_FORMAT_CONFIG",
    "FormatResult",
    "Issue",
    "XmlFormatConfig",
    "format_xml_selection",
]
