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


def _scalar_for(base: str | None) -> str:
    """Map a restriction base to our scalar type, prefix-agnostic. Tries an
    exact match first, then falls back to matching the base's LOCAL part
    (mirrors _local()) so e.g. ``xsd:integer`` (a non-``xs:`` prefix) still
    maps to ``integer`` instead of silently falling back to ``string``."""
    if not base:
        return "string"
    if base in _XSD_TO_SCALAR:
        return _XSD_TO_SCALAR[base]
    return _XSD_TO_SCALAR.get(f"xs:{_local(base)}", "string")


class _Collector:
    def __init__(self, parser):
        self._parser = parser
        self.roots: list[tuple[str, str]] = []   # (element name, type name)
        self.types: dict[str, dict] = {}          # type name -> record
        self._stack: list[str] = []               # local names
        # Stack of currently-open complexType frames, one entry per
        # xs:complexType start tag: the record for a named complexType, or
        # None for an anonymous (unnamed) one. Pushing a frame (rather than
        # just leaving the enclosing type in place) for the anonymous case
        # means attributes declared INSIDE it land nowhere — they don't leak
        # into the enclosing named type — while attributes declared AFTER it
        # closes correctly see the enclosing named type again, since popping
        # the anonymous frame restores it as the new stack top.
        self._type_stack: list[dict | None] = []
        self._current_attr: dict | None = None

    @property
    def _current_type(self) -> dict | None:
        return self._type_stack[-1] if self._type_stack else None

    def start(self, tag, attrs):
        local = _local(tag)
        parent = self._stack[-1] if self._stack else None
        self._stack.append(local)
        line = self._parser.CurrentLineNumber
        if local == "complexType":
            name = attrs.get("name")
            if name:
                record = {"line": line, "children": [], "attributes": {}}
                self.types[name] = record
                self._type_stack.append(record)
            else:
                self._type_stack.append(None)
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
            self._type_stack.pop()


def load_curated(text: str) -> CuratedSchema:
    parser = expat.ParserCreate()

    def _forbid_dtd(*_args):
        raise XsdLoadError(
            f"line {parser.CurrentLineNumber}: DTD declarations are not allowed "
            "in the curated XSD"
        )

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
            "type": _scalar_for(attr["base"]),
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
