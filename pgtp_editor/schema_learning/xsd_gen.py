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

from .settings_index import effective_labels

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
    return _generate(model, _attribute_lines)


def generate_curated_xsd(model):
    """Bootstrap emit mode (spec §11): labels ride as label="…" attributes on
    xs:enumeration — our curated dialect — instead of xs:documentation. Used
    exactly once, to seed curated.xsd from the learned model."""
    return _generate(model, _curated_attribute_lines)


def _generate(model, attribute_lines_fn):
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
        lines.extend(_complex_type_lines(path, model.paths[path], attribute_lines_fn))

    lines.append("</xs:schema>")
    return "\n".join(lines) + "\n"


def _complex_type_lines(path, entry, attribute_lines_fn):
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
        lines.extend(attribute_lines_fn(entry, attr_name))

    lines.append("  </xs:complexType>")
    return lines


def _documentation_text(label, note):
    if label and note:
        return f"{label} — {note}"
    return label or note or None


def _curated_attribute_lines(entry, attr_name):
    """Emit xs:enumeration with label="…" attributes (no xs:documentation)."""
    attr_entry = entry["attributes"][attr_name]
    required = attr_entry["attr_seen_count"] == entry["instance_count"]
    use = "required" if required else "optional"
    base_type = _XSD_BASE[attr_entry["type"]]
    universe = sorted(
        set(attr_entry.get("values") or []) | set(attr_entry.get("labels") or {})
    )
    if not attr_entry["overflowed"] and universe:
        labels = effective_labels(attr_entry)
        lines = [f"    <xs:attribute name={quoteattr(attr_name)} use={quoteattr(use)}>"]
        lines.append("      <xs:simpleType>")
        lines.append(f"        <xs:restriction base={quoteattr(base_type)}>")
        for value in universe:
            label = labels.get(value)
            if label:
                lines.append(
                    f"          <xs:enumeration value={quoteattr(value)} "
                    f"label={quoteattr(label)}/>"
                )
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


def _attribute_lines(entry, attr_name):
    attr_entry = entry["attributes"][attr_name]
    required = attr_entry["attr_seen_count"] == entry["instance_count"]
    use = "required" if required else "optional"
    base_type = _XSD_BASE[attr_entry["type"]]

    universe = sorted(
        set(attr_entry.get("values") or []) | set(attr_entry.get("labels") or {})
    )
    if not attr_entry["overflowed"] and universe:
        labels = effective_labels(attr_entry)
        notes = attr_entry.get("notes") or {}
        lines = [f"    <xs:attribute name={quoteattr(attr_name)} use={quoteattr(use)}>"]
        lines.append("      <xs:simpleType>")
        lines.append(f"        <xs:restriction base={quoteattr(base_type)}>")
        for value in universe:
            doc = _documentation_text(labels.get(value), notes.get(value))
            if doc:
                lines.append(f"          <xs:enumeration value={quoteattr(value)}>")
                lines.append("            <xs:annotation>")
                lines.append(f"              <xs:documentation>{escape(doc)}</xs:documentation>")
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
