"""Pure (Qt-free) tests for the event-handler body helpers used by SP2's
XML-editor code-region styling + write-back."""
from lxml import etree

from pgtp_editor.ui.event_body import (
    event_body_line_ranges,
    extract_event_body,
    replace_event_body,
    xml_escape_body,
    xml_unescape_body,
)


# The real .pgtp storage format: escaped plain text between <OnXxx>...</OnXxx>.
MULTILINE = (
    "<Page>\n"
    '  <EventHandlers>\n'
    '    <OnPreparePage enabled="true">\n'
    "$this-&gt;dataset-&gt;AddDistinct('id');\n"
    "if (a &lt; b &amp;&amp; c) { d(); }\n"
    "    </OnPreparePage>\n"
    "  </EventHandlers>\n"
    "</Page>\n"
)

# Close tag on the same line as the last code line (with trailing indent).
SAME_LINE = (
    "<Page>\n"
    '  <OnBeforePageLoad enabled="true">\n'
    "$this-&gt;dataset-&gt;AddDistinct('id');                      </OnBeforePageLoad>\n"
    "</Page>\n"
)


# ---------------------------------------------------------------------------
# escape / unescape round-trip
# ---------------------------------------------------------------------------

def test_escape_orders_ampersand_first():
    assert xml_escape_body("a < b && c > d") == "a &lt; b &amp;&amp; c &gt; d"


def test_escape_unescape_round_trip():
    code = "if (x < 1 && y > 2) { z('a & b'); }"
    assert xml_unescape_body(xml_escape_body(code)) == code


def test_unescape():
    assert xml_unescape_body("a &lt; b &amp;&amp; c &gt; d") == "a < b && c > d"


# ---------------------------------------------------------------------------
# event_body_line_ranges
# ---------------------------------------------------------------------------

def test_line_ranges_multiline_body():
    ranges = event_body_line_ranges(MULTILINE)
    assert len(ranges) == 1
    r = ranges[0]
    assert r["tag"] == "OnPreparePage"
    assert r["side"] == "S"
    assert r["start_line"] == 3  # <OnPreparePage ...>
    assert r["end_line"] == 6  # </OnPreparePage>
    # Body is unescaped and includes both code lines.
    assert "$this->dataset->AddDistinct('id');" in r["body"]
    assert "if (a < b && c) { d(); }" in r["body"]


def test_line_ranges_close_on_same_line():
    ranges = event_body_line_ranges(SAME_LINE)
    assert len(ranges) == 1
    r = ranges[0]
    assert r["tag"] == "OnBeforePageLoad"
    assert r["side"] == "C"
    assert r["start_line"] == 2
    assert r["end_line"] == 3
    # Inner content is preserved faithfully: it begins with the newline after
    # the open tag's '>' and the last code line precedes the same-line close.
    assert "$this->dataset->AddDistinct('id');" in r["body"]


def test_line_ranges_finds_multiple_handlers_with_sides():
    text = (
        "<Page>\n"
        '  <OnBeforePageLoad enabled="true">alert(1);</OnBeforePageLoad>\n'
        '  <OnPreparePage enabled="true">$x-&gt;go();</OnPreparePage>\n'
        "</Page>\n"
    )
    ranges = event_body_line_ranges(text)
    assert [(r["tag"], r["side"]) for r in ranges] == [
        ("OnBeforePageLoad", "C"),
        ("OnPreparePage", "S"),
    ]


def test_line_ranges_ignores_non_handler_tags():
    text = "<Page>\n  <Caption>Hello</Caption>\n  <SomeOther>x</SomeOther>\n</Page>\n"
    assert event_body_line_ranges(text) == []


def test_line_ranges_ignores_self_closing_handler():
    text = '<Page>\n  <OnPreparePage enabled="true"/>\n</Page>\n'
    assert event_body_line_ranges(text) == []


def test_line_ranges_empty_body():
    text = '<Page>\n  <OnPreparePage enabled="true"></OnPreparePage>\n</Page>\n'
    ranges = event_body_line_ranges(text)
    assert len(ranges) == 1
    assert ranges[0]["body"] == ""


# ---------------------------------------------------------------------------
# extract_event_body (unescapes)
# ---------------------------------------------------------------------------

def test_extract_event_body_unescapes():
    tag, side, body = extract_event_body(MULTILINE, 1)
    assert tag == "OnPreparePage"
    assert side == "S"
    assert "$this->dataset->AddDistinct('id');" in body
    assert "&gt;" not in body


def test_extract_event_body_at_or_after_start_line():
    tag, _side, _body = extract_event_body(MULTILINE, 3)
    assert tag == "OnPreparePage"


def test_extract_event_body_no_handler_raises():
    import pytest

    with pytest.raises(ValueError):
        extract_event_body("<Page></Page>", 1)


# ---------------------------------------------------------------------------
# replace_event_body
# ---------------------------------------------------------------------------

def test_replace_swaps_only_inner_text_preserving_tags_and_outside():
    result = replace_event_body(MULTILINE, 3, "return 42;")
    # Tags + attributes preserved verbatim.
    assert '<OnPreparePage enabled="true">' in result
    assert "</OnPreparePage>" in result
    # New body present, escaped-form of old body gone.
    assert "return 42;" in result
    assert "AddDistinct" not in result
    # Everything outside the element preserved byte-for-byte.
    assert result.startswith("<Page>\n  <EventHandlers>\n")
    assert result.endswith("  </EventHandlers>\n</Page>\n")


def test_replace_escapes_special_chars():
    result = replace_event_body(SAME_LINE, 2, "if (a < b && c > d) e();")
    assert "if (a &lt; b &amp;&amp; c &gt; d) e();" in result
    # Raw '<'/'>' from the code must NOT appear as literal inner text (only the
    # tag delimiters do).
    inner = result.split('<OnBeforePageLoad enabled="true">', 1)[1].split(
        "</OnBeforePageLoad>", 1
    )[0]
    assert "<" not in inner and ">" not in inner


def test_replace_close_on_same_line_preserves_close_tag():
    result = replace_event_body(SAME_LINE, 2, "new();")
    assert "new();</OnBeforePageLoad>" in result


def test_replace_empty_body():
    result = replace_event_body(MULTILINE, 3, "")
    assert '<OnPreparePage enabled="true"></OnPreparePage>' in result


def test_replace_result_reparses_as_xml():
    result = replace_event_body(MULTILINE, 3, "if (a < b && c > d) { e(); }")
    root = etree.fromstring(result.encode("utf-8"))
    body = root.find(".//OnPreparePage").text
    # lxml gives back the unescaped text.
    assert body == "if (a < b && c > d) { e(); }"


def test_replace_no_handler_raises():
    import pytest

    with pytest.raises(ValueError):
        replace_event_body("<Page></Page>", 1, "x;")
