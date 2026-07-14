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


# -- breadcrumb ------------------------------------------------------------


def test_breadcrumb_from_page_detail_ancestors_for_column():
    text = (
        "<Root>\n"
        '  <Page caption="Equipment" fileName="equip">\n'
        '    <Detail caption="Attachments" tableName="att">\n'
        '      <ColumnPresentation caption="WBS" fieldName="wbs_id"/>\n'
        "    </Detail>\n"
        "  </Page>\n"
        "</Root>"
    )
    entries = scan_captions(text)
    column_entry = next(e for e in entries if e.element_tag == "ColumnPresentation")
    assert column_entry.breadcrumb == "Equipment → Attachments → wbs_id"


def test_breadcrumb_falls_back_to_fileName_then_tag():
    text = (
        "<Root>\n"
        '  <Page fileName="equip">\n'
        '    <ColumnPresentation caption="Name" fieldName="name_col"/>\n'
        "  </Page>\n"
        "</Root>"
    )
    entries = scan_captions(text)
    column_entry = next(e for e in entries if e.element_tag == "ColumnPresentation")
    # Page has no caption -> falls back to fileName "equip"; column label is its
    # fieldName.
    assert column_entry.breadcrumb == "equip → name_col"


def test_breadcrumb_top_level_element_is_just_its_own_label():
    text = '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    entry = scan_captions(text)[0]
    # No Page/Detail/OnTheFlyInsertPage ancestor -> breadcrumb is the element's
    # own label (a Page's caption).
    assert entry.breadcrumb == "Home"


def test_breadcrumb_default_empty_on_dataclass():
    entry = CaptionEntry(
        line=2, element_tag="Page", anchor="p1", attribute="caption", value="Hello"
    )
    assert entry.breadcrumb == ""


def test_breadcrumb_detail_inner_page_not_doubled():
    # Real .pgtp shape: a <Detail> wraps an inner <Page> that repeats the same
    # level. The Detail and its immediate inner <Page> must collapse to ONE
    # breadcrumb level (issue #3), so a Page>Detail>Detail>column produces
    # 'Équipement → Équipement\\Sous-article → Activités → col', NOT the doubled
    # 'Équipement → Équipement\\Sous-article → Équipement\\Sous-article → …'.
    text = (
        "<Root>\n"
        '  <Page caption="Équipement" fileName="equip">\n'
        '    <Detail caption="Équipement\\Sous-article" tableName="sub">\n'
        '      <Page fileName="subpage">\n'
        '        <Detail caption="Activités" tableName="act">\n'
        '          <Page fileName="actpage">\n'
        '            <ColumnPresentation caption="Col" fieldName="col"/>\n'
        "          </Page>\n"
        "        </Detail>\n"
        "      </Page>\n"
        "    </Detail>\n"
        "  </Page>\n"
        "</Root>"
    )
    entries = scan_captions(text)
    column_entry = next(e for e in entries if e.element_tag == "ColumnPresentation")
    assert column_entry.breadcrumb == (
        "Équipement → Équipement\\Sous-article → Activités → col"
    )


def test_breadcrumb_captionless_detail_falls_back_to_inner_page_label():
    # A caption-less Detail still shows a meaningful label by falling back to
    # its inner Page's caption/fileName/tableName.
    text = (
        "<Root>\n"
        '  <Page caption="Top" fileName="top">\n'
        '    <Detail tableName="dt">\n'
        '      <Page caption="InnerPageLabel" fileName="inner">\n'
        '        <ColumnPresentation caption="Col" fieldName="col"/>\n'
        "      </Page>\n"
        "    </Detail>\n"
        "  </Page>\n"
        "</Root>"
    )
    entries = scan_captions(text)
    column_entry = next(e for e in entries if e.element_tag == "ColumnPresentation")
    assert column_entry.breadcrumb == "Top → InnerPageLabel → col"


from pgtp_editor.ui.caption_scan import apply_caption_edits
from lxml import etree as _etree


def _entry(line, attribute, element_tag="Page", anchor="a", value=""):
    return CaptionEntry(
        line=line, element_tag=element_tag, anchor=anchor, attribute=attribute, value=value
    )


def test_apply_replaces_single_attribute_value():
    text = '<Root>\n  <Page caption="Old" fileName="home"/>\n</Root>'
    result = apply_caption_edits(text, [(_entry(2, "caption"), "New")])
    assert result == '<Root>\n  <Page caption="New" fileName="home"/>\n</Root>'


def test_apply_empty_edit_set_is_identity():
    text = '<Root>\n  <Page caption="Old"/>\n</Root>'
    assert apply_caption_edits(text, []) == text


