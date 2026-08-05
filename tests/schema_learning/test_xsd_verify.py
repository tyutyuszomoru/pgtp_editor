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


def test_duplicate_attribute_name_in_same_complex_type_flagged():
    """BUG-002: a duplicate xs:attribute name= within one complexType (e.g.
    from copy-pasting a sibling *AbilityMode block) silently overwrote the
    first definition with no diagnostic. Verify must now catch it."""
    text = _wrap(
        '  <xs:complexType name="T">\n'
        '    <xs:attribute name="a" use="optional">\n'
        '      <xs:simpleType><xs:restriction base="xs:integer">\n'
        '        <xs:enumeration value="1" label="First"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        '    <xs:attribute name="a" use="optional"/>\n'
        "  </xs:complexType>"
    )
    issues = verify_curated(text)
    messages = [i.message for i in issues]
    assert any("duplicate attribute name 'a'" in m for m in messages)
    # Reported at the SECOND (overwriting) occurrence's line, not the first.
    dup = next(i for i in issues if "duplicate attribute name" in i.message)
    second_line = text.splitlines().index('    <xs:attribute name="a" use="optional"/>') + 1
    assert dup.line == second_line


def test_same_attribute_name_in_different_complex_types_is_not_flagged():
    """The seen-names set resets per complexType -- the same attribute name
    reused across two different complexTypes (very common in this dialect,
    e.g. every Page-like type has its own 'caption') is not a duplicate."""
    text = _wrap(
        '  <xs:complexType name="T1">\n'
        '    <xs:attribute name="a" use="optional"/>\n'
        "  </xs:complexType>\n"
        '  <xs:complexType name="T2">\n'
        '    <xs:attribute name="a" use="optional"/>\n'
        "  </xs:complexType>"
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "duplicate attribute name" not in messages


def test_duplicate_attribute_name_does_not_suppress_per_occurrence_sums_checks():
    """The new duplicate-attribute-name check must be purely additive: each
    occurrence of the duplicated xs:attribute is still its own independent
    xs:attribute element as far as the parser/checker's start/end pair is
    concerned, so the existing sums-specific checks (missing labels, over
    SUMS_MAX_ATOMS) must still fire per-occurrence, attributed to each
    occurrence's own line, alongside the new duplicate-name issue."""
    text = _wrap(
        '  <xs:complexType name="T">\n'
        '    <xs:attribute name="a" sums="true">\n'  # line 3: unlabeled sums attr
        "      <xs:simpleType><xs:restriction base=\"xs:integer\">\n"
        '        <xs:enumeration value="1"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        '    <xs:attribute name="a" sums="true">\n'  # line 8: duplicate name, ALSO unlabeled
        "      <xs:simpleType><xs:restriction base=\"xs:integer\">\n"
        '        <xs:enumeration value="2"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    issues = verify_curated(text)
    lines = text.splitlines()
    first_line = lines.index('    <xs:attribute name="a" sums="true">') + 1
    second_line = (
        len(lines[:first_line])
        + lines[first_line:].index('    <xs:attribute name="a" sums="true">')
        + 1
    )
    assert first_line != second_line

    dup_issues = [i for i in issues if "duplicate attribute name 'a'" in i.message]
    assert len(dup_issues) == 1
    assert dup_issues[0].line == second_line  # reported at the overwriting occurrence

    sums_issues = [i for i in issues if "sums attribute has no labeled atomic values" in i.message]
    # Both occurrences are still independently unlabeled sums attributes --
    # the duplicate-name bookkeeping must not have swallowed either check.
    assert {i.line for i in sums_issues} == {first_line, second_line}


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


def test_hint_misplaced_off_attribute_is_flagged():
    text = _wrap(
        '  <xs:complexType name="T" hint="wrong">\n'
        '    <xs:attribute name="a" hint="a file path"/>\n'
        "  </xs:complexType>"
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "hint=" in messages
    assert "not on complexType" in messages


def test_sums_attribute_with_no_labeled_values_is_flagged():
    text = _wrap(
        '  <xs:complexType name="T">\n'
        '    <xs:attribute name="a" sums="true">\n'
        "      <xs:simpleType><xs:restriction base=\"xs:integer\">\n"
        '        <xs:enumeration value="1"/>\n'
        '        <xs:enumeration value="2"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "sums attribute has no labeled atomic values" in messages


def test_sums_attribute_with_a_labeled_value_is_not_flagged():
    text = _wrap(
        '  <xs:complexType name="T">\n'
        '    <xs:attribute name="a" sums="true">\n'
        "      <xs:simpleType><xs:restriction base=\"xs:integer\">\n"
        '        <xs:enumeration value="1" label="A"/>\n'
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "no labeled atomic values" not in messages


def test_sums_attribute_over_cap_is_flagged():
    enums = "\n".join(
        f'        <xs:enumeration value="{i}" label="L{i}"/>' for i in range(17)
    )
    text = _wrap(
        '  <xs:complexType name="T">\n'
        '    <xs:attribute name="a" sums="true">\n'
        "      <xs:simpleType><xs:restriction base=\"xs:integer\">\n"
        f"{enums}\n"
        "      </xs:restriction></xs:simpleType>\n"
        "    </xs:attribute>\n"
        "  </xs:complexType>"
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "sums attribute has too many values for derivation (17 > 16)" in messages


def test_inline_unnamed_complex_type_is_flagged():
    text = _wrap(
        '  <xs:element name="Root" type="Root_Type"/>\n'
        '  <xs:complexType name="Root_Type">\n'
        '    <xs:element name="Child">\n'
        '      <xs:complexType>\n'
        '        <xs:attribute name="inner"/>\n'
        '      </xs:complexType>\n'
        '    </xs:element>\n'
        '  </xs:complexType>'
    )
    messages = " | ".join(i.message for i in verify_curated(text))
    assert "inline (unnamed) complexType is not part of the dialect" in messages


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
