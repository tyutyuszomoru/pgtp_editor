import defusedxml.ElementTree as ET

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.xsd_gen import _type_name, generate_xsd


def _build_sample_model():
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {"Child": 1}, False)
    model.merge_element("Root", {"mode": "2"}, {"Child": 1}, False)
    model.merge_element("Root/Child", {"name": "x"}, {}, False)
    model.merge_element("Root/Child", {"name": "y"}, {}, False)
    return model


def test_generated_xsd_is_well_formed_xml():
    model = _build_sample_model()
    xsd_text = generate_xsd(model)

    ET.fromstring(xsd_text)  # raises if malformed


def test_generated_xsd_declares_root_element():
    model = _build_sample_model()
    xsd_text = generate_xsd(model)

    assert '<xs:element name="Root" type="Root_Type"/>' in xsd_text


def test_generated_xsd_includes_enumeration_for_small_value_set():
    model = _build_sample_model()
    xsd_text = generate_xsd(model)

    assert '<xs:enumeration value="1"/>' in xsd_text
    assert '<xs:enumeration value="2"/>' in xsd_text


def test_generated_xsd_declares_child_element_with_type_ref():
    model = _build_sample_model()
    xsd_text = generate_xsd(model)

    assert 'name="Child" type="Root_Child_Type"' in xsd_text


def test_generated_xsd_marks_overflowed_attribute_as_plain_type():
    model = Model()
    for i in range(11):
        model.merge_element("Root", {"free": str(i)}, {}, False)

    xsd_text = generate_xsd(model)
    assert '<xs:attribute name="free" type="xs:integer" use="required"/>' in xsd_text
    assert "xs:enumeration" not in xsd_text


def test_generated_xsd_marks_optional_attribute():
    model = Model()
    model.merge_element("Root", {"a": "1"}, {}, False)
    model.merge_element("Root", {}, {}, False)

    xsd_text = generate_xsd(model)
    assert 'use="optional"' in xsd_text


def test_generated_xsd_uses_unbounded_for_repeated_children():
    model = Model()
    model.merge_element("Root", {}, {"Item": 3}, False)
    model.merge_element("Root/Item", {}, {}, False)

    xsd_text = generate_xsd(model)
    assert 'maxOccurs="unbounded"' in xsd_text


def test_generated_xsd_marks_mixed_content():
    model = Model()
    model.merge_element("Root", {}, {}, True)

    xsd_text = generate_xsd(model)
    assert 'mixed="true"' in xsd_text


def test_type_name_for_simple_paths_without_underscores():
    assert _type_name("Root") == "Root_Type"
    assert _type_name("Root/Child") == "Root_Child_Type"


def test_type_name_escapes_literal_underscores_to_avoid_collision():
    assert _type_name("A_B/C") == "A__B_C_Type"
    assert _type_name("A/B_C") == "A_B__C_Type"
    assert _type_name("A_B/C") != _type_name("A/B_C")


def test_generate_xsd_does_not_collide_type_names_for_underscore_paths():
    model = Model()
    model.merge_element("A_B/C", {}, {}, False)
    model.merge_element("A/B_C", {}, {}, False)

    xsd_text = generate_xsd(model)

    name1 = _type_name("A_B/C")
    name2 = _type_name("A/B_C")
    assert name1 != name2
    assert f'<xs:complexType name="{name1}"' in xsd_text
    assert f'<xs:complexType name="{name2}"' in xsd_text


# --- xs:documentation emission: new tests for this sub-project ---


def test_labeled_enum_value_emits_documentation_while_unlabeled_stays_plain():
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {}, False)
    model.merge_element("Root", {"mode": "2"}, {}, False)
    model.paths["Root"]["attributes"]["mode"]["labels"]["1"] = "Full export"

    xsd_text = generate_xsd(model)

    assert (
        '<xs:enumeration value="1">\n'
        "            <xs:annotation>\n"
        "              <xs:documentation>Full export</xs:documentation>\n"
        "            </xs:annotation>\n"
        "          </xs:enumeration>"
    ) in xsd_text
    assert '<xs:enumeration value="2"/>' in xsd_text
    ET.fromstring(xsd_text)  # still well-formed XML


def test_missing_labels_key_does_not_raise_key_error():
    # Simulates a schema_model.json written before this sub-project existed:
    # no "labels" key at all on the attribute entry.
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {}, False)
    del model.paths["Root"]["attributes"]["mode"]["labels"]

    xsd_text = generate_xsd(model)

    assert '<xs:enumeration value="1"/>' in xsd_text


def test_empty_string_label_is_treated_as_no_label():
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {}, False)
    model.paths["Root"]["attributes"]["mode"]["labels"]["1"] = ""

    xsd_text = generate_xsd(model)

    assert '<xs:enumeration value="1"/>' in xsd_text
    assert "xs:documentation" not in xsd_text


def test_label_with_xml_special_characters_is_escaped():
    model = Model()
    model.merge_element("Root", {"mode": "1"}, {}, False)
    model.paths["Root"]["attributes"]["mode"]["labels"]["1"] = "A & B < C"

    xsd_text = generate_xsd(model)

    assert "<xs:documentation>A &amp; B &lt; C</xs:documentation>" in xsd_text
    ET.fromstring(xsd_text)  # must remain well-formed XML despite the raw label text
