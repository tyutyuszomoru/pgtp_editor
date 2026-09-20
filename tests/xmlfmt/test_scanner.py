"""`pgtp_editor.xmlfmt.scanner` -- the opacity-aware lexer (§18.4 part C).

Two invariants carry the whole formatter and are asserted here directly: the
token stream **tiles the input byte for byte**, and opaque constructs
(comments, CDATA, PIs, DOCTYPEs) are **single tokens whose interior is never
scanned** -- the phantom-tag defect that rules out reusing
`ui/xml_structure.scan` for an engine that rewrites text.
"""
from __future__ import annotations

import pytest

from pgtp_editor.xmlfmt.scanner import (
    CDATA,
    COMMENT,
    DOCTYPE,
    PI,
    TAG_CLOSE,
    TAG_OPEN,
    TAG_SELF_CLOSING,
    TEXT,
    LineIndex,
    scan,
)

PGTP_SHAPED = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<Project>\n"
    '  <Page name="customers" caption="Customers">\n'
    "    <!-- a <Page/> mentioned in a comment is NOT an element -->\n"
    '    <Fields>\n'
    '      <Field name="id" type="int"/>\n'
    "    </Fields>\n"
    '    <Event name="OnPageLoad">if ($x &lt; 1) { echo "hi"; }</Event>\n'
    "  </Page>\n"
    "</Project>\n"
)


def kinds(text: str) -> list[str]:
    return [tok.kind for tok in scan(text)]


# --------------------------------------------------------------------------
# Tiling / never-raises
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "",
        "   ",
        "plain text",
        "a < b and c > d",
        PGTP_SHAPED,
        "<a><b/></a>",
        "<!-- unterminated",
        "<![CDATA[ unterminated",
        "<?pi unterminated",
        "<!DOCTYPE unterminated",
        "<tag unterminated",
        "</",
        "<",
        "<<<>>>",
        "<a <b>",
        '<a x="1><b/>',
        "\r\n<a/>\r",
    ],
)
def test_tokens_tile_the_input_byte_for_byte(source):
    tokens = scan(source)
    assert "".join(tok.text for tok in tokens) == source
    for tok in tokens:
        assert tok.text == source[tok.start : tok.end]
    # Contiguous and ordered.
    cursor = 0
    for tok in tokens:
        assert tok.start == cursor
        assert tok.end > tok.start
        cursor = tok.end
    assert cursor == len(source)


def test_scan_never_raises_on_hostile_input():
    for source in ("<" * 200, "<!--" * 50, "<a" + 'b="' * 50, "\x00<a/>\x00"):
        scan(source)  # must simply return


# --------------------------------------------------------------------------
# Kinds
# --------------------------------------------------------------------------


def test_tag_kinds_and_names():
    tokens = scan('<Page name="a">text</Page><Field x="1"/>')
    assert [t.kind for t in tokens] == [TAG_OPEN, TEXT, TAG_CLOSE, TAG_SELF_CLOSING]
    assert [t.name for t in tokens] == ["Page", None, "Page", "Field"]


def test_greater_than_inside_a_quoted_attribute_does_not_end_the_tag():
    tokens = scan('<Field caption="a > b" other=\'c > d\'/>')
    assert len(tokens) == 1
    assert tokens[0].kind == TAG_SELF_CLOSING
    assert tokens[0].text.endswith("/>")


def test_self_closing_detection_tolerates_a_space_before_the_slash():
    assert kinds("<a />") == [TAG_SELF_CLOSING]
    assert kinds('<a b="x/">') == [TAG_OPEN]


@pytest.mark.parametrize(
    "source, kind",
    [
        ("<!-- <Page/> -->", COMMENT),
        ("<![CDATA[ <Page/> & ]]>", CDATA),
        ("<?php echo '<Page/>'; ?>", PI),
        ("<!DOCTYPE root SYSTEM 'x.dtd'>", DOCTYPE),
        ("<!DOCTYPE root [ <!ELEMENT a (b)> ]>", DOCTYPE),
        ("<!ENTITY foo 'bar'>", DOCTYPE),
    ],
)
def test_opaque_constructs_are_one_token_and_never_entered(source, kind):
    tokens = scan(source)
    assert [t.kind for t in tokens] == [kind]
    assert tokens[0].text == source
    assert not tokens[0].unterminated


