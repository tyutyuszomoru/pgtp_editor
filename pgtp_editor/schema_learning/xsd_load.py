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

"""Parse the hand-curated XSD (our dialect: label=/sums=/hint=) into the
in-memory Model shape that settings_index and the editor consume, plus
source-line maps for Go To XSD.

Streaming expat parser (DTDs forbidden — same defensive posture as
defusedxml) so every xs:attribute / xs:complexType records its 1-based
source line. Unknown structures are ignored; Verify (xsd_verify.py) is the
place that complains about dialect violations, not this loader.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from xml.parsers import expat

from .model import Model

_XSD_TO_SCALAR = {
    "xs:boolean": "boolean",
    "xs:integer": "integer",
    "xs:decimal": "decimal",
    "xs:string": "string",
}


class XsdLoadError(Exception):
    pass


@dataclass
class CuratedSchema:
    model: Model
    attribute_lines: dict[tuple[str, str], int] = field(default_factory=dict)
    element_lines: dict[str, int] = field(default_factory=dict)


def _local(tag: str) -> str:
    """'xs:attribute' -> 'attribute' (prefix-agnostic — the user may use any
    namespace prefix in their curated file)."""
    return tag.rsplit(":", 1)[-1]


class _Collector:
    def __init__(self, parser):
        self._parser = parser
        self.roots: list[tuple[str, str]] = []   # (element name, type name)
        self.types: dict[str, dict] = {}          # type name -> record
        self._stack: list[str] = []               # local names
        self._current_type: dict | None = None
        self._current_attr: dict | None = None

    def start(self, tag, attrs):
        local = _local(tag)
        parent = self._stack[-1] if self._stack else None
        self._stack.append(local)
        line = self._parser.CurrentLineNumber
        if local == "complexType" and attrs.get("name"):
            self._current_type = {
                "line": line, "children": [], "attributes": {},
            }
            self.types[attrs["name"]] = self._current_type
        elif local == "element":
            name, type_name = attrs.get("name"), attrs.get("type")
            if name and type_name:
                if parent == "schema":
                    self.roots.append((name, type_name))
                elif self._current_type is not None:
                    self._current_type["children"].append((name, type_name))
        elif local == "attribute" and self._current_type is not None:
            self._current_attr = {
                "name": attrs.get("name", ""),
                "line": line,
                "use": attrs.get("use", "optional"),
                "sums": attrs.get("sums") == "true",
                "hint": attrs.get("hint"),
                "base": attrs.get("type"),
                "values": [],
                "labels": {},
            }
        elif local == "restriction" and self._current_attr is not None:
            self._current_attr["base"] = attrs.get("base")
        elif local == "enumeration" and self._current_attr is not None:
            value = attrs.get("value", "")
            self._current_attr["values"].append(value)
            label = attrs.get("label")
            if label is not None:
                self._current_attr["labels"][value] = label

    def end(self, tag):
        local = _local(tag)
        self._stack.pop()
        if local == "attribute" and self._current_attr is not None:
            attr = self._current_attr
            if attr["name"] and self._current_type is not None:
                self._current_type["attributes"][attr["name"]] = attr
            self._current_attr = None
        elif local == "complexType":
            self._current_type = None


def _forbid_dtd(*_args):
    raise XsdLoadError("DTD declarations are not allowed in the curated XSD")


def load_curated(text: str) -> CuratedSchema:
    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = _forbid_dtd
    collector = _Collector(parser)
    parser.StartElementHandler = collector.start
    parser.EndElementHandler = collector.end
    try:
        parser.Parse(text, True)
    except expat.ExpatError as exc:
        raise XsdLoadError(
            f"line {exc.lineno}: {expat.errors.messages[exc.code]}"
        ) from exc

    schema = CuratedSchema(model=Model())
    for root_name, root_type in collector.roots:
        _walk(schema, collector.types, root_name, root_type, "", set())
    return schema


def _walk(schema, types, tag, type_name, parent_chain, stack):
    record = types.get(type_name)
    if record is None or type_name in stack:
        return
    chain = f"{parent_chain}/{tag}" if parent_chain else tag
    schema.element_lines[chain] = record["line"]
    entry, _is_new = schema.model._get_or_create_path(chain)
    for attr_name, attr in record["attributes"].items():
        model_entry = {
            "type": _XSD_TO_SCALAR.get(attr["base"], "string"),
            "values": list(attr["values"]),
            "overflowed": False,
            "attr_seen_count": 1,
            "labels": dict(attr["labels"]),
            "use": attr["use"],
        }
        if attr["sums"]:
            model_entry["sums"] = True
        if attr["hint"]:
            model_entry["hint"] = attr["hint"]
        entry["attributes"][attr_name] = model_entry
        schema.attribute_lines[(chain, attr_name)] = attr["line"]
    for child_tag, child_type in record["children"]:
        _walk(schema, types, child_tag, child_type, chain, stack | {type_name})
