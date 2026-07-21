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

from xml.sax.saxutils import escape, quoteattr

_XSD_BASE = {
    "boolean": "xs:boolean",
    "integer": "xs:integer",
    "decimal": "xs:decimal",
    "string": "xs:string",
}


def _type_name(path):
    escaped_segments = [segment.replace("_", "__") for segment in path.split("/")]
    return "_".join(escaped_segments) + "_Type"


def generate_xsd(model):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">',
    ]

    root_paths = sorted(p for p in model.paths if "/" not in p)
    for root_path in root_paths:
        lines.append(
            f'  <xs:element name={quoteattr(root_path)} type={quoteattr(_type_name(root_path))}/>'
        )

    for path in sorted(model.paths):
        lines.extend(_complex_type_lines(path, model.paths[path]))

    lines.append("</xs:schema>")
    return "\n".join(lines) + "\n"


def _complex_type_lines(path, entry):
    lines = []
    if not entry["order_stable"]:
        lines.append(
            f"  <!-- WARNING: child order varies across samples for {escape(path)}; "
            f"using first-observed order -->"
        )

    mixed_attr = ' mixed="true"' if entry["has_text"] else ""
    lines.append(f'  <xs:complexType name={quoteattr(_type_name(path))}{mixed_attr}>')

    if entry["order"]:
        lines.append("    <xs:sequence>")
        for tag in entry["order"]:
            child_info = entry["children"][tag]
            min_occurs = "0" if child_info["ever_absent"] else "1"
            max_occurs = "unbounded" if child_info["ever_multiple"] else "1"
            child_type = _type_name(f"{path}/{tag}")
            lines.append(
                f"      <xs:element name={quoteattr(tag)} type={quoteattr(child_type)} "
                f"minOccurs={quoteattr(min_occurs)} maxOccurs={quoteattr(max_occurs)}/>"
            )
        lines.append("    </xs:sequence>")

    for attr_name in sorted(entry["attributes"]):
        lines.extend(_attribute_lines(entry, attr_name))

    lines.append("  </xs:complexType>")
    return lines


def _attribute_lines(entry, attr_name):
    attr_entry = entry["attributes"][attr_name]
    required = attr_entry["attr_seen_count"] == entry["instance_count"]
    use = "required" if required else "optional"
    base_type = _XSD_BASE[attr_entry["type"]]

    if not attr_entry["overflowed"] and attr_entry["values"]:
        lines = [f"    <xs:attribute name={quoteattr(attr_name)} use={quoteattr(use)}>"]
        lines.append("      <xs:simpleType>")
        lines.append(f"        <xs:restriction base={quoteattr(base_type)}>")
        labels = attr_entry.get("labels", {})
        for value in sorted(attr_entry["values"]):
            label = labels.get(value)
            if label:
                lines.append(f"          <xs:enumeration value={quoteattr(value)}>")
                lines.append("            <xs:annotation>")
                lines.append(f"              <xs:documentation>{escape(label)}</xs:documentation>")
                lines.append("            </xs:annotation>")
                lines.append("          </xs:enumeration>")
            else:
                lines.append(f"          <xs:enumeration value={quoteattr(value)}/>")
        lines.append("        </xs:restriction>")
        lines.append("      </xs:simpleType>")
        lines.append("    </xs:attribute>")
        return lines

    return [
        f"    <xs:attribute name={quoteattr(attr_name)} type={quoteattr(base_type)} "
        f"use={quoteattr(use)}/>"
    ]
