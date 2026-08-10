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

# pgtp_editor/xmlfmt/config.py
"""The XML indenter's only tunable (§18.4 part C).

The SQL engine's `FormatConfig` (part B) is a rule catalog because SQL layout
is a matter of taste at a dozen independent points. The XML engine has exactly
one degree of freedom -- **how wide one nesting level is** -- because §18.4
part C restricts it to "purely the whitespace that sits between tags":
attribute order, casing, self-closing form, text and entities are all off the
table by rule, so there is nothing else a preference could name.

Kept as a frozen dataclass in its own module anyway, for two reasons:

* it is the same shape part D's `Settings > Autoformatter settings...` dialog
  already has to persist for the SQL side, so the persistence lane needs no
  special case for XML;
* a future second knob (say "collapse blank lines") lands here without
  touching `format_xml_selection`'s signature.

`indent_unit` defaults to **two spaces**, not the SQL engine's four: that is
what `.pgtp` and `.xsd` files in this project are actually written with (§2),
and an indenter whose default disagrees with the corpus would rewrite every
line of every file the first time it is used.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class XmlFormatConfig:
    """Layout preferences for `format_xml_selection`.

    Frozen so a config can be shared freely (module-level default, dialog
    preview, host panel) without any caller being able to mutate another's.
    """

    #: The string emitted once per nesting level. Whitespace by contract --
    #: the engine writes it into inter-tag positions only.
    indent_unit: str = "  "


#: The shipped behaviour, exactly. Callers that do not care pass nothing.
DEFAULT_XML_FORMAT_CONFIG = XmlFormatConfig()
