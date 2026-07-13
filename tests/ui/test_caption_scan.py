from pgtp_editor.ui.caption_scan import CAPTION_ATTRIBUTES, CaptionEntry, scan_captions


def test_caption_attributes_fixed_order():
    assert CAPTION_ATTRIBUTES == (
        "caption",
        "shortCaption",
        "headerHint",
        "insertFormCaption",
        "groupName",
    )


def test_caption_entry_is_frozen_dataclass():
    entry = CaptionEntry(
        line=2, element_tag="Page", anchor="p1", attribute="caption", value="Hello"
    )
    assert (entry.line, entry.element_tag, entry.anchor, entry.attribute, entry.value) == (
        2,
        "Page",
        "p1",
        "caption",
        "Hello",
    )
    import dataclasses
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.value = "changed"


def test_scan_single_attribute():
    text = '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    entries = scan_captions(text)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.line == 2
    assert entry.element_tag == "Page"
    assert entry.attribute == "caption"
    assert entry.value == "Home"


def test_scan_multi_attribute_line_yields_one_row_per_attribute_in_fixed_order():
    # A single line carrying caption + shortCaption + groupName -> 3 rows,
    # ordered by the fixed CAPTION_ATTRIBUTES order, all on the same line.
    text = (
        "<Root>\n"
        '  <Page groupName="G" caption="C" shortCaption="S" fileName="home"/>\n'
        "</Root>"
    )
    entries = scan_captions(text)
    assert [(e.attribute, e.value, e.line) for e in entries] == [
        ("caption", "C", 2),
        ("shortCaption", "S", 2),
        ("groupName", "G", 2),
    ]


def test_scan_document_order_then_attribute_order():
    text = (
        "<Root>\n"
        '  <Page caption="P1" fileName="a"/>\n'
        '  <Detail caption="D1" shortCaption="D1s" tableName="t"/>\n'
        "</Root>"
    )
    entries = scan_captions(text)
    assert [(e.element_tag, e.attribute, e.line) for e in entries] == [
        ("Page", "caption", 2),
        ("Detail", "caption", 3),
        ("Detail", "shortCaption", 3),
    ]


def test_scan_decodes_entities_from_lxml():
    text = '<Root>\n  <Page caption="A &amp; B &lt;x&gt;"/>\n</Root>'
    entries = scan_captions(text)
    assert entries[0].value == "A & B <x>"


def test_scan_all_five_attributes():
    text = (
        "<Root>\n"
        '  <X caption="c" shortCaption="sc" headerHint="hh" '
        'insertFormCaption="ifc" groupName="gn"/>\n'
        "</Root>"
    )
    entries = scan_captions(text)
    assert [e.attribute for e in entries] == list(CAPTION_ATTRIBUTES)


def test_scan_ignores_non_caption_attributes():
    text = '<Root>\n  <Page fileName="home" tableName="t"/>\n</Root>'
    assert scan_captions(text) == []


def test_scan_malformed_text_returns_empty_list():
    assert scan_captions("<a><b></a>") == []


def test_scan_empty_text_returns_empty_list():
    assert scan_captions("") == []


def test_anchor_prefers_fieldName():
    text = '<Root>\n  <ColumnPresentation caption="C" fieldName="col1" tableName="t"/>\n</Root>'
    assert scan_captions(text)[0].anchor == "col1"


def test_anchor_falls_back_to_fileName_then_tableName_then_tag():
    file_text = '<Root>\n  <Page caption="C" fileName="home"/>\n</Root>'
    assert scan_captions(file_text)[0].anchor == "home"

    table_text = '<Root>\n  <Detail caption="C" tableName="t1"/>\n</Root>'
    assert scan_captions(table_text)[0].anchor == "t1"

    tag_text = '<Root>\n  <MenuGroup caption="C"/>\n</Root>'
    assert scan_captions(tag_text)[0].anchor == "MenuGroup"