def test_doctype_internal_subset_may_contain_angle_brackets():
    source = "<!DOCTYPE root [ <!ELEMENT a (b)> <!ELEMENT b (#PCDATA)> ]><root/>"
    tokens = scan(source)
    assert [t.kind for t in tokens] == [DOCTYPE, TAG_SELF_CLOSING]
    assert tokens[0].text.endswith("]>")


def test_a_comment_is_not_read_as_a_declaration():
    """`<!--` must be dispatched before the generic `<!`, or the comment's
    interior would stop being opaque at its first `>`."""
    tokens = scan("<!-- a > b --><x/>")
    assert [t.kind for t in tokens] == [COMMENT, TAG_SELF_CLOSING]


def test_the_phantom_tag_case_xml_structure_gets_wrong():
    tokens = scan("<a><!-- <b> --><![CDATA[</c>]]></a>")
    assert [t.kind for t in tokens] == [TAG_OPEN, COMMENT, CDATA, TAG_CLOSE]
    assert [t.name for t in tokens if t.name] == ["a", "a"]


def test_bare_less_than_stays_text():
    tokens = scan("1 < 2 and 3 > 2")
    assert [t.kind for t in tokens] == [TEXT]


# --------------------------------------------------------------------------
# Unterminated
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, kind",
    [
        ("<!-- x", COMMENT),
        ("<![CDATA[ x", CDATA),
        ("<?pi x", PI),
        ("<!DOCTYPE x", DOCTYPE),
        ("<tag attr", TAG_OPEN),
        ("</tag", TAG_CLOSE),
    ],
)
def test_unterminated_constructs_are_flagged_not_raised(source, kind):
    tokens = scan(source)
    assert [t.kind for t in tokens] == [kind]
    assert tokens[0].unterminated
    assert tokens[0].end == len(source)


def test_unquoted_less_than_inside_a_tag_stops_it_locally():
    """`<a <b/>` must not swallow the rest of the document."""
    tokens = scan("<a <b/>")
    assert tokens[0].kind == TAG_OPEN and tokens[0].unterminated
    assert tokens[0].text == "<a "
    assert tokens[1].kind == TAG_SELF_CLOSING


# --------------------------------------------------------------------------
# Spans and line/column
# --------------------------------------------------------------------------


def test_whitespace_predicate_is_text_only():
    tokens = scan("<a>\n  \n</a>")
    assert [t.is_whitespace for t in tokens] == [False, True, False]
    assert not scan("<a>x</a>")[1].is_whitespace


def test_line_and_column_are_one_based_and_end_is_exclusive():
    source = "<a>\n  <b/>\n</a>"
    b = [t for t in scan(source) if t.name == "b"][0]
    assert (b.start_line, b.start_col) == (2, 3)
    assert (b.end_line, b.end_col) == (2, 7)


def test_line_index_handles_all_three_line_endings():
    index = LineIndex("a\r\nb\nc\rd")
    assert index.line_col(0) == (1, 1)
    assert index.line_col(3) == (2, 1)  # after \r\n
    assert index.line_col(5) == (3, 1)  # after \n
    assert index.line_col(7) == (4, 1)  # after lone \r
    assert index.line_col(10_000) == (4, 2)  # clamped


def test_xsd_shaped_input_with_a_pi_and_a_comment():
    source = (
        '<?xml version="1.0"?>\n'
        "<!-- generated; do not edit -->\n"
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
        '  <xs:element name="root" type="xs:string"/>\n'
        "</xs:schema>\n"
    )
    tokens = [t for t in scan(source) if t.kind != TEXT]
    assert [t.kind for t in tokens] == [PI, COMMENT, TAG_OPEN, TAG_SELF_CLOSING, TAG_CLOSE]
    assert [t.name for t in tokens if t.name] == ["xs:schema", "xs:element", "xs:schema"]