def test_apply_preserves_unedited_lines_byte_for_byte():
    text = (
        "<Root>\n"
        '  <Page caption="Old" fileName="home"/>\n'
        '  <Detail caption="Keep" tableName="t"/>\n'
        "</Root>"
    )
    result = apply_caption_edits(text, [(_entry(2, "caption"), "New")])
    lines = result.splitlines(keepends=True)
    original_lines = text.splitlines(keepends=True)
    # Every line except line 2 is byte-identical.
    assert lines[0] == original_lines[0]
    assert lines[2] == original_lines[2]
    assert lines[3] == original_lines[3]
    assert 'caption="New"' in lines[1]


def test_apply_boundary_caption_not_matched_inside_shortCaption():
    # A line with BOTH caption and shortCaption/insertFormCaption: editing
    # `caption` must change ONLY caption, never the tail of the longer names.
    text = (
        "<Root>\n"
        '  <Page insertFormCaption="I" caption="C" shortCaption="S"/>\n'
        "</Root>"
    )
    result = apply_caption_edits(text, [(_entry(2, "caption"), "CHANGED")])
    assert result == (
        "<Root>\n"
        '  <Page insertFormCaption="I" caption="CHANGED" shortCaption="S"/>\n'
        "</Root>"
    )


def test_apply_shortCaption_edit_leaves_caption_untouched():
    text = '<Root>\n  <Page caption="C" shortCaption="S"/>\n</Root>'
    result = apply_caption_edits(text, [(_entry(2, "shortCaption"), "S2")])
    assert result == '<Root>\n  <Page caption="C" shortCaption="S2"/>\n</Root>'


def test_apply_escapes_special_characters_double_quoted():
    text = '<Root>\n  <Page caption="Old"/>\n</Root>'
    result = apply_caption_edits(text, [(_entry(2, "caption"), 'A & B < C > D "q"')])
    # & first, then < > "  -> the raw line contains the escaped form.
    assert 'caption="A &amp; B &lt; C &gt; D &quot;q&quot;"' in result


def test_apply_escaping_round_trips_through_lxml():
    text = '<Root>\n  <Page caption="Old" shortCaption="Keep"/>\n</Root>'
    new_value = 'Tom & Jerry <best> "friends"'
    result = apply_caption_edits(text, [(_entry(2, "caption"), new_value)])
    root = _etree.fromstring(result.encode("utf-8"))
    page = root[0]
    assert page.attrib["caption"] == new_value  # decodes back to the intended string
    assert page.attrib["shortCaption"] == "Keep"  # untouched attribute preserved


def test_apply_multiple_edits_on_same_line():
    text = '<Root>\n  <Page caption="C" shortCaption="S"/>\n</Root>'
    result = apply_caption_edits(
        text,
        [(_entry(2, "caption"), "C2"), (_entry(2, "shortCaption"), "S2")],
    )
    assert result == '<Root>\n  <Page caption="C2" shortCaption="S2"/>\n</Root>'


def test_apply_missing_attribute_on_line_is_skipped_not_crash():
    # Defensive: an edit naming an attribute that isn't on the given line
    # leaves that line unchanged and does not corrupt others.
    text = '<Root>\n  <Page caption="C"/>\n  <Page shortCaption="S"/>\n</Root>'
    result = apply_caption_edits(
        text,
        [
            (_entry(2, "shortCaption"), "WONT_MATCH"),  # line 2 has no shortCaption
            (_entry(3, "shortCaption"), "S2"),
        ],
    )
    assert result == '<Root>\n  <Page caption="C"/>\n  <Page shortCaption="S2"/>\n</Root>'


def test_apply_only_replaces_first_occurrence_on_line():
    # count=1: if the same attribute somehow appears twice on a line, only the
    # first is replaced (matches the scan's single-value read).
    text = '<Root>\n  <Page caption="A" caption="B"/>\n</Root>'
    result = apply_caption_edits(text, [(_entry(2, "caption"), "X")])
    assert result == '<Root>\n  <Page caption="X" caption="B"/>\n</Root>'


# -- Phase 4: find / filter / replace core ---------------------------------

import pytest

from pgtp_editor.ui.caption_scan import (
    SEARCH_MODES,
    apply_find_replace,
    matches,
)


def test_search_modes_constant():
    assert SEARCH_MODES == ("normal", "extended", "regular")


# apply_find_replace -- normal mode

def test_normal_replace_all_occurrences():
    assert apply_find_replace("ababab", "a", "X", "normal", True) == "XbXbXb"


def test_normal_no_match_returns_none():
    assert apply_find_replace("hello", "zzz", "X", "normal", True) is None


