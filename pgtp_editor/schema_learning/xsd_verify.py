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

"""Dialect verifier for the curated XSD (spec §11): OUR rules, not W3C
schema-for-schemas validity. Streaming expat pass collecting Issues with
1-based line numbers."""
from __future__ import annotations

from dataclasses import dataclass
from xml.parsers import expat

from .settings_index import SUMS_MAX_ATOMS

_KNOWN_BASES = {"xs:boolean", "xs:integer", "xs:decimal", "xs:string"}
_KNOWN_BASE_LOCALS = {base.split(":", 1)[1] for base in _KNOWN_BASES}


@dataclass
class Issue:
    line: int
    message: str
    fatal: bool = False


def _local(tag):
    return tag.rsplit(":", 1)[-1]


class _Checker:
    def __init__(self, parser):
        self._parser = parser
        self.issues: list[Issue] = []
        self._enum_values_seen: set[str] | None = None   # per open xs:attribute
        self._type_names: dict[str, int] = {}
        self._type_refs: list[tuple[str, int]] = []
        # Per-open xs:attribute bookkeeping for the sums-specific rules:
        # is this attribute marked sums="true", does it carry any labeled
        # enumeration value, how many enumeration values does it have, and
        # at what line did it start (for reporting).
        self._attr_is_sums = False
        self._attr_has_label = False
        self._attr_enum_count = 0
        self._attr_line = 0

    def start(self, tag, attrs):
        local = _local(tag)
        line = self._parser.CurrentLineNumber
        if "label" in attrs and local != "enumeration":
            self.issues.append(Issue(line, f"label=\"…\" belongs on xs:enumeration, not on {local}"))
        if "sums" in attrs and local != "attribute":
            self.issues.append(Issue(line, f"sums=\"true\" belongs on xs:attribute, not on {local}"))
        if "hint" in attrs and local != "attribute":
            self.issues.append(Issue(line, f"hint=\"…\" belongs on xs:attribute, not on {local}"))
        if local == "complexType":
            name = attrs.get("name")
            if name:
                if name in self._type_names:
                    self.issues.append(Issue(line, f"duplicate type name '{name}'"))
                else:
                    self._type_names[name] = line
            else:
                self.issues.append(Issue(line, "inline (unnamed) complexType is not part of the dialect"))
        elif local == "element":
            type_name = attrs.get("type")
            if type_name:
                self._type_refs.append((type_name, line))
        elif local == "attribute":
            self._enum_values_seen = set()
            self._attr_is_sums = attrs.get("sums") == "true"
            self._attr_has_label = False
            self._attr_enum_count = 0
            self._attr_line = line
        elif local == "restriction":
            base = attrs.get("base")
            if base and base not in _KNOWN_BASES and _local(base) not in _KNOWN_BASE_LOCALS:
                self.issues.append(Issue(line, f"unknown base type '{base}'"))
        elif local == "enumeration" and self._enum_values_seen is not None:
            value = attrs.get("value", "")
            if value in self._enum_values_seen:
                self.issues.append(Issue(line, f"duplicate enumeration value '{value}'"))
            self._enum_values_seen.add(value)
            self._attr_enum_count += 1
            if "label" in attrs:
                self._attr_has_label = True

    def end(self, tag):
        if _local(tag) == "attribute":
            if self._attr_is_sums and not self._attr_has_label:
                self.issues.append(
                    Issue(self._attr_line, "sums attribute has no labeled atomic values")
                )
            if self._attr_is_sums and self._attr_enum_count > SUMS_MAX_ATOMS:
                self.issues.append(
                    Issue(
                        self._attr_line,
                        "sums attribute has too many values for derivation "
                        f"({self._attr_enum_count} > {SUMS_MAX_ATOMS})",
                    )
                )
            self._enum_values_seen = None
            self._attr_is_sums = False
            self._attr_has_label = False
            self._attr_enum_count = 0

    def finish(self):
        for type_name, line in self._type_refs:
            if type_name not in self._type_names:
                self.issues.append(Issue(line, f"unresolved type reference '{type_name}'"))
        self.issues.sort(key=lambda issue: issue.line)
        return self.issues


def verify_curated(text: str) -> list[Issue]:
    parser = expat.ParserCreate()
    checker = _Checker(parser)

    def _forbid_dtd(*_args):
        raise expat.ExpatError("DTD declarations are not allowed")

    parser.StartDoctypeDeclHandler = _forbid_dtd
    parser.StartElementHandler = checker.start
    parser.EndElementHandler = checker.end
    try:
        parser.Parse(text, True)
    except expat.ExpatError as exc:
        lineno = getattr(exc, "lineno", parser.CurrentLineNumber) or 1
        return [Issue(lineno, f"XML error: {exc}", fatal=True)]
    return checker.finish()
