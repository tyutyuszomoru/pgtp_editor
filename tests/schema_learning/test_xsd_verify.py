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

from pgtp_editor.schema_learning.xsd_verify import Issue, verify_curated


def _wrap(body):
    return (
        '<?xml version="1.0"?>\n'
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
        f"{body}\n</xs:schema>\n"
    )


def test_clean_dialect_has_no_issues():
    text = _wrap(
        '  <xs:element name="Root" type="Root_Type"/>\n'
        '  <xs:complexType name="Root_Type">\n'
        '    <xs:attribute name="a" use="optional" sums="true">\n'
        '      <xs:simpleType><xs:restriction base="xs:integer">\n'
        '        <xs:enumeration value="1" label="A"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    assert verify_curated(text) == []


def test_malformed_is_single_fatal_issue():
    issues = verify_curated("<broken")
    assert len(issues) == 1 and issues[0].fatal


def test_duplicate_enum_values_flagged():
    text = _wrap(
        '  <xs:complexType name="T">\n'
        '    <xs:attribute name="a">\n'
        "      <xs:simpleType><xs:restriction base=\"xs:integer\">\n"
        '        <xs:enumeration value="1"/>\n'
        '        <xs:enumeration value="1"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    assert any("duplicate enumeration value" in i.message for i in verify_curated(text))


def test_misplaced_dialect_attributes_and_bad_base():
    text = _wrap(
        '  <xs:complexType name="T" label="wrong">\n'
        '    <xs:attribute name="a" >\n'
        '      <xs:simpleType><xs:restriction base="xs:unknown">\n'
        '        <xs:enumeration value="1" sums="true"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "label" in messages          # label on non-enumeration
    assert "sums" in messages           # sums off xs:attribute
    assert "unknown base type" in messages


def test_unresolved_child_type_and_duplicate_type_names():
    text = _wrap(
        '  <xs:element name="Root" type="Missing_Type"/>\n'
        '  <xs:complexType name="T"/>\n'
        '  <xs:complexType name="T"/>'
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "unresolved type reference" in messages
    assert "duplicate type name" in messages


def test_issues_are_sorted_by_line():
    text = _wrap(
        '  <xs:complexType name="T" label="wrong">\n'
        '    <xs:attribute name="a" sums="true"/>\n'
        '  </xs:complexType>\n'
        '  <xs:complexType name="U" label="also-wrong"/>'
    )
    issues = verify_curated(text)
    lines = [issue.line for issue in issues]
    assert lines == sorted(lines)


def test_known_base_with_different_prefix_is_lenient():
    text = (
        '<?xml version="1.0"?>\n'
        '<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
        '  <xsd:complexType name="T">\n'
        '    <xsd:attribute name="a">\n'
        '      <xsd:simpleType><xsd:restriction base="xsd:integer">\n'
        '        <xsd:enumeration value="1"/>\n'
        "      </xsd:restriction></xsd:simpleType>\n"
        "    </xsd:attribute>\n"
        "  </xsd:complexType>\n"
        "</xsd:schema>\n"
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "unknown base type" not in messages