def test_normal_case_sensitive_does_not_match_wrong_case():
    assert apply_find_replace("Hello", "hello", "X", "normal", True) is None


def test_normal_case_insensitive_matches_and_preserves_original_casing():
    # Replaces the matched span but keeps surrounding casing intact.
    assert apply_find_replace("HELLO world", "hello", "hi", "normal", False) == "hi world"


def test_normal_case_insensitive_replaces_all():
    assert apply_find_replace("Ab ab AB", "ab", "_", "normal", False) == "_ _ _"


def test_empty_find_returns_none():
    assert apply_find_replace("hello", "", "X", "normal", True) is None


# apply_find_replace -- extended mode

def test_extended_decodes_newline_escape_in_find():
    # find is the two-char string backslash-n, decoded to a real newline.
    assert apply_find_replace("a\nb", chr(92) + "n", " ", "extended", True) == "a b"


def test_extended_decodes_tab_and_hex_in_replacement():
    # replacement is backslash-t backslash-x41 -> tab + char 0x41 ("A").
    repl = chr(92) + "t" + chr(92) + "x41"
    assert apply_find_replace("aXb", "X", repl, "extended", True) == "a\tAb"


def test_extended_decodes_backslash_and_null():
    assert apply_find_replace("a" + chr(92) + "b", chr(92) + chr(92), "/", "extended", True) == "a/b"
    assert apply_find_replace("a\x00b", chr(92) + "0", "-", "extended", True) == "a-b"


# apply_find_replace -- regular mode

def test_regex_capture_group_reference():
    result = apply_find_replace("John Smith", r"(\w+) (\w+)", r"\2 \1", "regular", True)
    assert result == "Smith John"


def test_regex_no_match_returns_none():
    assert apply_find_replace("abc", r"\d+", "X", "regular", True) is None


def test_regex_case_insensitive():
    assert apply_find_replace("Hello", r"hello", "hi", "regular", False) == "hi"


def test_regex_case_sensitive_no_match():
    assert apply_find_replace("Hello", r"hello", "hi", "regular", True) is None


def test_regex_invalid_raises_value_error():
    with pytest.raises(ValueError):
        apply_find_replace("abc", r"(", "X", "regular", True)


def test_unknown_mode_raises_value_error():
    with pytest.raises(ValueError):
        apply_find_replace("abc", "a", "X", "bogus", True)


# matches()

def test_matches_normal():
    assert matches("hello world", "world", "normal", True) is True
    assert matches("hello world", "WORLD", "normal", True) is False
    assert matches("hello world", "WORLD", "normal", False) is True


def test_matches_empty_find_matches_everything():
    assert matches("anything", "", "normal", True) is True


def test_matches_extended():
    assert matches("a\tb", "\t", "extended", True) is True


def test_matches_regular():
    assert matches("abc123", r"\d+", "regular", True) is True
    assert matches("abc", r"\d+", "regular", True) is False


def test_matches_regular_invalid_raises():
    with pytest.raises(ValueError):
        matches("abc", r"(", "regular", True)


# --- Phase 5: transform_caption ---------------------------------------------

from pgtp_editor.ui.caption_scan import TRANSFORM_KINDS, transform_caption


def test_transform_kinds_constant():
    assert TRANSFORM_KINDS == (
        "title",
        "upper",
        "lower",
        "sentence",
        "trim",
        "humanize",
    )


def test_transform_title():
    assert transform_caption("wbs id", "title") == "Wbs Id"


def test_transform_upper():
    assert transform_caption("Wbs Id", "upper") == "WBS ID"


def test_transform_lower():
    assert transform_caption("Wbs Id", "lower") == "wbs id"


def test_transform_sentence():
    assert transform_caption("hello WORLD", "sentence") == "Hello world"
    assert transform_caption("", "sentence") == ""


def test_transform_trim():
    assert transform_caption("  hello world  ", "trim") == "hello world"
    # internal runs are NOT collapsed
    assert transform_caption("  a   b  ", "trim") == "a   b"


def test_transform_humanize_drops_trailing_id():
    assert transform_caption("physicallocation_id", "humanize") == "Physicallocation"
    assert transform_caption("wbs_id", "humanize") == "Wbs"


def test_transform_humanize_multiword():
    assert transform_caption("physical_location_id", "humanize") == "Physical Location"


def test_transform_humanize_non_id_trailing_kept():
    assert transform_caption("criticality_lvl", "humanize") == "Criticality Lvl"


def test_transform_humanize_no_underscore():
    assert transform_caption("criticality", "humanize") == "Criticality"


def test_transform_unknown_kind_raises():
    with pytest.raises(ValueError):
        transform_caption("x", "bogus")
