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

import pytest

from pgtp_editor.schema_learning.xsd_load import CuratedSchema, XsdLoadError, load_curated

_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">
  <xs:element name="Root" type="Root_Type"/>
  <xs:complexType name="Root_Type">
    <xs:sequence>
      <xs:element name="Item" type="Root_Item_Type" minOccurs="0" maxOccurs="1"/>
    </xs:sequence>
    <xs:attribute name="localizationFileName" use="required" hint="Path to localization file" type="xs:string"/>
  </xs:complexType>
  <xs:complexType name="Root_Item_Type">
    <xs:attribute name="phpDriver" use="optional">
      <xs:simpleType>
        <xs:restriction base="xs:integer">
          <xs:enumeration value="0" label="pdo"/>
          <xs:enumeration value="1" label="php-psql"/>
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
    <xs:attribute name="printProperties" use="optional" sums="true">
      <xs:simpleType>
        <xs:restriction base="xs:integer">
          <xs:enumeration value="1" label="A"/>
          <xs:enumeration value="2" label="B"/>
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
  </xs:complexType>
</xs:schema>
"""


def test_parses_chains_attributes_labels():
    schema = load_curated(_XSD)
    assert set(schema.model.paths) == {"Root", "Root/Item"}
    php = schema.model.paths["Root/Item"]["attributes"]["phpDriver"]
    assert php["type"] == "integer"
    assert php["values"] == ["0", "1"]
    assert php["labels"] == {"0": "pdo", "1": "php-psql"}
    assert "sums" not in php
    loc = schema.model.paths["Root"]["attributes"]["localizationFileName"]
    assert loc["hint"] == "Path to localization file"
    assert loc["values"] == []
    assert loc["use"] == "required"


def test_sums_flag_and_line_maps():
    schema = load_curated(_XSD)
    pp = schema.model.paths["Root/Item"]["attributes"]["printProperties"]
    assert pp["sums"] is True
    # line maps: the xs:attribute lines and complexType lines (1-based)
    assert schema.attribute_lines[("Root/Item", "phpDriver")] == 11
    assert schema.element_lines["Root/Item"] == 10
    assert ("Root", "localizationFileName") in schema.attribute_lines


def test_malformed_xml_raises_with_line():
    with pytest.raises(XsdLoadError) as excinfo:
        load_curated("<xs:schema><oops</xs:schema>")
    assert "line" in str(excinfo.value)


def test_dtd_is_refused():
    with pytest.raises(XsdLoadError):
        load_curated('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><xs:schema/>')


def test_type_cycle_does_not_hang():
    cyclic = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="A" type="A_Type"/>
  <xs:complexType name="A_Type">
    <xs:sequence><xs:element name="A" type="A_Type"/></xs:sequence>
  </xs:complexType>
</xs:schema>"""
    schema = load_curated(cyclic)
    assert "A" in schema.model.paths
