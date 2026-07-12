import defusedxml.ElementTree as ET

from pgtp_editor.schema_learning.parser import walk_element, walk_document


def test_walk_single_element_yields_its_own_path_and_attrib():
    root = ET.fromstring('<Root a="1" b="2"/>')
    events = list(walk_element(root, root.tag))

    assert events == [("Root", {"a": "1", "b": "2"}, {}, False)]


def test_walk_nested_elements_builds_full_paths():
    root = ET.fromstring('<Root><Child x="1"/><Child x="2"/></Root>')
    events = list(walk_element(root, root.tag))

    paths = [e[0] for e in events]
    assert paths == ["Root", "Root/Child", "Root/Child"]
    assert events[0][2] == {"Child": 2}
    assert events[1][1] == {"x": "1"}
    assert events[2][1] == {"x": "2"}


def test_walk_grandchild_path_includes_full_ancestry():
    root = ET.fromstring("<A><B><C/></B></A>")
    events = list(walk_element(root, root.tag))

    paths = [e[0] for e in events]
    assert paths == ["A", "A/B", "A/B/C"]


def test_walk_detects_meaningful_text():
    root = ET.fromstring("<Root>hello</Root>")
    events = list(walk_element(root, root.tag))

    assert events[0][3] is True


def test_walk_ignores_whitespace_only_text():
    root = ET.fromstring("<Root>\n  <Child/>\n</Root>")
    events = list(walk_element(root, root.tag))

    assert events[0][3] is False


def test_walk_document_parses_from_file(tmp_path):
    xml_path = tmp_path / "sample.xml"
    xml_path.write_text('<Root a="1"><Child/></Root>', encoding="utf-8")

    events = list(walk_document(str(xml_path)))

    assert events[0][0] == "Root"
    assert events[1][0] == "Root/Child"


def test_walk_document_strips_cesu8_surrogate_pairs(tmp_path):
    # CESU-8 mis-encoded surrogate pair (as could appear in a malformed
    # real-world .pgtp file's free-text content) must be stripped rather
    # than raising a not-well-formed-XML error.
    xml_path = tmp_path / "cesu8.xml"
    surrogate_pair_bytes = b"\xed\xa0\xbd\xed\xb8\x80"  # mis-encoded U+1F600
    data = b'<Root a="1">before' + surrogate_pair_bytes + b"after</Root>"
    xml_path.write_bytes(data)

    events = list(walk_document(str(xml_path)))

    assert events[0][0] == "Root"
    assert events[0][3] is True
